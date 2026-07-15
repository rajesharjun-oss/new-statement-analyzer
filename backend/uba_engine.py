import json
import re
from typing import List, Dict, Tuple, Any

# Import shared utilities from pdf_extractor
try:
    from pdf_extractor import group_words_to_rows
except ImportError:
    # Fallback if running standalone
    def group_words_to_rows(words, y_tol=3.0):
        if not words:
            return []
        sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
        rows = []
        current_row = {"top": sorted_words[0]["top"], "words": [sorted_words[0]]}
        for w in sorted_words[1:]:
            if abs(w["top"] - current_row["top"]) <= y_tol:
                current_row["words"].append(w)
            else:
                rows.append(current_row)
                current_row = {"top": w["top"], "words": [w]}
        rows.append(current_row)
        return rows


def parse_uba_ocr_text(json_text: str) -> List[Dict[str, Any]]:
    """
    Parse UBA transactions from OCR JSON output.
    Expected JSON structure: { "header": [...], "rows": [ {"Txn Date": "...", ...} ] }
    """
    transactions = []
    
    try:
        data = json.loads(json_text)
        rows = data.get("rows", [])
        
        print(f"DEBUG: Parsed {len(rows)} JSON rows from OCR")
        
        for row in rows:
            def get_val(keys):
                for k in keys:
                    if k in row and row[k]:
                        return row[k]
                return ""

            trans_date = get_val(["Txn Date", "Trans Date", "Date", "TRANS DATE"])
            value_date = get_val(["Value Date", "Val Date", "VALUE DATE"]) or trans_date
            desc = get_val(["Description", "Narration", "Details", "Particulars", "NARRATION",
                            "Transaction Remarks", "Remarks"])
            ref = get_val(["Reference", "Ref", "Chq No", "Cheque No", "CHQ NO",
                           "Cheque Number"])

            def parse_amt(val):
                if not val or str(val).isspace(): return 0.0
                try:
                    s = str(val).replace(',', '').strip()
                    v = float(s)
                    # Safety Clamp: Reject hallucinated massive amounts (>10 Billion)
                    if abs(v) > 10000000000.0:
                        return 0.0
                    return v
                except: return 0.0

            debit = parse_amt(get_val(["Debit", "Dr", "DEBIT", "Withdrawal", "WITHDRAWAL"]))
            credit = parse_amt(get_val(["Credit", "Cr", "CREDIT", "Deposit", "DEPOSIT"]))
            balance = parse_amt(get_val(["Balance", "Bal", "BALANCE"]))
            
            if not trans_date:
                continue
            if debit == 0.0 and credit == 0.0:
                continue

            txn = {
                "date": trans_date,
                "value_date": value_date,
                "description": desc,
                "debit": debit,
                "credit": credit,
                "balance": balance,
                "reference": ref
            }
            transactions.append(txn)
            
    except json.JSONDecodeError as e:
        print(f"DEBUG: JSON parse error: {e}")
        if "```json" in json_text:
             try:
                 clean_json = json_text.split("```json")[1].split("```")[0].strip()
                 return parse_uba_ocr_text(clean_json)
             except:
                 pass
        print("DEBUG: Raw text was not valid JSON.")
        return []
        
    return transactions


def detect_uba_columns(words: List[Dict], bank_identifier: str = "") -> Dict[str, Tuple[float, float]] | None:
    """
    Detect UBA column boundaries from header row.
    Supports two template variants:
      Template A: TRANS DATE | VALUE DATE | NARRATION | CHQ NO | DEBIT | CREDIT | BALANCE
      Template B: Transaction | Value Date | Cheque Number | Transaction Remarks | Withdrawal | Deposit | Balance
    """
    if not words:
        return None

    # --- Step 1: Find the header row by scoring ---
    keywords = [
        "TRANSACTION", "TRANS", "VALUE", "DATE", "NARRATION", "REMARKS",
        "CHQ", "CHEQUE", "NUMBER", "REF", "DEBIT", "CREDIT", "BALANCE",
        "WITHDRAWAL", "DEPOSIT", "LODGEMENT", "DESCRIPTION", "DETAILS"
    ]

    rows = group_words_to_rows(words, y_tol=3.0)

    best_row = None
    best_row_idx = -1
    max_score = 0

    for idx, r in enumerate(rows):
        row_text_upper = " ".join([w["text"].upper() for w in r["words"]])

        # Mandatory: must have DATE and BALANCE
        if "DATE" not in row_text_upper:
            continue
        if "BALANCE" not in row_text_upper:
            continue
        # Must have at least one amount keyword
        if not any(x in row_text_upper for x in ["DEBIT", "CREDIT", "WITHDRAWAL", "DEPOSIT"]):
            continue

        score = 0
        for w in r["words"]:
            for k in keywords:
                if k in w["text"].upper():
                    score += 1

        if score > max_score:
            max_score = score
            best_row = r
            best_row_idx = idx

    if not best_row or max_score < 4:
        return None

    print(f"DEBUG: Found UBA Header Row: {[w['text'] for w in best_row['words']]}")

    # --- Step 2: Also check the row immediately below for multi-line headers ---
    # UBA Template B splits "Transaction" + "Date" and "Cheque" + "Number" across two rows
    header_words = list(best_row["words"])
    if best_row_idx + 1 < len(rows):
        next_row = rows[best_row_idx + 1]
        next_text = " ".join([w["text"].upper() for w in next_row["words"]])
        # If next row has "DATE" or "NUMBER" it's likely continuation
        if any(k in next_text for k in ["DATE", "NUMBER"]):
            header_words.extend(next_row["words"])
            print(f"DEBUG: UBA multi-line header, added row: {[w['text'] for w in next_row['words']]}")

    # Sort header words by x0
    sorted_words = sorted(header_words, key=lambda w: w["x0"])

    # --- Step 3: Find column anchors ---
    def find_word(text_part, start_idx=0):
        for i in range(start_idx, len(sorted_words)):
            if text_part in sorted_words[i]["text"].upper():
                return i, sorted_words[i]
        return -1, None

    bounds = {}

    # 1. Transaction Date
    # IMPORTANT: Prefer DATE tokens over TRANS to avoid accidentally using
    # "TRANSACTION" as the date anchor in headers like:
    # S/NO | DATE | TRANSACTION DETAILS | ...
    date_candidates = [
        w for w in sorted_words
        if ("DATE" in w["text"].upper() and "VALUE" not in w["text"].upper())
    ]
    w_td = min(date_candidates, key=lambda w: w["x0"]) if date_candidates else None
    if not w_td:
        idx_td, w_td = find_word("TRANS DATE")
    if not w_td:
        idx_td, w_td = find_word("TRANS")
    if w_td:
        bounds["date"] = (w_td["x0"], w_td["x1"])

    # 2. Value Date
    idx_vd, w_vd = find_word("VALUE")
    if w_vd:
        bounds["value_date"] = (w_vd["x0"], w_vd["x1"])

    # 3. Description (Narration / Transaction Remarks / Remarks / Description / Transaction Details)
    idx_desc, w_desc = find_word("NARRATION")
    if not w_desc:
        idx_desc, w_desc = find_word("REMARKS")
    if not w_desc:
        idx_desc, w_desc = find_word("DESCRIPTION")
    if not w_desc:
        idx_desc, w_desc = find_word("DETAILS")
    if w_desc:
        bounds["description"] = (w_desc["x0"], w_desc["x1"])

    # 4. Reference (CHQ NO / Cheque Number / REF NO)
    idx_ref, w_ref = find_word("CHQ")
    if not w_ref:
        idx_ref, w_ref = find_word("CHEQUE")
    if not w_ref:
        idx_ref, w_ref = find_word("REF")
    if w_ref:
        bounds["reference"] = (w_ref["x0"], w_ref["x1"])

    # 5. Debit / Withdrawal
    idx_deb, w_deb = find_word("DEBIT")
    if not w_deb:
        idx_deb, w_deb = find_word("WITHDRAWAL")
    if w_deb:
        bounds["debit"] = (w_deb["x0"], w_deb["x1"])

    # 6. Credit / Deposit / Lodgement
    idx_cred, w_cred = find_word("CREDIT")
    if not w_cred:
        idx_cred, w_cred = find_word("DEPOSIT")
    if not w_cred:
        idx_cred, w_cred = find_word("LODG")
    if w_cred:
        bounds["credit"] = (w_cred["x0"], w_cred["x1"])

    # 7. Balance
    idx_bal, w_bal = find_word("BALANCE")
    if w_bal:
        bounds["balance"] = (w_bal["x0"], w_bal["x1"])

    # Mandatory: need at least date + one amount + balance
    if "date" not in bounds or ("debit" not in bounds and "credit" not in bounds):
        print("DEBUG: UBA detected header but missing critical columns")
        return None

    # --- Step 4: Build cuts with right-edge bias for numeric columns ---
    sorted_cols = sorted(bounds.items(), key=lambda item: item[1][0])

    cuts = {}
    for i in range(len(sorted_cols)):
        col_name, (l, r) = sorted_cols[i]

        if i == 0:
            # Don't force-start at x=0; this prevents serial/S-NO columns
            # from contaminating the date field.
            start = max(0.0, l - 5.0)
        else:
            prev_name, (prev_l, prev_r) = sorted_cols[i-1]
            # Tight boundary for description → give it max room
            if col_name == "description" and prev_name == "value_date":
                start = prev_r + 2
            elif col_name in ["debit", "credit", "balance"] and prev_name in ["debit", "credit"]:
                start = (prev_r + r) / 2
            else:
                start = (prev_r + l) / 2

        if i == len(sorted_cols) - 1:
            end = 1000.0
        else:
            next_name, (next_l, next_r) = sorted_cols[i+1]
            # Wide boundary for description
            if col_name == "description":
                end = next_l - 5
            elif col_name in ["debit", "credit"] and next_name in ["debit", "credit", "balance"]:
                end = (r + next_r) / 2
            else:
                end = (r + next_l) / 2

        cuts[col_name] = (start, end)

    print(f"DEBUG: UBA Column boundaries: {[(n, f'{l:.1f}-{r:.1f}') for n, (l, r) in cuts.items()]}")
    return cuts


UBA_AMOUNT_RE = re.compile(r"^\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?$|^\(?\d+(?:\.\d{2})?\)?$")
UBA_FULL_DATE_RE = re.compile(r"\b\d{2}-[A-Za-z]{3}-\d{4}\b")
UBA_PARTIAL_DATE_RE = re.compile(r"\b\d{2}-[A-Za-z]{3}-")
UBA_YEAR_RE = re.compile(r"\b20\d{2}\b")
UBA_FOOTER_MARKERS = (
    "DOWNLOAD APP",
    "CHAT WITH LEO",
    "OUR WEBSITE",
    "HEAD OFFICE",
    "PRIVACY POLICY",
    "AFRICA'SGLOBALBANK",
    "CFC@UBAGROUP.COM",
)


def _word_text(words: List[Dict[str, Any]]) -> str:
    return " ".join(str(w.get("text", "")) for w in sorted(words, key=lambda w: (w.get("x0", 0), w.get("top", 0))) if w.get("text"))


def _row_text(row: Dict[str, Any]) -> str:
    return _word_text(row.get("words", []))


def _region_words(row: Dict[str, Any], left: float, right: float) -> List[Dict[str, Any]]:
    return [
        w for w in sorted(row.get("words", []), key=lambda item: item.get("x0", 0))
        if float(w.get("x0", 0)) >= left and float(w.get("x0", 0)) < right
    ]


def _region_text(row: Dict[str, Any], left: float, right: float) -> str:
    return _word_text(_region_words(row, left, right))


def _first_header_word(words: List[Dict[str, Any]], *needles: str) -> Dict[str, Any] | None:
    for word in sorted(words, key=lambda item: item.get("x0", 0)):
        text = str(word.get("text", "")).upper()
        if any(needle in text for needle in needles):
            return word
    return None


def _detect_uba_amount_layout(rows: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    for row in rows:
        words = row.get("words", [])
        upper = _row_text(row).upper()
        if not all(token in upper for token in ("TRANS", "VALUE", "BALANCE")):
            continue
        if not any(token in upper for token in ("NARRATION", "REMARKS", "DETAILS", "DESCRIPTION")):
            continue
        if not any(token in upper for token in ("DEBIT", "WITHDRAWAL")):
            continue
        if not any(token in upper for token in ("CREDIT", "DEPOSIT", "LODGEMENT")):
            continue

        trans_word = _first_header_word(words, "TRANS", "TRANSACTION")
        value_word = _first_header_word(words, "VALUE")
        desc_word = _first_header_word(words, "NARRATION", "REMARKS", "DETAILS", "DESCRIPTION")
        debit_word = _first_header_word(words, "DEBIT", "WITHDRAWAL")
        credit_word = _first_header_word(words, "CREDIT", "DEPOSIT", "LODGEMENT")
        balance_word = _first_header_word(words, "BALANCE")
        date_words = [w for w in sorted(words, key=lambda item: item.get("x0", 0)) if "DATE" in str(w.get("text", "")).upper()]

        if not (trans_word and value_word and desc_word and debit_word and credit_word and balance_word):
            continue

        value_date_right = float(date_words[1].get("x1", 151.0)) + 8.0 if len(date_words) >= 2 else float(desc_word.get("x0", 165.0)) - 6.0
        value_date_right = min(value_date_right, float(desc_word.get("x0", value_date_right + 5.0)) - 4.0)
        date_left = max(0.0, float(trans_word.get("x0", 35.0)) - 10.0)
        date_right = float(value_word.get("x0", 100.0)) - 4.0
        value_left = max(date_right, float(value_word.get("x0", 100.0)) - 6.0)
        desc_left = max(value_date_right - 6.0, 150.0)
        desc_right = float(debit_word.get("x0", 345.0)) - 8.0
        amount_left = float(debit_word.get("x0", 345.0)) - 30.0
        debit_right = float(credit_word.get("x0", 425.0)) - 10.0
        balance_left = float(balance_word.get("x0", 507.0)) - 10.0

        return {
            "header_top": float(row.get("top", 0.0)),
            "date": (date_left, date_right),
            "value_date": (value_left, value_date_right),
            "description": (desc_left, desc_right),
            "amount": (amount_left, balance_left),
            "debit_right": debit_right,
            "balance": (balance_left, 1000.0),
        }
    return None


def _is_uba_body_noise(text: str) -> bool:
    upper = text.upper().replace(" ", "")
    return any(marker.replace(" ", "") in upper for marker in UBA_FOOTER_MARKERS)


def _money_from_token(text: str, parse_money_func) -> float | None:
    raw = str(text or "").strip()
    if not raw or not UBA_AMOUNT_RE.match(raw):
        return None
    value = parse_money_func(raw)
    if value == 0.0 and not re.search(r"\d", raw):
        return None
    return round(float(value), 2)


def _date_from_nearby_rows(rows: List[Dict[str, Any]], idx: int, bounds: Tuple[float, float], fallback: str = "") -> str:
    left, right = bounds
    same_row = _region_text(rows[idx], left, right) if 0 <= idx < len(rows) else ""
    same_match = UBA_FULL_DATE_RE.search(same_row)
    if same_match:
        return same_match.group(0)

    for part_idx in [idx, idx - 1, idx - 2, idx - 3]:
        if part_idx < 0 or part_idx >= len(rows):
            continue
        part_text = _region_text(rows[part_idx], left, right)
        part_match = UBA_PARTIAL_DATE_RE.search(part_text)
        if not part_match:
            continue
        for year_idx in [part_idx, part_idx + 1, part_idx + 2, idx, idx + 1, idx + 2, idx + 3]:
            if year_idx < 0 or year_idx >= len(rows):
                continue
            year_text = _region_text(rows[year_idx], left, right)
            year_match = UBA_YEAR_RE.search(year_text)
            if year_match:
                return part_match.group(0) + year_match.group(0)

    for row_idx in [idx - 1, idx + 1, idx - 2, idx + 2, idx - 3, idx + 3]:
        if row_idx < 0 or row_idx >= len(rows):
            continue
        text = _region_text(rows[row_idx], left, right)
        match = UBA_FULL_DATE_RE.search(text)
        if match:
            return match.group(0)
    return fallback


def _clean_uba_description(text: str) -> str:
    text = re.sub(r"\bTRANS\b|\bVALUE\b|\bNARRATION\b|\bDEBIT\b|\bCREDIT\b|\bBALANCE\b|\bCHQ\b|\bNO\b", " ", text, flags=re.I)
    text = re.sub(r"\b\d{2}-[A-Za-z]{3}-\d{4}\b", " ", text)
    text = re.sub(r"\b20\d{2}\b", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -|/")


def _description_for_amount_row(
    rows: List[Dict[str, Any]],
    idx: int,
    amount_row_indices: set[int],
    layout: Dict[str, Any],
) -> str:
    left, right = layout["description"]
    parts: List[str] = []
    row_top = float(rows[idx].get("top", 0.0))

    before = idx - 1
    while before >= 0 and before not in amount_row_indices:
        if row_top - float(rows[before].get("top", 0.0)) > 22.0:
            break
        text = _region_text(rows[before], left, right)
        if text and not _is_uba_body_noise(text):
            parts.insert(0, text)
        before -= 1

    same = _region_text(rows[idx], left, right)
    if same and not _is_uba_body_noise(same):
        parts.append(same)

    return _clean_uba_description(" ".join(parts))


def _extract_uba_amount_line_transactions(pdf: Any, metadata: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import group_words_to_rows, parse_money

    transactions: List[Dict[str, Any]] = []
    last_date = ""
    last_value_date = ""

    for page_num, page in enumerate(pdf.pages, start=1):
        words = page.extract_words(x_tolerance=2, y_tolerance=2, keep_blank_chars=False)
        if not words:
            continue
        page_rows = group_words_to_rows(words, y_tol=3.0)
        layout = _detect_uba_amount_layout(page_rows)
        if not layout:
            continue

        body_rows: List[Dict[str, Any]] = []
        for row in page_rows:
            row_top = float(row.get("top", 0.0))
            text = _row_text(row)
            if row_top <= layout["header_top"] + 6.0 or row_top > 735.0:
                continue
            if _is_uba_body_noise(text):
                continue
            body_rows.append({"page": page_num, "top": row_top, "words": row.get("words", [])})

        amount_entries: List[Tuple[int, Dict[str, Any], str, float, float]] = []
        amount_left, amount_right = layout["amount"]
        balance_left, balance_right = layout["balance"]
        amount_row_indices: set[int] = set()

        for idx, row in enumerate(body_rows):
            balance_values = [
                _money_from_token(word.get("text", ""), parse_money)
                for word in _region_words(row, balance_left, balance_right)
            ]
            balance_values = [value for value in balance_values if value is not None]
            if not balance_values:
                continue
            balance = balance_values[-1]
            for word in _region_words(row, amount_left, amount_right):
                amount = _money_from_token(word.get("text", ""), parse_money)
                if amount is None:
                    continue
                kind = "debit" if float(word.get("x1", 0.0)) <= layout["debit_right"] else "credit"
                amount_entries.append((idx, row, kind, amount, balance))
                amount_row_indices.add(idx)

        for idx, row, kind, amount, balance in amount_entries:
            txn_date = _date_from_nearby_rows(body_rows, idx, layout["date"], last_date)
            value_date = _date_from_nearby_rows(body_rows, idx, layout["value_date"], last_value_date or txn_date)
            if txn_date:
                last_date = txn_date
            if value_date:
                last_value_date = value_date
            description = _description_for_amount_row(body_rows, idx, amount_row_indices, layout)
            raw_text = _row_text(row)
            transactions.append({
                "date": txn_date,
                "value_date": value_date or txn_date,
                "description": description,
                "debit": amount if kind == "debit" else 0.0,
                "credit": amount if kind == "credit" else 0.0,
                "balance": balance,
                "reference": "",
                "_page": page_num,
                "_row": round(float(row.get("top", 0.0)), 2),
                "raw_text": raw_text,
            })

    if not transactions:
        return [], metadata

    amount_meta = {**metadata, "bank": "uba", "method": "uba_amount_lines"}
    stmt_debit = _money_from_token(str(amount_meta.get("statement_total_debit") or ""), parse_money)
    stmt_credit = _money_from_token(str(amount_meta.get("statement_total_credit") or ""), parse_money)
    extracted_debit = round(sum(float(txn.get("debit") or 0.0) for txn in transactions), 2)
    extracted_credit = round(sum(float(txn.get("credit") or 0.0) for txn in transactions), 2)
    print(
        "DEBUG: UBA amount-line parser extracted "
        f"{len(transactions)} rows (debit={extracted_debit:.2f}, credit={extracted_credit:.2f})."
    )

    if stmt_debit is not None and stmt_credit is not None:
        if abs(extracted_debit - stmt_debit) <= 1.0 and abs(extracted_credit - stmt_credit) <= 1.0:
            return transactions, amount_meta
        print(
            "WARN: UBA amount-line parser totals mismatch "
            f"(debit_diff={extracted_debit - stmt_debit:.2f}, credit_diff={extracted_credit - stmt_credit:.2f})."
        )
        return [], metadata

    return transactions, amount_meta


import pdfplumber
from pathlib import Path


def extract_uba_via_coordinates(pdf_path: Path, metadata: Dict[str, Any], pdf: pdfplumber.PDF = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import parse_date_smart, parse_money, is_noise_row, group_words_to_rows, assign_row_to_cols, merge_multiline_rows
    
    # If pdf handle is provided, use it, otherwise open
    _auto_close = False
    if pdf is None:
        pdf = pdfplumber.open(pdf_path)
        _auto_close = True
        
    amount_txns, amount_meta = _extract_uba_amount_line_transactions(pdf, metadata)
    if amount_txns:
        if _auto_close:
            pdf.close()
        return amount_txns, amount_meta

    all_rows = []
    cuts = None
    
    try:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            if not words: continue
            
            # Re-detect cuts on every page to be safe
            page_cuts = detect_uba_columns(words)
            if page_cuts: cuts = page_cuts
            
            if not cuts: continue
            
            row_groups = group_words_to_rows(words, y_tol=3.0)
            for rg in row_groups:
                row = assign_row_to_cols(rg["words"], cuts)
                if is_noise_row(row): continue
                row["_page"] = page_num
                all_rows.append(row)
                
        txns = merge_multiline_rows(all_rows)
        # Final cleanup/parsing happens in map_uba_records or returning to extractor
        return txns, metadata
    finally:
        if _auto_close:
            pdf.close()
