"""
ecobank_extractor.py
====================
Standalone Ecobank bank-statement extractor.
- No categorisation (just extraction).
- Uses pdfplumber word positions + midpoint assignment — avoids the
  pdfplumber table-extraction bugs that were leaving Description empty.
"""
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import pdfplumber
import pandas as pd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MONEY_RE = re.compile(
    r"^-?\d{1,3}(?:,\d{3})*(?:\.\d{2})$|^-?\d+(?:\.\d{2})$"
)
DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}$")  # e.g. 05-Jun-2025


def parse_money(s: str) -> Optional[float]:
    s = (s or "").strip().replace(" ", "")
    if not s:
        return None
    if not MONEY_RE.match(s):
        return None
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None


def looks_like_date(s: str) -> bool:
    return bool(DATE_RE.match((s or "").strip()))


def safe_join(parts: List[str]) -> str:
    txt = " ".join(p for p in (p.strip() for p in parts) if p)
    return re.sub(r"\s+", " ", txt).strip()


def normalize_ref(desc: str) -> Tuple[str, str]:
    """Pull 'REFNO:…' out of description.  Returns (reference, cleaned_description)."""
    if not desc:
        return "", ""
    m = re.search(r"\bREF(?:NO)?[:\s]*([A-Za-z0-9]+)\b", desc, flags=re.IGNORECASE)
    if not m:
        return "", desc.strip()
    ref = m.group(1).strip()
    cleaned = re.sub(
        r"\bREF(?:NO)?[:\s]*" + re.escape(ref) + r"\b", "", desc, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,|-")
    return ref, cleaned


# ---------------------------------------------------------------------------
# Column-bounds detection
# ---------------------------------------------------------------------------

@dataclass
class ColumnBounds:
    txn_date:    Tuple[float, float]
    description: Tuple[float, float]
    value_date:  Tuple[float, float]
    debit:       Tuple[float, float]
    credit:      Tuple[float, float]
    balance:     Tuple[float, float]


def _midpoint(x0: float, x1: float) -> float:
    return (x0 + x1) / 2.0


def _in_interval(x: float, interval: Tuple[float, float]) -> bool:
    return interval[0] <= x < interval[1]


def _group_words_to_lines(words: List[Dict], y_tol: float = 2.0) -> List[List[Dict]]:
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
    lines: List[List[Dict]] = []
    cur: List[Dict] = []
    last_top = None
    for w in sorted_words:
        t = w["top"]
        if last_top is None or abs(t - last_top) <= y_tol:
            cur.append(w)
        else:
            lines.append(cur)
            cur = [w]
        last_top = t
    if cur:
        lines.append(cur)
    return lines


def _find_header_bounds(words: List[Dict]) -> Optional[Tuple[ColumnBounds, float]]:
    """
    Detect the transaction table header and return (ColumnBounds, header_top_y).

    Requires all six column titles to be present on the same logical line:
        Transaction  Date  Description  Value  Date  Debit  Credit  Balance

    Returns None if the header cannot be detected.
    """
    lines = _group_words_to_lines(words, y_tol=3.0)

    def line_text(ln: List[Dict]) -> str:
        return " ".join(w["text"] for w in ln).lower()

    def find_x(ln: List[Dict], *token_seqs: Tuple[str, ...]) -> Optional[float]:
        """Return x0 of the first word that matches any of the token sequences."""
        texts = [w["text"].lower() for w in ln]
        for tokens in token_seqs:
            for i in range(len(texts)):
                if all(
                    i + j < len(texts) and texts[i + j] == tokens[j]
                    for j in range(len(tokens))
                ):
                    return ln[i]["x0"]
        return None

    for ln in lines:
        t = line_text(ln)
        # All six concepts must appear
        if not (
            "transaction" in t
            and "description" in t
            and "value" in t
            and "debit" in t
            and "credit" in t
            and "balance" in t
        ):
            continue

        # Locate x positions of each column label
        x_txn  = find_x(ln, ("transaction",), ("date",))
        x_desc = find_x(ln, ("description",))
        x_val  = find_x(ln, ("value",))
        x_deb  = find_x(ln, ("debit",), ("withdrawal",), ("dr",))
        x_cre  = find_x(ln, ("credit",), ("deposit",), ("cr",))
        x_bal  = find_x(ln, ("balance",), ("bal",))

        # Use the leftmost word's x0 as tx_txn if "transaction" not found separately
        if x_txn is None and ln:
            x_txn = ln[0]["x0"]

        if None in (x_txn, x_desc, x_val, x_deb, x_cre, x_bal):
            continue
        if not (x_txn < x_desc < x_val < x_deb < x_cre < x_bal):
            continue

        pad = 2.0
        bounds = ColumnBounds(
            txn_date    = (0.0,         x_desc - pad),
            description = (x_desc - pad, x_val  - pad),
            value_date  = (x_val  - pad, x_deb  - pad),
            debit       = (x_deb  - pad, x_cre  - pad),
            credit      = (x_cre  - pad, x_bal  - pad),
            balance     = (x_bal  - pad, 10_000.0),
        )
        header_top = min(w["top"] for w in ln)
        return bounds, header_top

    return None


# ---------------------------------------------------------------------------
# Row extraction
# ---------------------------------------------------------------------------

def _words_to_raw_rows(words: List[Dict], bounds: ColumnBounds) -> List[Dict]:
    """Assign each word on the page to a column bucket using its centroid x."""
    lines = _group_words_to_lines(words, y_tol=2.0)
    rows: List[Dict] = []

    for ln in lines:
        b: Dict[str, List[str]] = {
            "txn": [], "desc": [], "val": [], "deb": [], "cre": [], "bal": []
        }
        for w in ln:
            txt = w["text"].strip()
            if not txt:
                continue
            x = _midpoint(w["x0"], w["x1"])
            if   _in_interval(x, bounds.txn_date):    b["txn"].append(txt)
            elif _in_interval(x, bounds.description): b["desc"].append(txt)
            elif _in_interval(x, bounds.value_date):  b["val"].append(txt)
            elif _in_interval(x, bounds.debit):        b["deb"].append(txt)
            elif _in_interval(x, bounds.credit):       b["cre"].append(txt)
            elif _in_interval(x, bounds.balance):      b["bal"].append(txt)

        txn_txt  = safe_join(b["txn"])
        desc_txt = safe_join(b["desc"])
        val_txt  = safe_join(b["val"])
        deb_txt  = safe_join(b["deb"])
        cre_txt  = safe_join(b["cre"])
        bal_txt  = safe_join(b["bal"])

        # Only keep lines with meaningful content
        has_money = any(
            parse_money(v) is not None for v in [deb_txt, cre_txt, bal_txt]
        )
        if not (looks_like_date(txn_txt) or has_money or desc_txt):
            continue

        # Guard: value_date must look like a date (never an amount)
        if val_txt and parse_money(val_txt) is not None and not looks_like_date(val_txt):
            val_txt = ""

        rows.append({
            "Txn Date":    txn_txt,
            "Value Date":  val_txt,
            "Description": desc_txt,
            "Debit_raw":   deb_txt,
            "Credit_raw":  cre_txt,
            "Balance_raw": bal_txt,
        })

    return rows


# ---------------------------------------------------------------------------
# Continuation-line merging
# ---------------------------------------------------------------------------

def _merge_continuations(rows: List[Dict]) -> List[Dict]:
    """
    Rows without a Txn Date are description continuations; merge them into
    the previous transaction row.
    """
    merged: List[Dict] = []
    current: Optional[Dict] = None

    for r in rows:
        txn_date = (r.get("Txn Date") or "").strip()
        desc     = (r.get("Description") or "").strip()

        # Skip opening/closing balance summary lines
        desc_up = desc.upper()
        if "OPENING BALANCE" in desc_up or "CLOSING BALANCE" in desc_up:
            continue

        if looks_like_date(txn_date):
            current = r.copy()
            merged.append(current)
        else:
            if current is None:
                continue
            # Append continuation description
            if desc:
                current["Description"] = safe_join(
                    [current.get("Description", ""), desc]
                )
            # Fill missing value_date from continuation
            if not current.get("Value Date") and r.get("Value Date"):
                if looks_like_date(r["Value Date"]):
                    current["Value Date"] = r["Value Date"]
            # Fill missing amounts from continuation (rare edge case)
            for k in ("Debit_raw", "Credit_raw", "Balance_raw"):
                if not (current.get(k) or "").strip() and (r.get(k) or "").strip():
                    current[k] = r[k]

    return merged


# ---------------------------------------------------------------------------
# Finalise to typed DataFrame
# ---------------------------------------------------------------------------

def _finalize(rows: List[Dict]) -> pd.DataFrame:
    out = []
    for r in rows:
        txn_date = (r.get("Txn Date") or "").strip()
        val_date = (r.get("Value Date") or "").strip()
        desc     = (r.get("Description") or "").strip()

        debit   = parse_money(r.get("Debit_raw",   ""))
        credit  = parse_money(r.get("Credit_raw",  ""))
        balance = parse_money(r.get("Balance_raw", ""))

        if not looks_like_date(txn_date):
            continue
        # Skip rows with literally nothing
        if not desc and debit is None and credit is None and balance is None:
            continue

        ref, cleaned_desc = normalize_ref(desc)

        out.append({
            "Txn Date":   txn_date,
            "Value Date": val_date if looks_like_date(val_date) else "",
            "Reference":  ref,
            "Description": cleaned_desc,
            "Debit":      float(debit)   if debit   is not None else 0.0,
            "Credit":     float(credit)  if credit  is not None else 0.0,
            "Balance":    float(balance) if balance is not None else 0.0,
        })

    df = pd.DataFrame(out)
    if not df.empty:
        df = df.drop_duplicates(
            subset=["Txn Date", "Value Date", "Reference", "Description",
                    "Debit", "Credit", "Balance"]
        )
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_ecobank_transactions(pdf_path: str) -> pd.DataFrame:
    """
    Extract all transactions from an Ecobank statement PDF.

    Returns a DataFrame with columns:
        Txn Date | Value Date | Reference | Description | Debit | Credit | Balance
    """
    all_rows: List[Dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            words = page.extract_words(
                x_tolerance=1.5,
                y_tolerance=2.0,
                keep_blank_chars=False,
                use_text_flow=True,
            )
            if not words:
                continue

            result = _find_header_bounds(words)
            if result is None:
                # Page has no transaction table header — skip
                continue

            bounds, header_top = result

            # Only look at words BELOW the header line
            data_words = [w for w in words if w["top"] > header_top + 4.0]

            page_rows = _words_to_raw_rows(data_words, bounds)

            # Drop obvious page-footer noise
            cleaned = [
                r for r in page_rows
                if not re.search(
                    r"^page\s+\d+|authorised\s+signatory|this\s+is\s+a\s+computer",
                    (r.get("Description") or "").lower(),
                )
            ]
            all_rows.extend(cleaned)

    merged = _merge_continuations(all_rows)
    df     = _finalize(merged)
    print(f"[ecobank_extractor] Extracted {len(df)} transactions from {pdf_path!r}")
    return df


def df_to_transactions(df: pd.DataFrame) -> List[Dict]:
    """
    Convert the DataFrame from extract_ecobank_transactions() into the
    list-of-dicts format expected by the main pipeline
    (i.e. same schema as other banks in pdf_extractor.py).
    """
    txns = []
    for i, row in df.iterrows():
        txns.append({
            "date":               row["Txn Date"],
            "value_date":         row["Value Date"],
            "reference":          row["Reference"],
            "originating_branch": "",
            "remarks":            row["Description"],
            "description":        row["Description"],
            "debit":              float(row["Debit"]),
            "credit":             float(row["Credit"]),
            "balance":            float(row["Balance"]),
            "category":           "Unallocated",
            "is_reversal":        False,
            "_page":              0,
            "_row":               int(i),
        })
    return txns


if __name__ == "__main__":
    import sys
    pdf = sys.argv[1] if len(sys.argv) > 1 else "ecobank_statement.pdf"
    out = sys.argv[2] if len(sys.argv) > 2 else "ecobank_transactions.xlsx"
    df = extract_ecobank_transactions(pdf)
    print(df.to_string())
