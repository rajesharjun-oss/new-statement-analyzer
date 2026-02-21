"""
Backend PDF Extraction with pdfplumber
"""
import pdfplumber
import re
import math
import os
import pandas as pd
from pathlib import Path
from typing import List, Dict, Tuple, Any

from uba_engine import detect_uba_columns, parse_uba_ocr_text
try:
    from gemini_vision import extract_text_with_gemini_vision, extract_transactions_via_ai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    def extract_transactions_via_ai(*args, **kwargs): return []

# OCR fallback
try:
    from ocr_helper import extract_text_with_ocr
    OCR_MODULE_AVAILABLE = True
except ImportError:
    OCR_MODULE_AVAILABLE = False
    def extract_text_with_ocr(*args, **kwargs):
        raise ImportError("ocr_helper module not found")

# Define OCR availability based on OpenAI API key presence
OCR_AVAILABLE = bool(os.getenv("OPENAI_API_KEY"))

# Regex patterns for field repair (GTBank-specific)
BRANCH_LIKE = re.compile(r"^\s*\d{3}\s+[A-Z][A-Z ]+\s*$")
BRANCH_PREFIX = re.compile(r"^\s*(\d{3}\s+[A-Z][A-Z ]+)\s+(.*)$")
REF_TOKEN = re.compile(r"^'?([A-Z0-9]{6,})$")

def looks_like_ref(tok: str) -> bool:
    """Check if token looks like a reference ID (must contain digits)"""
    t = tok.strip().strip("'")
    return len(t) >= 6 and any(c.isdigit() for c in t)  # Must contain digits

# Flexible date patterns
DATE_DMY_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$")       # 01-Jan-2023 OR 1-JAN-2026
DATE_MDY_SL_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")      # 10/1/2025 (Access)
DATE_DMY_YY_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$")    # 15-Jan-21 (Fidelity)
MONEY_RE = re.compile(r"^-?[\d,]+(?:\.\d{2})?$")             # Standard money pattern

from datetime import datetime
import pandas as pd

def is_date(text: str) -> bool:
    """
    Check if text looks like a date (DD/MM/YYYY, DD-MMM-YYYY, YYYY-MM-DD, or DD Mon YYYY)
    """
    if not text or len(text) < 6:
        return False
    # Standard: 31/01/2023, 31-Jan-2023, 2023-01-31
    if re.match(r"^\d{1,2}[-/\.]\w{3,}[-/\.]\d{2,4}$", text): return True
    if re.match(r"^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}$", text): return True
    if re.match(r"^\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}$", text): return True
    
    # Space separated: 01 Jan 2024 (FCMB) - Allow leading/trailing spaces
    if re.match(r"^\s*\d{1,2}\s+\w{3,}\.?\s+\d{2,4}\s*$", text): return True
    
    return False

def parse_date(text: str) -> str:
    """
    Normalize date to YYYY-MM-DD
    """
    try:
        # 1. DD Mon YYYY (01 Jan 2024)
        if re.match(r"^\s*\d{1,2}\s+\w{3,}\.?\s+\d{2,4}\s*$", text):
            # clean up spaces
            clean = re.sub(r"\s+", " ", text.strip())
            return datetime.strptime(clean, "%d %b %Y").strftime("%Y-%m-%d")
            
        # 2. Standard formats
        return pd.to_datetime(text, dayfirst=True).strftime("%Y-%m-%d")
    except:
        return text

# ... (keep existing code) ...

def detect_providus_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for Providus Bank (TXN DATE | VAL DATE | REMARKS | DEBIT | CREDIT | BALANCE)
    """
    # 1) Find header row
    header_keywords = ["TXN DATE", "VAL DATE", "REMARKS", "DEBIT", "CREDIT", "BALANCE"]
    
    # Filter words that match keywords
    header_words = []
    for w in words:
        txt = w["text"].upper().strip()
        if any(k in txt for k in header_keywords):
            header_words.append(w)
            
    if len(header_words) < 3:
        return None
        
    # Group by Y to find the main header line
    rows = group_words_to_rows(header_words, y_tol=2.0)
    best_row = max(rows, key=lambda r: len(r["words"]))
    
    if len(best_row["words"]) < 3:
        return None
        
    # Extract known columns from this row
    # Use simple x-coordinate mapping
    
    def find_x(sub: str):
        matches = [w["x0"] for w in best_row["words"] if sub in w["text"].upper()]
        return min(matches) if matches else None
        
    def find_x_right(sub: str):
        matches = [w["x1"] for w in best_row["words"] if sub in w["text"].upper()]
        return max(matches) if matches else None

    x_txn = find_x("TXN")
    x_val = find_x("VAL")
    x_rem = find_x("REMARKS")
    x_deb = find_x_right("DEBIT")
    x_cred = find_x_right("CREDIT")
    x_bal = find_x_right("BALANCE")
    
    if x_txn is None:
        return None

    # Build columns
    cols = [("date", x_txn)]
    
    if x_val is not None:
        cols.append(("value_date", x_val))
    if x_rem is not None:
        cols.append(("description", x_rem))
    if x_deb is not None:
        cols.append(("debit", x_deb))
    if x_cred is not None:
        cols.append(("credit", x_cred))
    if x_bal is not None:
        cols.append(("balance", x_bal))
        
    # Sort by X
    cols = sorted(cols, key=lambda x: x[1])
    
    # Calculate cuts
    cuts = {}
    for i, (name, x) in enumerate(cols):
        if i == 0:
            cuts[name] = (-math.inf, (x + cols[i+1][1]) / 2)
        elif i == len(cols) - 1:
             cuts[name] = ((cols[i-1][1] + x) / 2, math.inf)
        else:
             cuts[name] = ((cols[i-1][1] + x) / 2, (x + cols[i+1][1]) / 2)
             
    print(f"DEBUG: Providus Columns: {cuts}")
    return cuts

def detect_column_cuts_from_header(words: List[Dict[str, Any]], bank_identifier: str = "gtbank") -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries from the header row (routes to bank-specific logic)
    """
    # SMART TEMPLATE DETECTION: Try all robust detectors and pick the best one.
    # This avoids fragility where a bank name isn't detected or a header keyword is slightly off.
    
    detectors = [
        ("Providus", detect_providus_columns),
        ("Zenith", detect_zenith_columns),
        ("Wema", detect_wema_columns),
        ("FCMB", detect_fcmb_columns),
        ("FirstBank", detect_firstbank_columns),
        ("Ecobank", detect_ecobank_columns),
        ("UBA", detect_uba_columns),
        ("Access", detect_access_columns),
        ("Fidelity", detect_fidelity_columns),
        ("AptSecurities", detect_apt_columns),
        ("GTBank", detect_gtbank_columns) # Fallback last
    ]
    
    best_cuts = None
    best_score = -1
    best_name = ""
    
    print(f"DEBUG: Starting Smart Template Detection for bank hint: {bank_identifier}")
    
    # Priority: if bank_identifier matches a specific detector, try that FIRST with a bonus score
    # But still try others if it fails.
    
    for name, detector_func in detectors:
        try:
            # UBA and Access need extra args
            if name == "UBA":
                cuts = detector_func(words, "uba")
            elif name == "Access":
                cuts = detector_func(words, "accessbank")
            elif name == "Fidelity":
                cuts = detector_func(words, "fidelity")
            elif name == "AptSecurities":
                cuts = detector_func(words, "apt_securities")
            elif name == "FirstBank":
                cuts = detector_func(words)
            elif name == "Wema":
                cuts = detector_func(words)
            elif name == "FCMB":
                cuts = detector_func(words)
            else:
                cuts = detector_func(words)
            
            if cuts:
                # Score = number of columns found
                score = len(cuts)
                
                # Bonus for mandatory columns (Date, Debit, Credit)
                if "TransDate" in cuts and "Debit" in cuts and "Credit" in cuts:
                    score += 2
                    
                # Bonus if this matches the user/auto-detected bank
                if bank_identifier and name.lower() in bank_identifier.lower():
                     score += 5
                
                print(f"DEBUG: Detector {name} found {len(cuts)} columns. Score: {score}")
                
                if score > best_score:
                    best_score = score
                    best_cuts = cuts
                    best_name = name
                    
        except Exception as e:
            print(f"DEBUG: Detector {name} crashed: {e}")
            continue

    if best_cuts:
        print(f"DEBUG: Selected Best Template: {best_name} (Score: {best_score})")
        return best_cuts

    # Last resort fallback if everything failed
    return detect_gtbank_columns(words)


def parse_date_smart(date_str: str) -> str | None:
    """
    Parse various date formats robustly.
    Normalization: DD-MMM-YYYY (e.g., 15-Jan-2023)
    """
    s = (date_str or "").strip()
    if not s or len(s) < 6:
        return None
    
    # Standard: 01-Jan-2023
    if DATE_DMY_RE.match(s):
        return s
        
    try:
        # Use pandas for robust parsing. dayfirst=True is critical for Nigerian banks.
        dt = pd.to_datetime(s, dayfirst=True, errors='coerce')
        if pd.isna(dt):
            # Check for DD-MMM-YY (Fidelity 15-Jan-21)
            if DATE_DMY_YY_RE.match(s):
                parts = s.split('-')
                return f"{parts[0]}-{parts[1]}-20{parts[2]}"
            return None
        return dt.strftime("%d-%b-%Y")
    except:
        return None

# Strict money parsing
MONEY_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})*(?:\.\d{2})$|^-?\d+(?:\.\d{2})$")

def first_money(s: str) -> str:
    """Extract first valid money amount from string"""
    if not s:
        return ""
    for tok in s.replace("?","").split():
        tok = tok.strip().replace(",", ",")
        if MONEY_RE.match(tok):
            return tok
    return ""

# Split decimal detection
MONEY_FULL_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})*(?:\.\d{2})$|^-?\d+(?:\.\d{2})$")
PARTIAL_DOT_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})*\.$|^-?\d+\.$")
DEC_TAIL_RE = re.compile(r"^\d{1,2}$")

def _try_merge_split_decimal(base: str, tail: str):
    base = (base or "").strip()
    tail = (tail or "").strip()
    if not base or not tail:
        return None
    if PARTIAL_DOT_RE.match(base) and DEC_TAIL_RE.match(tail):
        merged = base + tail
        if MONEY_FULL_RE.match(merged):
            return merged
    return None
def is_txn_start(row: dict) -> bool:
    """Check if row starts with a valid transaction date"""
    return parse_date_smart(row.get("date")) is not None

def is_noise_row(row: dict) -> bool:
    """Check if row is Account Summary/totals block"""
    text = " ".join([
        row.get("description","") or "",
        row.get("reference","") or "",
    ]).upper()

    return any(k in text for k in [
        "ACCOUNT SUMMARY",
        "OPENING BALANCE",
        "CLOSING BALANCE",
        "TOTAL DEBIT",
        "TOTAL CREDIT",
        "BRANCH:",
        "PERIOD",
        "CURRENCY",
    ])

def extract_transactions(pdf_path: str, bank_identifier: str = "auto") -> Tuple[List[Dict], Dict[str, Any]]:
    """
    Main extraction function with improved accuracy
    
    Args:
        pdf_path: Path to PDF file
        bank_identifier: Bank identifier for bank-specific parsing
                        ('auto', 'gtbank', 'accessbank', 'firstbank', 'zenith', 'uba')
    
    Returns: (transactions, metadata)
    """
    all_rows: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {
        "account_name": None,
        "statement_period": None,
        "statement_total_debit": None,
        "statement_total_credit": None,
        "opening_balance": None,
        "closing_balance": None,
        "bank": bank_identifier
    }
    
    column_debug = {}  # Define in outer scope for metadata access
    
    with pdfplumber.open(pdf_path) as pdf:
        pages_data: List[Tuple[int, List[Dict[str, Any]]]] = []

        # --- 1) Parse metadata from page 1 text (important for validation) ---
        first_text = pdf.pages[0].extract_text() or ""
        metadata.update(parse_statement_metadata(first_text))

        # --- 2) Auto-detect bank if not specified ---
        if bank_identifier == "auto":
            first_text = pdf.pages[0].extract_text() or ""
            if "ECOBANK" in first_text.upper():
                bank_identifier = "ecobank"
            elif "UBA" in first_text.upper() or "UNITED BANK" in first_text.upper():
                bank_identifier = "uba"
            elif "GUARANTY TRUST" in first_text.upper() or "GTBANK" in first_text.upper():
                bank_identifier = "gtbank"
            elif "ZENITH" in first_text.upper():
                bank_identifier = "zenith"
            elif "FIRST BANK" in first_text.upper() or "FIRSTBANK" in first_text.upper():
                bank_identifier = "firstbank"
            elif "WEMA" in first_text.upper():
                bank_identifier = "wema"
            elif "FCMB" in first_text.upper() or "FIRST CITY" in first_text.upper():
                bank_identifier = "fcmb"
            else:
                bank_identifier = "gtbank"  # Default to GTBank
            print(f"DEBUG: Auto-detected bank: {bank_identifier}")
        
    # --- 0a) Special Case: Access Bank Deterministic Global Layout Consensus
    if bank_identifier == "accessbank":
        try:
             return extract_access_consensus(Path(pdf_path), metadata)
        except Exception as e:
             print(f"DEBUG: Access Bank consensus engine failed: {e}. Triggering Hybrid AI Fallback...")
             if GEMINI_AVAILABLE and os.getenv("GEMINI_API_KEY"):
                 txns = extract_transactions_via_ai(str(pdf_path))
                 if txns: return txns, metadata

    # --- 0b) Special Case: Zenith Table Strategy
    if bank_identifier == "zenith":
        try:
             # Try table strategy first
             zenith_txns = extract_zenith_via_tables(Path(pdf_path), metadata)
             if zenith_txns:
                 return zenith_txns, metadata
        except Exception as e:
             print(f"DEBUG: Zenith table strategy failed: {e}. Trying Hybrid AI Fallback...")
             if GEMINI_AVAILABLE and os.getenv("GEMINI_API_KEY"):
                 txns = extract_transactions_via_ai(str(pdf_path))
                 if txns: return txns, metadata

    # --- 0c) Special Case: Ecobank Dedicated Extractor
    if bank_identifier == "ecobank":
        try:
             eco_txns = extract_ecobank_via_tables(Path(pdf_path), metadata)
             if eco_txns:
                 return eco_txns, metadata
        except Exception as e:
             print(f"DEBUG: Ecobank table strategy failed: {e}. Trying Hybrid AI Fallback...")
             if GEMINI_AVAILABLE and os.getenv("GEMINI_API_KEY"):
                 txns = extract_transactions_via_ai(str(pdf_path))
                 if txns: return txns, metadata

    # --- 0d) Special Case: FCMB Table Strategy
    if bank_identifier == "fcmb":
        try:
             fcmb_txns = extract_fcmb_via_tables(Path(pdf_path), metadata)
             if fcmb_txns:
                 return fcmb_txns, metadata
        except Exception as e:
             print(f"DEBUG: FCMB table strategy failed: {e}. Trying Hybrid AI Fallback...")
             if GEMINI_AVAILABLE and os.getenv("GEMINI_API_KEY"):
                 txns = extract_transactions_via_ai(str(pdf_path))
                 if txns: return txns, metadata

    # Reset metadata["_debug"] if fallback is used
    column_debug = {}
    
    with pdfplumber.open(pdf_path) as pdf:
        # --- 1) Scan all pages to detect header and column positions ---
        base_cuts = None
        for i, p in enumerate(pdf.pages):
            words = []
            try:
                words = p.extract_words(x_tolerance=2, y_tolerance=2)
                print(f"DEBUG: Page {i} words count: {len(words)}")
            except Exception as e:
                print(f"DEBUG: Page {i} pdfplumber extraction crashed ({type(e).__name__}: {e}), trying OCR...")
                continue
            
            if not words:
                print(f"DEBUG: Page {i} has no words, skipping...")
                continue
            
            base_cuts = detect_column_cuts_from_header(words, bank_identifier)
            print(f"DEBUG: Generic detect result: {base_cuts}")
            
            # Try specific bank detectors if generic failed or for robust override
            if not base_cuts:
                print(f"DEBUG: Trying specific detector for {bank_identifier}")
                if bank_identifier == "uba":
                    base_cuts = detect_uba_columns(words, bank_identifier)
                elif bank_identifier == "accessbank":
                    base_cuts = detect_access_columns(words, bank_identifier)
                elif bank_identifier == "fidelity":
                    base_cuts = detect_fidelity_columns(words, bank_identifier)
                elif bank_identifier == "apt_securities":
                     base_cuts = detect_apt_columns(words, bank_identifier)

            if base_cuts:
                print(f"DEBUG: Header detected on page {i+1}")
                print(f"DEBUG: FOUND CUTS: {base_cuts}")
                break
                
        # --- OCR Fallback: Try if standard detection completely failed ---
        if not base_cuts:
            print(f"DEBUG: Standard detection failed on all pages. Trying Gemini Multimodal fallback...")
            
            if GEMINI_AVAILABLE and os.getenv("GEMINI_API_KEY"):
                try:
                    transactions = extract_transactions_via_ai(str(pdf_path))
                    if transactions:
                         print(f"DEBUG: Gemini Multimodal extracted {len(transactions)} txns")
                         return transactions, {}
                except Exception as e:
                    print(f"DEBUG: Gemini Multimodal fallback failed: {e}")

            # Legacy OCR fallback as last resort
            print(f"DEBUG: Falling back to legacy OCR engine (Engine: {os.getenv('OCR_ENGINE', 'openai')})...")
            if not OCR_MODULE_AVAILABLE:
                 raise ValueError("Could not detect column header and Gemini Multimodal is not available.")

            try:
                ocr_text = ""
                # Try first 2 pages
                for i in range(min(2, len(pdf.pages))):
                    print(f"DEBUG: Attempting OCR on page {i}...")
                    ocr_text += "\n" + extract_text_with_ocr(str(pdf_path), i)
                
                if bank_identifier == "uba":
                    transactions = parse_uba_ocr_text(ocr_text)
                    if transactions: return transactions, {}

                raise ValueError(
                    f"Header not detected by pdfplumber. Legacy OCR ({os.getenv('OCR_ENGINE', 'openai')}) used as fail-safe, "
                    "but parsing failed. Please use text-based PDFs or check Gemini API connectivity."
                )
            except Exception as e:
                print(f"DEBUG: Legacy OCR fallback failed: {e}")
                raise ValueError(f"Could not detect column header after scanning all pages. AI and Legacy OCR also failed: {e}")
        
        # DEBUG: Store column info for debugging
        column_debug = {col: f"{bounds[0]:.1f} to {bounds[1]:.1f}" for col, bounds in base_cuts.items()}
        print(f"DEBUG: Detected columns: {column_debug}")

        # --- 3) Extract all pages using the same fixed column cuts ---
        for page_num, page in enumerate(pdf.pages, start=1):
            # Wrap in try-except to prevent one bad page from crashing entire analysis
            try:
                words = page.extract_words(x_tolerance=2, y_tolerance=2)
            except Exception as e:
                print(f"DEBUG: pdfplumber failed on page {page_num}: {type(e).__name__}: {e}")
                words = []
            
            if not words:
                print(f"DEBUG: Page {page_num} has no words, skipping...")
                continue

            row_groups = group_words_to_rows(words, y_tol=2.5)

            for rg in row_groups:
                line_text = " ".join([w["text"] for w in rg["words"]]).lower()

                # skip obvious header/footer noise
                if "computer generated" in line_text or "customer information" in line_text:
                    continue
                # Skip the TABLE HEADER row only (exact words, not "transfer")
                header_like = (
                    re.search(r"\btrans\.?\b|\btransaction\b", line_text, re.I)
                    and re.search(r"\bdebits?\b|\bdebit\b|\bwithdrawal\b", line_text, re.I)
                    and re.search(r"\bcredits?\b|\bcredit\b|\bdeposit\b", line_text, re.I)
                    and re.search(r"\bbalance\b", line_text, re.I)
                )
                if header_like:
                    continue

                row = assign_row_to_cols(rg["words"], base_cuts)
                
                # CRITICAL: Skip Account Summary / totals blocks
                if is_noise_row(row):
                    print(f"DEBUG: Skipped noise row: {row}")
                    continue
                
                # DON'T parse money strictly here - split decimals need merging first!
                # row["Debit"] = first_money(row.get("Debit","") or row.get("Debits","") or row.get("Withdrawal",""))
                # row["Credit"] = first_money(row.get("Credit","") or row.get("Credits","") or row.get("Deposit",""))
                # row["Balance"] = first_money(row.get("Balance",""))
                
                # Keep numeric-only continuation rows (e.g. split decimals like "13")
                def has_any_text(row: dict) -> bool:
                    for v in row.values():
                        if isinstance(v, str) and v.strip():
                            return True
                    return False

                def has_decimal_tail(row: dict) -> bool:
                    # if any field contains a standalone 1–2 digit token, keep it for merge logic
                    for k, v in row.items():
                        if not isinstance(v, str):
                            continue
                        if re.fullmatch(r"\d{1,2}", v.strip()):
                            return True
                    return False

                if not has_any_text(row) and not has_decimal_tail(row):
                    continue
                
                # Debug: log when we keep a tail row
                if any(isinstance(v, str) and re.fullmatch(r"\d{1,2}", v.strip()) for v in row.values()):
                    print(f"DEBUG: kept tail row page {page_num}: {row}")

                row["_page"] = page_num
                all_rows.append(row)

    print(f"DEBUG: Total rows before merge: {len(all_rows)}")
    
    # --- 4) Merge multiline rows into clean transactions ---
    transactions = merge_multiline_rows(all_rows)
    
    print(f"DEBUG: Total transactions after merge: {len(transactions)}")
    
    # --- 4) Repair field mixing (GTBank-specific cleanup) ---
    transactions = repair_fields_batch(transactions)

    # --- 7) Convert to final format with numeric values ---
    # First, sort by statement order (page, row) - DON'T sort by category or date later!
    transactions.sort(key=lambda t: (t.get("_page", 0), t.get("_row", 0)))
    
    final_transactions = []
    for txn in transactions:
        # Build description for categorization (combine all text fields)
        desc_parts = []
        if txn.get("reference"):
            desc_parts.append(txn["reference"])
        if txn.get("branch"):
            desc_parts.append(txn["branch"])
        if txn.get("description"):
            desc_parts.append(txn["description"])
        description = " ".join(desc_parts).strip()
        
        # Parse amounts
        deb_val = parse_money(txn.get("debit", ""))
        cred_val = parse_money(txn.get("credit", ""))
        
        # USER REQUEST: Filter non-zero transactions (especially for Access Bank logic)
        # We skip rows where BOTH debit and credit are 0.0, unless it's a specific balance-only row we want to keep?
        # Standard bank behavior is to only show transactions with movement.
        if deb_val == 0.0 and cred_val == 0.0:
            continue

        # Keep fields SEPARATE for Excel, but include description for categorization
        final_transactions.append({
            "date": txn["date"],
            "value_date": txn.get("value_date", ""),
            "reference": txn.get("reference", ""),
            "originating_branch": txn.get("branch", ""),  # Note: internally "branch", externally "originating_branch"
            "remarks": txn.get("description", ""), # Use description for remarks here
            "description": description,  # For categorization only
            "debit": deb_val,
            "credit": cred_val,
            "balance": parse_money(txn.get("balance", "")),
            "category": "Unallocated",
            "is_reversal": False,
            "_page": txn.get("_page"),
            "_row": txn.get("_row")
        })
    
    # Add debug info to metadata
    metadata["_debug"] = {
        "columns_detected": column_debug,
        "first_3_transactions": [
            {
                "date": t.get("date"),
                "debit": t.get("debit"),
                "credit": t.get("credit"),
                "reference": t.get("reference", "")[:20],
                "branch": t.get("originating_branch", "")[:20],
                "remarks": t.get("remarks", "")[:30]
            }
            for t in final_transactions[:3]
        ]
    }
    
    return final_transactions, metadata


def build_description(tx: dict) -> str:
    """
    Build structured transaction description from reference, branch, and description
    """
    ref = (tx.get("reference") or "").strip()
    branch = (tx.get("branch") or "").strip()
    rem = (tx.get("description") or "").strip()

    # Ignore placeholder references
    if ref in {"", "'", "'GAP", "GAP"}:
        ref = ""

    parts = []
    if ref:
        parts.append(ref)
    if branch and branch not in rem:
        parts.append(branch)
    if rem:
        parts.append(rem)

    return " ".join(parts).strip()


def repair_ref_branch_remarks(tx: dict) -> dict:
    """
    Repair column mixing between reference, branch, and description (GTBank-specific)
    """
    ref = (tx.get("reference") or "").strip()
    br = (tx.get("branch") or "").strip()
    rm = (tx.get("description") or "").strip()

    # 1) If branch is at the start of description, move it out
    m = BRANCH_PREFIX.match(rm)
    if m and (not br or not BRANCH_LIKE.match(br)):
        br = m.group(1).strip()
        rm = m.group(2).strip()

    # 2) If reference accidentally contains branch, move branch out
    if BRANCH_LIKE.match(ref) and not br:
        br, ref = ref, ""

    # 3) If description starts with a reference token and ref is empty/placeholder, extract it
    first = rm.split()[0] if rm else ""
    if (not ref or ref in {"'", "GAP", "'GAP"}) and first and looks_like_ref(first):
        ref = first
        rm = rm[len(first):].strip()

    # 4) If ref contains multiple tokens, keep first as ref, push rest into description
    if ref and " " in ref:
        parts = ref.split()
        ref = parts[0]
        spill = " ".join(parts[1:]).strip()
        if spill:
            rm = (spill + " " + rm).strip()
    
    # 5) Clean placeholder references
    if ref in {"'", "GAP", "'GAP"}:
        ref = ""

    tx["reference"] = ref
    tx["branch"] = br
    tx["description"] = rm
    return tx


def repair_fields_batch(transactions: List[Dict]) -> List[Dict]:
    """Apply repair_ref_branch_remarks to all transactions"""
    return [repair_ref_branch_remarks(tx) for tx in transactions]


def parse_statement_metadata(text: str) -> Dict[str, Any]:
    """
    Minimal metadata parser (for validation)
    """
    def find_money(pat):
        m = re.search(pat, text, re.I | re.MULTILINE)
        if not m: 
            return None
        return float(m.group(1).replace(",", ""))

    meta = {}
    
    # GTBank format: Account name is usually before "Trans. Date" header
    # GTBank format: Account name is usually before "Trans. Date" header
    m = re.search(r"CUSTOMER STATEMENT\s*([\s\S]*?)\s*Trans\.\s*Date", text, re.I)
    if not m:
        # Alternative: look for account name pattern
        m = re.search(r"(?:Account Name|Name)[:\s]*(.*?)(?:\n|$)", text, re.I)
    if m:
        raw_name = m.group(1)
        # Clean up: stop at "Total Debit" or "Total Credit" or "Currency", "Account No", or a bare date keyword
        stop_patterns = ["TOTAL DEBIT", "TOTAL CREDIT", "CURRENCY", "ACCOUNT NO", "ACC NO", " DATE ", "\nDATE"]
        upper_raw = raw_name.upper()
        
        min_idx = len(raw_name)
        for p in stop_patterns:
            # Use regex to find pattern with variable spaces
            pm = re.search(re.escape(p).replace(r"\ ", r"\s+"), upper_raw)
            if pm:
                idx = pm.start()
                if idx < min_idx:
                     min_idx = idx
        
        cleaned_name = raw_name[:min_idx].strip()
        # Remove trailing punctuation
        cleaned_name = cleaned_name.rstrip(":,.-")
        
        meta["account_name"] = " ".join([x.strip() for x in cleaned_name.splitlines() if x.strip()])

    # Statement period
    m = re.search(r"Statement Period\s*[:\s]*([\d\-A-Za-z\s]+to[\d\-A-Za-z\s]+)", text, re.I)
    if m:
        meta["statement_period"] = m.group(1).strip()

    # Try various patterns for totals
    # Pattern 1: "Total Debit 1,234,567.89"
    meta["statement_total_debit"] = (
        find_money(r"Total\s+Debit[:\s]*([\d,]+\.\d{2})") or
        find_money(r"Debit\s+Total[:\s]*([\d,]+\.\d{2})") or
        find_money(r"Total\s+Withdrawals?[:\s]*([\d,]+\.\d{2})")
    )
    
    meta["statement_total_credit"] = (
        find_money(r"Total\s+Credit[:\s]*([\d,]+\.\d{2})") or
        find_money(r"Credit\s+Total[:\s]*([\d,]+\.\d{2})") or
        find_money(r"Total\s+Deposits?[:\s]*([\d,]+\.\d{2})")
    )
    
    meta["opening_balance"] = (
        find_money(r"Opening\s+Balance[:\s]*([\d,]+\.\d{2})") or
        find_money(r"Balance\s+(?:Brought|B/F)[:\s]*([\d,]+\.\d{2})")
    )
    
    meta["closing_balance"] = (
        find_money(r"Closing\s+Balance[:\s]*([\d,]+\.\d{2})") or
        find_money(r"Balance\s+(?:Carried|C/F)[:\s]*([\d,]+\.\d{2})")
    )

    return meta





def detect_column_cuts_from_header(words: List[Dict[str, Any]], bank_identifier: str = "gtbank") -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries from the header row (routes to bank-specific logic)
    """
    if bank_identifier == "ecobank":
        return detect_ecobank_columns(words)
    elif bank_identifier == "zenith":
        return detect_zenith_columns(words)
    else:
        return detect_gtbank_columns(words)


def detect_zenith_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for Zenith Bank
    Common Headers: DATE | NARRATION | VALUE DATE | DEBIT | CREDIT | BALANCE
    Handles split words like ["DATE", "POSTED"] and ["VALUE", "DATE"]
    """
    if not words:
        return None

    # Loose keywords to identifying the header row
    # We look for the row having the most of these
    keywords = ["DATE", "POSTED", "VALUE", "NARRATION", "DESCRIPTION", "DEBIT", "CREDIT", "BALANCE"]
    
    rows = group_words_to_rows(words, y_tol=4.0) # Slightly higher tol
    
    best_row = None
    max_score = 0
    
    for r in rows:
        score = 0
        row_text_upper = " ".join([w["text"].upper() for w in r["words"]])
        
        # Must definitely contain DATE and (DEBIT or CREDIT or BALANCE)
        if "DATE" not in row_text_upper: continue
        if not any(x in row_text_upper for x in ["DEBIT", "CREDIT", "BALANCE"]): continue
        
        for w in r["words"]:
            if w["text"].upper() in keywords:
                score += 1
        
        # Bonus for exact phrases
        if "DATE POSTED" in row_text_upper: score += 2
        if "VALUE DATE" in row_text_upper: score += 2
        if "DESCRIPTION" in row_text_upper: score += 2

        if score > max_score:
            max_score = score
            best_row = r

    if not best_row or max_score < 3:
        return None

    print(f"DEBUG: Found Zenith Header Row: {[w['text'] for w in best_row['words']]}")

    # Now extracting x-coordinates for specific columns
    # We iterate words left-to-right to find anchors
    
    sorted_words = sorted(best_row["words"], key=lambda w: w["x0"])
    
    bounds = {}
    
    # helper: find word containing text (approximate)
    def find_word_x(text_part, start_idx=0):
        for i in range(start_idx, len(sorted_words)):
            if text_part in sorted_words[i]["text"].upper():
                return i, sorted_words[i]
        return -1, None

    # 1. date (DATE POSTED or just DATE at start)
    # Usually the first "DATE"
    idx_td, w_td = find_word_x("DATE")
    if w_td: 
        bounds["date"] = (w_td["x0"], w_td["x1"])
    
    # 2. value_date (Look for "VALUE")
    idx_vd, w_vd = find_word_x("VALUE")
    if w_vd:
        bounds["value_date"] = (w_vd["x0"], w_vd["x1"])

    # 3. description (NARRATION / DESCRIPTION)
    idx_rem, w_rem = find_word_x("NARRATION")
    if not w_rem: idx_rem, w_rem = find_word_x("DESCRIPTION")
    if not w_rem: idx_rem, w_rem = find_word_x("PARTICULARS")
    if w_rem: bounds["description"] = (w_rem["x0"], w_rem["x1"])

    # 4. debit/credit/balance
    for col in ["DEBIT", "CREDIT", "BALANCE"]:
        idx, w = find_word_x(col)
        # Handle "DR" or "CR"
        if not w and col == "DEBIT": idx, w = find_word_x("DR")
        if not w and col == "CREDIT": idx, w = find_word_x("CR")
        if not w and col == "BALANCE": idx, w = find_word_x("BAL")
        
        if w:
            bounds[col.lower()] = (w["x0"], w["x1"])

    # Mandatory check
    if "date" not in bounds or "debit" not in bounds:
        return None

    # Sort columns by X position
    sorted_cols = sorted(bounds.items(), key=lambda item: item[1][0])
    
    cuts = {}
    for i in range(len(sorted_cols)):
        col_name, (l, r) = sorted_cols[i]
        
        # Start
        if i == 0:
            start = 0.0
        else:
            prev_name, (prev_l, prev_r) = sorted_cols[i-1]
            start = (prev_r + l) / 2
            
        # End
        if i == len(sorted_cols) - 1:
            end = 1000.0
        else:
            next_name, (next_l, next_r) = sorted_cols[i+1]
            end = (r + next_l) / 2
            
        cuts[col_name] = (start, end)
        
    return cuts


def detect_ecobank_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Robust Ecobank column detection.
    Only locks onto the true table header (not Account Summary).
    Uses right/left edges to form safer boundaries for right-aligned numeric columns.
    """
    if not words:
        return None

    # --- 1) Find a header band that contains MANY header tokens together ---
    header_terms = {
        "date": r"(?:Trans(?:action)?\s*Date|Trans\.?\s*Date|Trn\s*Date|Date\b)",
        "value_date": r"(?:Value\s*Date|Val\s*Date)",
        "description": r"(?:Description|Narration|Remarks?|Details|Particulars)",
        "debit": r"(?:Debit|Withdrawal|Dr\b)",
        "credit": r"(?:Credit|Deposit|Cr\b)",
        "balance": r"(?:Balance|Bal\b)"
    }

    # collect candidate tops where any header term appears
    tops = [w["top"] for w in words if any(re.search(rx, w["text"], re.I) for rx in header_terms.values())]
    if not tops:
        return None

    # group by approximate top and score each band by how many distinct header fields it contains
    # (this rejects "Total Credit" alone)
    candidate_tops = sorted(set(round(t, 1) for t in tops))

    best = None  # (score, top, header_words)
    for t in candidate_tops:
        band = (t - 6, t + 6)
        hw = [w for w in words if band[0] <= w["top"] <= band[1]]

        found = set()
        for key, rx in header_terms.items():
            if any(re.search(rx, w["text"], re.I) for w in hw):
                found.add(key)

        score = len(found)

        # require at least 4 columns present to be considered a real table header
        if score >= 4:
            # also reject obvious summary bands
            band_text = " ".join(w["text"] for w in hw).upper()
            if "ACCOUNT SUMMARY" in band_text or "TOTAL CREDIT" in band_text or "TOTAL DEBIT" in band_text:
                continue

            if best is None or score > best[0]:
                best = (score, t, hw)

    if not best:
        return None

    _, header_top, header_words = best

    # --- 2) Find header label positions using BOTH left and right edges ---
    def find_left(rx: str):
        xs = [w["x0"] for w in header_words if re.search(rx, w["text"], re.I)]
        return min(xs) if xs else None

    def find_right(rx: str):
        xs = [w["x1"] for w in header_words if re.search(rx, w["text"], re.I)]
        return max(xs) if xs else None

    # anchor points
    # Detect Value Date FIRST to constrain TransDate
    x_value_l = find_left(header_terms["value_date"])
    x_value_r = find_right(header_terms["value_date"])

    # Detect TransDate, but exclude matches that overlap ValueDate
    # (Because regex "Date" matches "Value Date")
    trans_words = [w for w in header_words if re.search(header_terms["date"], w["text"], re.I)]
    
    # Filter out words that belong to Value Date column (if detected)
    if x_value_l is not None:
        # Keep words significantly to the left of Value Date
        trans_words = [w for w in trans_words if w["x1"] < x_value_l + 5]
        
    x_trans_l = min([w["x0"] for w in trans_words]) if trans_words else None
    x_trans_r = max([w["x1"] for w in trans_words]) if trans_words else None
    
    print("DEBUG: Entering detect_ecobank_columns")
    
    # HEURISTIC: Fix Value Date masquerading as Trans Date
    # If TransDate is detected too far right (> 200), it's likely Value Date.
    if x_trans_l is not None and x_trans_l > 200:
        print(f"DEBUG: TransDate detected late at {x_trans_l}. Check if it is actually ValueDate.")
        if x_value_l is None:
            # We found 'Date' at 200+ (which is usually Value Date), but didn't find specific Value Date header.
            # Convert it to Value Date.
            print("DEBUG: Promoting late TransDate to ValueDate and checking for missing TransDate.")
            x_value_l = x_trans_l
            x_value_r = x_trans_r
            
            # Now look for a leftmost Date word at < 150
            # If not found, inject placeholder
            left_candidates = [w for w in header_words if w["x0"] < 150 and re.search(r"Date", w["text"], re.I)]
            if left_candidates:
                x_trans_l = min(w["x0"] for w in left_candidates)
                x_trans_r = max(w["x1"] for w in left_candidates)
                print(f"DEBUG: Found real TransDate candidate at {x_trans_l}")
            else:
                x_trans_l = 40.0
                x_trans_r = 120.0
                print("DEBUG: Injected placeholder TransDate at 40.0-120.0")

    if x_trans_l is not None and x_trans_r is not None:
        print(f"DEBUG: TransDate raw width: {x_trans_r} - {x_trans_l} = {x_trans_r - x_trans_l}")
    
    # HEURISTIC: Clamp wide TransDate.
    if x_trans_l is not None and x_trans_r is not None and (x_trans_r - x_trans_l > 100):
        print(f"DEBUG: Clamping wide TransDate ({x_trans_r - x_trans_l:.1f}pts) to 130pts")
        x_trans_r = x_trans_l + 130

    x_desc_l  = find_left(header_terms["description"])
    x_desc_r  = find_right(header_terms["description"])

    x_deb_l   = find_left(header_terms["debit"])
    x_deb_r   = find_right(header_terms["debit"])

    x_cred_l  = find_left(header_terms["credit"])
    x_cred_r  = find_right(header_terms["credit"])

    x_bal_l   = find_left(header_terms["balance"])
    x_bal_r   = find_right(header_terms["balance"])

    # require core columns
    if any(v is None for v in [x_trans_l, x_desc_l, x_deb_l, x_cred_l, x_bal_l]):
        return None

    cols = []
    cols.append(("date", x_trans_l, x_trans_r))
    cols.append(("description", x_desc_l, x_desc_r))
    if x_value_l is not None:
        cols.append(("value_date", x_value_l, x_value_r))
    cols.append(("debit", x_deb_l, x_deb_r))
    cols.append(("credit", x_cred_l, x_cred_r))
    cols.append(("balance", x_bal_l, x_bal_r))

    cols.sort(key=lambda c: c[1])  # sort by left edge

    # --- 3) Build safer boundaries using midpoint with smart shifting ---
    # We define cut points *between* columns.
    cut_points = []
    for i in range(len(cols) - 1):
        c1 = cols[i]
        c2 = cols[i+1]
        name1, l1, r1 = c1
        name2, l2, r2 = c2
        
        # Start with standard midpoint
        mid = (r1 + l2) / 2
        
        # ADJUSTMENTS based on known Ecobank layout quirks:
        # 1. "Transaction Date" header is very wide, but data (dd-mmm-yyyy) is narrow.
        #    "Debit/Withdrawal" header is narrow, but data can be wide.
        #    Shift boundary LEFT to give Debit more space.
        # 1. "TransDate" -> "Debit"
        if name1 == "date" and name2 == "debit":
            proposed_cut = r1 - 25
            if (proposed_cut - l1) < 20:
                 proposed_cut = l1 + 20
            mid = proposed_cut
        elif name1 == "description" and name2 == "date":
            l2_effective = l2 - 30
            mid = (r1 + l2_effective) / 2

        cut_points.append(mid)

    cuts: Dict[str, Tuple[float, float]] = {}
    for i, (name, l, r) in enumerate(cols):
        left_bound = cut_points[i-1] if i > 0 else -math.inf
        right_bound = cut_points[i] if i < len(cut_points) else math.inf
        cuts[name] = (left_bound, right_bound)

    print("DEBUG: ECOBANK HEADER TOP:", header_top)
    print("DEBUG: ECOBANK CUTS:", {k: (round(v[0],1), round(v[1],1)) for k,v in cuts.items()})
    return cuts


def detect_access_columns(words: List[Dict], bank_identifier: str) -> Dict[str, Tuple[float, float]] | None:
    """Access Bank: Date | Transaction Details | Reference | Value Date | Withdrawals | Lodgements | Balance"""
    if bank_identifier != "accessbank": return None
    
    # 1. Gather x-coordinates of known headers
    def find_x(regex):
        matches = [w for w in words if re.search(regex, w["text"], re.I)]
        return min([w["x0"] for w in matches]) if matches else None

    # Right-aligned columns need right edge
    def find_x_right(regex):
        matches = [w for w in words if re.search(regex, w["text"], re.I)]
        return max([w["x1"] for w in matches]) if matches else None

    x_date = find_x(r"Date")
    x_details = find_x(r"Details|Narration|Description|Particulars")
    x_ref = find_x(r"Ref|Chq")
    x_val = find_x(r"Value")
    x_with = find_x_right(r"Withdraw|Debit|Dr\b")
    x_lodge = find_x_right(r"Lodg|Deposit|Credit|Cr\b")
    x_bal = find_x_right(r"Balance|Bal\b")

    if not all([x_date, x_details, x_with, x_lodge, x_bal]):
        print(f"DEBUG: ACCESS DETECT FAILED. Found: date={x_date}, det={x_details}, with={x_with}, lodge={x_lodge}, bal={x_bal}")
        return None

    # 2. Build cuts directly
    # Date | Details | Ref | Value | With | Lodge | Bal
    cuts = {}
    
    # Date: 0 to Details
    cuts["date"] = (0, x_details - 5)
    
    # Details: Date to Ref (or Value if Ref missing)
    next_col = x_ref if x_ref else x_val
    cuts["description"] = (x_details - 5, next_col - 5)
    
    # Reference
    if x_ref and x_val:
        cuts["reference"] = (x_ref - 5, x_val - 5)
    elif x_ref:
        cuts["reference"] = (x_ref - 5, x_with - 50) # Fallback

    # Value Date
    if x_val:
        cuts["value_date"] = (x_val - 5, x_with - 10)

    # Withdrawals (Debit)
    cuts["debit"] = (x_with - 80, x_with + 5)
    
    # Lodgements (Credit)
    cuts["credit"] = (x_lodge - 80, x_lodge + 5)
    
    # Balance
    cuts["balance"] = (x_bal - 80, x_bal + 5)

    print(f"DEBUG: ACCESS columns: {cuts.keys()}")
    return cuts

def detect_fidelity_columns(words: List[Dict], bank_identifier: str) -> Dict[str, Tuple[float, float]] | None:
    """Fidelity: Transaction Date | Value Date | Channel | Details | Pay In | Pay Out | Balance"""
    if bank_identifier != "fidelity": return None
    
    # Fidelity headers are often distinct
    def find_col(regex):
        ms = [w for w in words if re.search(regex, w.get("text", ""), re.I)]
        if not ms: return None
        # Sort by x0 just in case
        ms.sort(key=lambda w: w.get("x0", 0))
        return ms[0] if ms else None

    trans_date = find_col(r"Transaction")
    val_date = find_col(r"Value")
    channel = find_col(r"Channel")
    details = find_col(r"Details")
    pay_in = find_col(r"Pay\s*In")
    pay_out = find_col(r"Pay\s*Out")
    bal = find_col(r"Balance")

    if not (trans_date and details and (pay_in or pay_out) and bal):
        print(f"DEBUG: FIDELITY detection failed - missing required columns")
        return None

    cols = []
    cols.append(("date", trans_date.get("x0", 0)))
    if val_date: cols.append(("value_date", val_date.get("x0", 0)))
    if channel: cols.append(("channel", channel.get("x0", 0)))
    cols.append(("description", details.get("x0", 0)))
    
    if pay_in: cols.append(("credit", pay_in.get("x0", 0)))
    if pay_out: cols.append(("debit", pay_out.get("x0", 0)))
    cols.append(("balance", bal.get("x0", 0)))

    cols.sort(key=lambda x: x[1])
    
    cuts = {}
    for i in range(len(cols)):
        name, left = cols[i]
        # Right edge is next col's left or strict width
        if i < len(cols) - 1:
            right = cols[i+1][1]
        else:
            right = 1000 # End of page
            
        cuts[name] = (left - 5, right - 5)
    
    print(f"DEBUG: FIDELITY columns: {cuts.keys()}")
    return cuts

def detect_apt_columns(words: List[Dict], bank_identifier: str) -> Dict[str, Tuple[float, float]] | None:
    """APT: Txn Date | ValueDate | GL Description | [Blank] | Debit | Credit | Balance"""
    if bank_identifier != "apt_securities": return None
    
    # Find headers
    # Txn Date
    txn = [w for w in words if "Txn" in w["text"] or "Date" in w["text"]]
    
    # GL Description
    gl = [w for w in words if "GL" in w["text"] or "Description" in w["text"]]
    
    # Debit/Credit/Balance
    deb = [w for w in words if "Debit" in w["text"]]
    cred = [w for w in words if "Credit" in w["text"]]
    bal = [w for w in words if "Balance" in w["text"]]
    
    if not (txn and gl and deb and cred and bal):
        return None
        
    # Use right-edge alignment for numbers
    x_deb = max(w["x1"] for w in deb)
    x_cred = max(w["x1"] for w in cred)
    x_bal = max(w["x1"] for w in bal)
    
    x_txn = min(w["x0"] for w in txn)
    x_gl = min(w["x0"] for w in gl)
    
    cuts = {}
    cuts["date"] = (0, x_gl - 10) 
    cuts["description"] = (x_gl - 10, x_deb - 100) 
    
    cuts["debit"] = (x_deb - 80, x_deb + 5)
    cuts["credit"] = (x_cred - 80, x_cred + 5)
    cuts["balance"] = (x_bal - 80, x_bal + 5)

    print(f"DEBUG: APT columns: {cuts.keys()}")
    return cuts





def detect_gtbank_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for GTBank from the header row.
    """
    if not words:
        return None

    # find header band by locating tokens like Debit/Credit/Balance/Trans
    header_candidates = [w["top"] for w in words if re.search(r"(Trans|Value|Debit|Credit|Balance|Remarks|Refer|Particulars|Details|Branch|Originat)", w["text"], re.I)]
    if not header_candidates:
        return None

    # pick the most common top band
    header_top = sorted(header_candidates)[len(header_candidates)//2]
    band = (header_top - 6, header_top + 6)
    header_words = [w for w in words if band[0] <= w["top"] <= band[1]]

    def find_x(regex: str):
        """Find left edge (x0) for left-aligned columns"""
        xs = [w["x0"] for w in header_words if re.search(regex, w["text"], re.I)]
        return min(xs) if xs else None
    
    def find_x_right(regex: str):
        """Find right edge (x1) for right-aligned numeric columns"""
        xs = [w["x1"] for w in header_words if re.search(regex, w["text"], re.I)]
        return max(xs) if xs else None

    # Left-aligned columns - use left edge
    x_trans = find_x(r"Trans")
    x_value = find_x(r"Value")
    x_ref   = find_x(r"Refer")
    
    # Right-aligned numeric columns - use right edge for better alignment
    x_deb   = find_x_right(r"Deb")
    x_cred  = find_x_right(r"Cred")
    x_bal   = find_x_right(r"Bal")
    
    # Other columns
    x_branch = find_x(r"Originat|Branch")  # Originating Branch column
    x_rem   = find_x(r"Remarks?|Particulars|Details")  # Description column

    if any(v is None for v in [x_trans, x_deb, x_cred, x_bal]):
        return None

    cols = [
        ("date", x_trans),
    ]
    
    if x_value is not None:
        cols.append(("value_date", x_value))
    
    if x_ref is not None:
        cols.append(("reference", x_ref))
    
    cols.extend([
        ("debit", x_deb),
        ("credit", x_cred),
        ("balance", x_bal),
    ])
    
    if x_branch is not None:
        cols.append(("branch", x_branch))
    
    if x_rem is not None:
        cols.append(("description", x_rem))
    elif x_branch is not None:
        cols.append(("description", x_branch + 100))
    elif x_bal is not None:
        cols.append(("description", x_bal + 120))
    
    # CRITICAL: Sort columns by X position to ensure correct left-to-right order
    # This prevents column boundary overlap
    cols = sorted(cols, key=lambda x: x[1])
    
    print(f"DEBUG: Column positions: {[(name, f'{x:.1f}') for name, x in cols]}")

    cuts: Dict[str, Tuple[float, float]] = {}
    for i, (name, x) in enumerate(cols):
        if i == 0:
            # First column: from -inf to midpoint to next column
            cuts[name] = (-math.inf, (x + cols[i+1][1]) / 2)
        elif i == len(cols) - 1:
            # Last column: from midpoint from previous to +inf
            cuts[name] = ((cols[i-1][1] + x) / 2, math.inf)
        else:
            # Middle columns: midpoint from previous to midpoint to next
            cuts[name] = ((cols[i-1][1] + x) / 2, (x + cols[i+1][1]) / 2)
    
    print(f"DEBUG: Column boundaries: {[(name, f'{left:.1f}-{right:.1f}') for name, (left, right) in cuts.items()]}")
    return cuts


def assign_row_to_cols(row_words: List[Dict[str, Any]], cuts: Dict[str, Tuple[float, float]]) -> Dict[str, str]:
    """
    Assign words using Smart Anchoring logic (x0/x1) AND Content-Aware Repair:
    - Text columns (Date, Ref, Desc, Branch) use x0 (Start)
    - Numeric columns use x1 (End)
    - If geometric assignment fails (e.g. bad cuts), content checks move 
      Date/Ref tokens from Remarks back to their correct columns.
    """
    # Create bucket list for each column
    bucket = {k: [] for k in cuts.keys()}
    
    right_aligned_cols = {
        "Debit", "Credit", "Balance", 
        "Withdrawal", "Lodgement", "Lodgements", "Withdrawals",
        "Debits", "Credits", "Pay Out", "Pay In"
    }

    # Ensure words are sorted left-to-right
    row_words = sorted(row_words, key=lambda w: w["x0"])

    # 1. Geometric Assignment
    for w in row_words:
        x0, x1 = w["x0"], w["x1"]
        for col, (l, r) in cuts.items():
            if col in right_aligned_cols:
                ref_point = x1
            else:
                ref_point = x0
            
            if l <= ref_point < r:
                bucket[col].append(w["text"])
                break

    # 2. Content-Aware Repair (Fix mixed columns due to bad cuts)
    
    # Sources of mixed text (Details, Remarks, Narration - standard as 'description')
    source_col = "description"
    
    # REPAIR 1: date mixed into description
    if "date" in bucket and not bucket["date"] and bucket.get(source_col):
        w_text = bucket[source_col][0]
        if is_date(w_text):
            bucket["date"].append(bucket[source_col].pop(0))
            
    # REPAIR 2: reference mixed into description
    if "reference" in bucket and not bucket["reference"] and bucket.get(source_col):
        w_text = bucket[source_col][0]
        if looks_like_ref(w_text) and re.search(r"\d", w_text):
             bucket["reference"].append(bucket[source_col].pop(0))

    # REPAIR 4: Orphan Amount in description (e.g. debit shifted left into description)
    if bucket.get(source_col) and (not bucket.get("debit") or not bucket.get("credit")):
        w_text = bucket[source_col][-1]
        if re.match(r"^-?[\d,]+\.\d{2}$", w_text):
            candidate_word = None
            for w in reversed(row_words):
                if w["text"] == w_text:
                    candidate_word = w
                    break
            
            if candidate_word:
                x1 = candidate_word["x1"]
                if "debit" in cuts and not bucket["debit"]:
                    deb_l, deb_r = cuts["debit"]
                    if deb_l - 30 <= x1 <= deb_r:
                        bucket["debit"].append(bucket[source_col].pop())
                elif "credit" in cuts and not bucket["credit"]:
                    cred_l, cred_r = cuts["credit"]
                    if cred_l - 30 <= x1 <= cred_r:
                        bucket["credit"].append(bucket[source_col].pop())

    # REPAIR 5: Aggressive Numeric Snapping
    for target_col in ["debit", "credit", "balance"]:
        if target_col in cuts and not bucket[target_col]:
            target_center = (cuts[target_col][0] + cuts[target_col][1]) / 2
            if bucket.get(source_col):
                best_word_idx = -1
                min_dist = float('inf')
                for i, w_text in enumerate(bucket[source_col]):
                    if re.match(r"^-?[\d,]+(\.\d+)?$", w_text):
                        cand_w = next((w for w in reversed(row_words) if w["text"] == w_text), None)
                        if cand_w:
                            w_center = (cand_w["x0"] + cand_w["x1"]) / 2
                            dist = abs(w_center - target_center)
                            if dist < 60 and dist < min_dist:
                                min_dist = dist
                                best_word_idx = i
                
                if best_word_idx != -1:
                    bucket[target_col].append(bucket[source_col].pop(best_word_idx))

    # CLEANUP: Remove internal spaces in numeric fields
    for col in ["debit", "credit", "balance"]:
        if col in bucket and bucket[col]:
            full_str = "".join(bucket[col])
            bucket[col] = [full_str.replace(" ", "")]

    return {col: " ".join(vals).strip() for col, vals in bucket.items()}


def group_words_to_rows(words: List[Dict[str, Any]], y_tol: float = 3.0) -> List[Dict[str, Any]]:
    """
    Group words into physical rows (by Y coordinate)
    Tolerance tuned to 3.0 (from 3.5) to avoid merging distinct tight rows
    """
    rows: List[Dict[str, Any]] = []
    for w in sorted(words, key=lambda d: (d["top"], d["x0"])):
        placed = False
        for r in rows:
            if abs(w["top"] - r["top"]) <= y_tol:
                r["words"].append(w)
                r["top"] = (r["top"] + w["top"]) / 2
                placed = True
                break
        if not placed:
            rows.append({"top": w["top"], "words": [w]})
    for r in rows:
        r["words"].sort(key=lambda d: d["x0"])
    return rows


# ... (keep other functions) ...

def merge_multiline_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge multiline transactions using Strict Anchor Logic, Split Decimal Merging,
    and Right-to-Left Fallback logic.
    """
    out: List[Dict[str, Any]] = []
    current = None
    
    def clean_as_float(s):
        if not s: return 0.0
        s = s.replace(" ", "").replace(",", "")
        try: return float(s)
        except: return 0.0

    i = 0
    while i < len(rows):
        r = rows[i]
        
        # Standardized keys
        tdate = (r.get("date") or "").strip()
        ref = (r.get("reference") or "").strip()
        rem = (r.get("description") or "").strip()
        deb = (r.get("debit") or "").strip()
        cred = (r.get("credit") or "").strip()
        bal = (r.get("balance") or "").strip()
        branch = (r.get("branch") or "").strip()
        
        # Access raw text if available
        raw_text = r.get("_raw_text", "")
        if not raw_text:
             raw_text = " ".join([tdate, ref, rem, deb, cred, bal, branch])

        full_line_text = raw_text.upper()
        
        # --- FIX 5: STOP AT CLOSING BALANCE ---
        if "CLOSING BALANCE" in full_line_text:
             break
        if "OPENING BALANCE" in full_line_text:
            i += 1
            continue

        # --- FIX 2: SPLIT DECIMAL MERGE ---
        if i + 1 < len(rows):
            next_r = rows[i+1]
            next_deb = (next_r.get("debit") or "").strip()
            next_cred = (next_r.get("credit") or "").strip()
            next_bal = (next_r.get("balance") or "").strip()
            
            def try_merge_dec(curr_val, next_val):
                if not curr_val or not next_val: return None
                curr_val = curr_val.strip()
                next_val = next_val.strip()
                if curr_val.endswith('.') and re.match(r'^\d{1,2}$', next_val):
                     return curr_val + next_val
                if re.match(r'.*\.\d$', curr_val) and re.match(r'^\d$', next_val):
                     return curr_val + next_val
                return None

            m_d = try_merge_dec(deb, next_deb)
            if m_d: deb = m_d; rows[i+1]["debit"] = ""
            m_c = try_merge_dec(cred, next_cred)
            if m_c: cred = m_c; rows[i+1]["credit"] = ""
            m_b = try_merge_dec(bal, next_bal)
            if m_b: bal = m_b; rows[i+1]["balance"] = ""

        # --- FIX 1: STRICT ANCHOR LOGIC ---
        has_date = bool(parse_date_smart(tdate))
        has_amt = bool(deb or cred)
        has_bal = bool(bal)
        
        # --- FIX 3: RIGHT-TO-LEFT FALLBACK (If date+bal but no amount) ---
        if has_date and has_bal and not has_amt:
             # Try to parse from raw text
             # FIX 1: Relaxed regex for money tokens (no length limit, optional decimals)
             money_tokens = re.findall(r'[\d,]+(?:\.\d+)?', raw_text)
             # Filter out non-money like just "," or "." if any
             money_tokens = [m for m in money_tokens if re.search(r'\d', m)]
             # Heuristic: If we have balance, check last token.
             if len(money_tokens) >= 2:
                 pot_bal = clean_as_float(money_tokens[-1])
                 if abs(pot_bal - clean_as_float(bal)) < 1.0:
                      # Match! Preceeding might be amt
                      pot_amt = clean_as_float(money_tokens[-2])
                      # Simple assignment to Debit for now (Validation will check direction)
                      # Or check if credit column is populated? No it's empty.
                      # Assume Debit default, let Fix 6 resolve if wrong.
                      if not deb and not cred:
                           deb = money_tokens[-2]
                           current_flags = "Repaired (Right-to-Left)"
        
        is_anchor = has_date and (has_amt or has_bal) # Relaxed anchor for Fix 2

        if is_anchor:
            if current:
                out.append(current)
            
            current = {
                "_page": r.get("_page"),
                "_row": r.get("_row"),
                "date": parse_date_smart(tdate),
                "value_date": (r.get("value_date") or "").strip(),
                "reference": ref,
                "debit": deb,
                "credit": cred,
                "balance": bal,
                "description": rem,
                "branch": branch,
                "raw_text": raw_text
            }
        else:
            # Merging logic
            if current:
                desc_dt = parse_date_smart(rem)
                assigned_dt = False
                if desc_dt and not current["value_date"]:
                     current["value_date"] = desc_dt
                     assigned_dt = True
                
                if ref: current["reference"] = (current["reference"] + " " + ref).strip()
                if not assigned_dt and rem: 
                    current["description"] = (current["description"] + " " + rem).strip()
                if branch: current["branch"] = (current["branch"] + " " + branch).strip()
                
        i += 1

    if current:
        out.append(current)

    # --- FIX 14 & 2: FILTER & REPAIR ---
    final_out = []
    for txn in out:
        # If Date+Bal but no Amt, we keep it (Fix 2).
        if txn["date"]:
             final_out.append(txn)
    
    return final_out


def parse_money(text: str) -> float:
    """
    Parse money value, handling brackets as negatives
    """
    if not text or not isinstance(text, str):
        return 0.0
    
    text = text.strip()
    if not text:
        return 0.0
    
    if not re.search(r'[\d\.,]+', text):
        return 0.0
    
    # Check for brackets or minus
    is_negative = bool(re.match(r'^\(.*\)$', text)) or text.startswith('-')
    
    # Remove all non-numeric except dot
    clean = re.sub(r'[^\d\.]', '', text)
    
    try:
        num = float(clean)
        if is_negative:
            num = -num
        return num
    except ValueError:
        return 0.0




def reconcile_transactions(transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    FIX 1: Balance Reconciliation Check
    Expected Balance = Previous Balance - Debit + Credit
    If mismatch, flag it.
    
    FIX 6: Auto-repair (Placeholder logic - requires raw text access which is complex here, 
    but we can at least flag REPAIR_NEEDED).
    """
    if not transactions:
        return []
        
    def clean_amt(x):
        if isinstance(x, (int, float)): return x
        if not x: return 0.0
        return float(str(x).replace(",", "").replace(" ", "") or 0)

    reconciled = []
    
    for i in range(len(transactions)):
        txn = transactions[i]
        reconciled.append(txn)
        
        if i == 0: continue
        
        prev = transactions[i-1]
        
        prev_bal = clean_amt(prev["balance"])
        curr_bal = clean_amt(txn["balance"])
        deb = clean_amt(txn["debit"])
        cred = clean_amt(txn["credit"])
        
        # Calculate expected
        # D/C logic: Bal = Prev - Deb + Cred (assuming credit increases balance)
        expected = prev_bal - deb + cred
        
        # Use simple epsilon check
        if abs(expected - curr_bal) > 0.01:
            txn["reconciliation_error"] = True
            txn["expected_balance"] = expected
            txn["diff"] = curr_bal - expected
            
            # FIX 6: HEURISTIC REPAIR
            if abs(deb) < 0.01 and abs(cred) < 0.01:
                # We have 0 amount but balance changed.
                missing_amt = prev_bal - curr_bal # if positive, it was a debit
                
                if missing_amt > 0.01:
                    txn["debit"] = f"{missing_amt:.2f}"
                    txn["notes"] = "Auto-repaired missing Debit from balance diff"
                    # Clear error
                    del txn["reconciliation_error"]
                elif missing_amt < -0.01:
                    txn["credit"] = f"{abs(missing_amt):.2f}"
                    txn["notes"] = "Auto-repaired missing Credit from balance diff"
                    # Clear error
                    del txn["reconciliation_error"]

    return reconciled


def detect_firstbank_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for First Bank
    Headers: Trans Date | Ref. Number | Transaction Details | Value Date | Withdrawal(DR) | Deposit(CR) | Balance
    """
    if not words:
        return None

    # Keywords to identify header row
    keywords = ["TRANS", "DATE", "REF", "NUMBER", "DETAILS", "VALUE", "WITHDRAWAL", "DEPOSIT", "BALANCE"]
    
    # Zenith/FirstBank often clearer with slightly larger tolerance? Or stick to 3.0?
    rows = group_words_to_rows(words, y_tol=3.0)
    
    best_row = None
    max_score = 0
    
    for r in rows:
        score = 0
        row_text_upper = " ".join([w["text"].upper() for w in r["words"]])
        
        # Mandatory checks
        if "DATE" not in row_text_upper: continue
        if not any(x in row_text_upper for x in ["WITHDRAWAL", "DEPOSIT", "BALANCE"]): continue
        
        for w in r["words"]:
            for k in keywords: 
                if k in w["text"].upper():
                    score += 1
        
        # Bonus for specific FirstBank phrases
        if "WITHDRAWAL" in row_text_upper and "(DR)" in row_text_upper: score += 3
        if "DEPOSIT" in row_text_upper and "(CR)" in row_text_upper: score += 3
        if "TRANSACTION DETAILS" in row_text_upper: score += 2

        if score > max_score:
            max_score = score
            best_row = r

    if not best_row or max_score < 3:
        return None

    print(f"DEBUG: Found FirstBank Header Row: {[w['text'] for w in best_row['words']]}")

    # Extract columns
    sorted_words = sorted(best_row["words"], key=lambda w: w["x0"])
    
    # Use helper similar to Zenith
    def find_word_x(text_part, start_idx=0):
        for i in range(start_idx, len(sorted_words)):
            clean_text = re.sub(r"[^\w\s]", "", sorted_words[i]["text"].upper())
            if text_part in clean_text:
                return i, sorted_words[i]
        return -1, None

    bounds = {}

    # 1. date
    idx_td, w_td = find_word_x("TRANS")
    if not w_td: idx_td, w_td = find_word_x("DATE") # Fallback
    if w_td: bounds["date"] = (w_td["x0"], w_td["x1"])

    # 2. reference 
    idx_ref, w_ref = find_word_x("REF")
    if w_ref: bounds["reference"] = (w_ref["x0"], w_ref["x1"])

    # 3. description (Transaction Details)
    idx_rem, w_rem = find_word_x("DETAILS")
    if w_rem: bounds["description"] = (w_rem["x0"], w_rem["x1"])

    # 4. value_date
    idx_vd, w_vd = find_word_x("VALUE")
    if w_vd: bounds["value_date"] = (w_vd["x0"], w_vd["x1"])

    # 5. Withdrawal (Debit)
    idx_deb, w_deb = find_word_x("WITHDRAWAL") 
    if not w_deb: idx_deb, w_deb = find_word_x("DR")
    if w_deb: bounds["Debit"] = (w_deb["x0"], w_deb["x1"])

    # 6. Deposit (Credit)
    idx_cred, w_cred = find_word_x("DEPOSIT")
    if not w_cred: idx_cred, w_cred = find_word_x("CR")
    if w_cred: bounds["Credit"] = (w_cred["x0"], w_cred["x1"])

    # 7. Balance
    idx_bal, w_bal = find_word_x("BALANCE")
    if w_bal: bounds["Balance"] = (w_bal["x0"], w_bal["x1"])

    # Mandatory
    if "TransDate" not in bounds or "Debit" not in bounds:
        return None

    # Construct cuts
    sorted_cols = sorted(bounds.items(), key=lambda item: item[1][0])
    
    cuts = {}
    for i in range(len(sorted_cols)):
        col_name, (l, r) = sorted_cols[i]
        
        if i == 0:
            start = 0.0
        else:
            prev_name, (prev_l, prev_r) = sorted_cols[i-1]
            start = (prev_r + l) / 2
            
        if i == len(sorted_cols) - 1:
            end = 1000.0
        else:
            next_name, (next_l, next_r) = sorted_cols[i+1]
            end = (r + next_l) / 2
            
        cuts[col_name] = (start, end)

    return cuts


def detect_wema_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for Wema Bank
    Headers: Tran Date | Value Date | Narration | Tran ID | Cheque No | Withdrawals | Deposits | Balance
    """
    if not words:
        return None

    # Keywords to identify header row
    keywords = ["TRAN", "DATE", "VALUE", "NARRATION", "ID", "CHEQUE", "WITHDRAWALS", "DEPOSITS", "BALANCE"]
    
    # Try multiple tolerances
    rows = group_words_to_rows(words, y_tol=3.0)
    
    best_row = None
    max_score = 0
    
    for r in rows:
        score = 0
        row_text_upper = " ".join([w["text"].upper() for w in r["words"]])
        
        # Mandatory checks (relaxed)
        if "DATE" not in row_text_upper: continue
        # Allow singular "WITHDRAWAL" or "DEPOSIT" just in case
        if not any(x in row_text_upper for x in ["WITHDRAWAL", "DEPOSIT", "BALANCE"]): continue
        
        for w in r["words"]:
            for k in keywords: 
                if k in w["text"].upper():
                    score += 1
        
        # Bonus for specific Wema phrases
        if "TRAN DATE" in row_text_upper: score += 2
        if "TRAN ID" in row_text_upper: score += 2
        if "CHEQUE NO" in row_text_upper: score += 2

        if score > max_score:
            max_score = score
            best_row = r

    if not best_row or max_score < 3:
        return None

    print(f"DEBUG: Found Wema Header Row: {[w['text'] for w in best_row['words']]}")

    # Extract columns
    sorted_words = sorted(best_row["words"], key=lambda w: w["x0"])
    
    # Use helper
    def find_word_x(text_part, start_idx=0):
        for i in range(start_idx, len(sorted_words)):
            clean_text = sorted_words[i]["text"].upper()
            if text_part in clean_text:
                return i, sorted_words[i]
        return -1, None

    bounds = {}

    # 1. date
    idx_td, w_td = find_word_x("TRAN")
    if w_td:
         bounds["date"] = (w_td["x0"], w_td["x1"])
    else:
         idx_td, w_td = find_word_x("DATE") # Fallback
         if w_td: bounds["date"] = (w_td["x0"], w_td["x1"])

    # 2. value_date (Find VALUE)
    idx_vd, w_vd = find_word_x("VALUE")
    if w_vd: bounds["value_date"] = (w_vd["x0"], w_vd["x1"])

    # 3. description
    idx_rem, w_rem = find_word_x("NARRATION")
    if w_rem: bounds["description"] = (w_rem["x0"], w_rem["x1"])

    # 4. reference (ID or No)
    idx_ref, w_ref = find_word_x("ID") # TRAN ID
    if w_ref: bounds["reference"] = (w_ref["x0"], w_ref["x1"])
    
    # 5. debit
    idx_deb, w_deb = find_word_x("WITHDRAWAL") 
    if not w_deb: idx_deb, w_deb = find_word_x("DR")
    if w_deb: bounds["debit"] = (w_deb["x0"], w_deb["x1"])

    # 6. credit
    idx_cred, w_cred = find_word_x("DEPOSIT")
    if not w_cred: idx_cred, w_cred = find_word_x("CR")
    if w_cred: bounds["credit"] = (w_cred["x0"], w_cred["x1"])

    # 7. balance
    idx_bal, w_bal = find_word_x("BALANCE")
    if w_bal: bounds["balance"] = (w_bal["x0"], w_bal["x1"])

    # Mandatory
    if "date" not in bounds or "debit" not in bounds:
        print("DEBUG: Wema detected header but missing TransDate or Debit column")
        return None

    # Construct cuts
    sorted_cols = sorted(bounds.items(), key=lambda item: item[1][0])
    
    cuts = {}
    for i in range(len(sorted_cols)):
        col_name, (l, r) = sorted_cols[i]
        
        if i == 0:
            start = 0.0
        else:
            prev_name, (prev_l, prev_r) = sorted_cols[i-1]
            start = (prev_r + l) / 2
            
        if i == len(sorted_cols) - 1:
            end = 1000.0
        else:
            next_name, (next_l, next_r) = sorted_cols[i+1]
            end = (r + next_l) / 2
            
        cuts[col_name] = (start, end)

    return cuts


def detect_fcmb_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for FCMB
    Headers: Tran. Date | Value Date | Ref | Transaction Details | Debit | Credit | Balance
    """
    if not words:
        return None

    # Keywords to identify header row
    keywords = ["TRAN", "DATE", "VALUE", "REF", "DETAILS", "DEBIT", "CREDIT", "BALANCE"]
    
    # Try multiple tolerances
    rows = group_words_to_rows(words, y_tol=3.0)
    
    best_row = None
    max_score = 0
    
    for r in rows:
        score = 0
        row_text_upper = " ".join([w["text"].upper() for w in r["words"]])
        
        # Mandatory checks
        if "DATE" not in row_text_upper or "DETAILS" not in row_text_upper: continue
        if not any(x in row_text_upper for x in ["DEBIT", "CREDIT", "BALANCE"]): continue
        
        for w in r["words"]:
            for k in keywords: 
                if k in w["text"].upper():
                    score += 1

        if score > max_score:
            max_score = score
            best_row = r

    if not best_row or max_score < 3:
        return None

    print(f"DEBUG: Found FCMB Header Row: {[w['text'] for w in best_row['words']]}")

    # Extract columns
    sorted_words = sorted(best_row["words"], key=lambda w: w["x0"])
    
    # Use helper
    def find_word_x(text_part, start_idx=0):
        for i in range(start_idx, len(sorted_words)):
            clean_text = sorted_words[i]["text"].upper()
            if text_part in clean_text:
                return i, sorted_words[i]
        return -1, None

    bounds = {}

    # 1. date
    idx_td, w_td = find_word_x("TRAN")
    if w_td:
         bounds["date"] = (w_td["x0"], w_td["x1"])
    else:
         idx_td, w_td = find_word_x("DATE") # Fallback
         if w_td: bounds["date"] = (w_td["x0"], w_td["x1"])

    # 2. value_date (Find VALUE)
    idx_vd, w_vd = find_word_x("VALUE")
    if w_vd: bounds["value_date"] = (w_vd["x0"], w_vd["x1"])

    # 3. reference
    idx_ref, w_ref = find_word_x("REF")
    if w_ref: bounds["reference"] = (w_ref["x0"], w_ref["x1"])

    # 4. description
    idx_rem, w_rem = find_word_x("DETAILS")
    if w_rem: bounds["description"] = (w_rem["x0"], w_rem["x1"])
    
    # 5. debit
    idx_deb, w_deb = find_word_x("DEBIT") 
    if w_deb: bounds["debit"] = (w_deb["x0"], w_deb["x1"])

    # 6. credit
    idx_cred, w_cred = find_word_x("CREDIT")
    if w_cred: bounds["credit"] = (w_cred["x0"], w_cred["x1"])

    # 7. balance
    idx_bal, w_bal = find_word_x("BALANCE")
    if w_bal: bounds["balance"] = (w_bal["x0"], w_bal["x1"])

    # Mandatory
    if "date" not in bounds or "debit" not in bounds:
        print("DEBUG: FCMB detected header but missing TransDate or Debit column")
        return None

    # Construct cuts
    sorted_cols = sorted(bounds.items(), key=lambda item: item[1][0])
    
    cuts = {}
    for i in range(len(sorted_cols)):
        col_name, (l, r) = sorted_cols[i]
        
        if i == 0:
            start = 0.0
        else:
            prev_name, (prev_l, prev_r) = sorted_cols[i-1]
            start = (prev_r + l) / 2
            
        if i == len(sorted_cols) - 1:
            end = 1000.0
        else:
            next_name, (next_l, next_r) = sorted_cols[i+1]
            end = (r + next_l) / 2
            
        cuts[col_name] = (start, end)

    return cuts


def clean_currency_str(value):
    """Converts string currency (e.g., '1,200.50') to float."""
    if value is None:
        return 0.0
    if isinstance(value, (float, int)):
        return float(value)
    clean_str = str(value).replace(",", "").strip()
    try:
        return float(clean_str)
    except ValueError:
        return 0.0

def extract_zenith_via_tables(pdf_path: Path, metadata: Dict) -> List[Dict]:
    """
    Specialized extractor for Zenith using pdfplumber's extract_tables()
    This is often more robust for Zenith's grid lines.
    """
    print("DEBUG: Using Zenith Table-Based Extraction Strategy")
    all_rows = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            # Zenith often has distinct table lines
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Clean None/newlines
                    clean_row = [str(cell).strip().replace("\\n", " ") if cell else "" for cell in row]
                    if any(clean_row): # Skip empty rows
                         all_rows.append(clean_row)

    if not all_rows:
        print("DEBUG: No tables found in Zenith PDF.")
        return []

    # Create DataFrame from all rows
    df = pd.DataFrame(all_rows)
    
    # Locate Header (Optional but good for validation)
    # We will use positional logic mainly, but header helps confirm we have a statement
    header_idx = -1
    for i, row in df.iterrows():
        row_str = " ".join([str(x).upper() for x in row])
        if "DATE" in row_str and ("DESCRIPTION" in row_str or "NARRATION" in row_str or "PARTICULARS" in row_str) and ("DEBIT" in row_str or "WITHDRAWAL" in row_str):
            header_idx = i
            break
    
    # If header found, slice from there, otherwise assume whole file is data (risky but fallback)
    start_row = header_idx + 1 if header_idx != -1 else 0
    df_data = df.iloc[start_row:]
    
    final_txns = []
    
    for i, row in df_data.iterrows():
        # Convert row to list for positional access
        row_list = row.tolist()
        
        # Skip empty rows or rows with too few columns
        if not row_list or len(row_list) < 5: continue
        
        # Check if first column looks like a date (Zenith specific: DD/MM/YYYY)
        first_col = str(row_list[0]).strip()
        
        # Is it a date?
        date_parsed = parse_date(first_col)
        # If parse_date returned input text and it's not a valid date format, skip
        if not is_date(first_col) and date_parsed == first_col:
             continue 

        # --- MERGE SPLIT DESCRIPTION LOGIC ---
        # Assumption: 
        # - Col 0: Date
        # - Col 1: Value Date (usually)
        # - Last 3 cols: Debit, Credit, Balance
        # - Middle cols: Description parts
        
        # Identify Financials (Last 3)
        debit_str = row_list[-3]
        credit_str = row_list[-2]
        balance_str = row_list[-1]
        
        # Identify Description (Index 2 to -3)
        # Only if we have enough columns. If len is 5, 2:-3 is empty range [2:2] -> []
        # In that case, maybe description is col 1? 
        # Let's start Description from Col 2 normally, but if len is 5, it means [Date, ValDate, Deb, Cred, Bal] -> No Desc?
        # Actually Zenith usually has [Date, ValDate, Desc..., Deb, Cred, Bal].
        
        if len(row_list) > 5:
            desc_parts = row_list[2:-3]
            description = " ".join([str(x).strip() for x in desc_parts if x]).strip()
        elif len(row_list) == 5:
            # Maybe [Date, Desc, Deb, Cred, Bal] ?
            description = str(row_list[1]).strip()
        else:
            description = ""
            
        # Parse financials
        d_float = clean_currency_str(debit_str)
        c_float = clean_currency_str(credit_str)
        b_float = clean_currency_str(balance_str)
        
        if d_float == 0 and c_float == 0: continue

        txn = {
            "date": date_parsed,
            "value_date": "",
            "reference": "",
            "branch": "",
            "description": description,
            "debit": d_float,
            "credit": c_float,
            "balance": b_float,
            "category": "Unallocated",
            "is_reversal": False,
            "_page": page_num,
            "_row": i
        }
        
        final_txns.append(txn)
             
    print(f"DEBUG: Extracted {len(final_txns)} transactions via Zenith Table strategy (Split Merge)")
    return final_txns


def extract_fcmb_via_tables(pdf_path: Path, metadata: Dict) -> List[Dict]:
    """
    Specialized extractor for FCMB using pdfplumber's extract_tables()
    Strategy: 
    - Col 0: Date
    - Last 3 Cols: Debit, Credit, Balance
    - Middle: Description
    """
    print("DEBUG: Using FCMB Table-Based Extraction Strategy")
    all_rows = []
    
    with pdfplumber.open(pdf_path) as pdf:
        # Try to capture totals from page 1 text for metadata
        try:
            first_text = pdf.pages[0].extract_text()
            # FCMB Summary Pattern
            deb_match = re.search(r"Total Debit[:\s]*([\d,]+\.\d{2})", first_text, re.IGNORECASE)
            cred_match = re.search(r"Total Credit[:\s]*([\d,]+\.\d{2})", first_text, re.IGNORECASE)
            
            if deb_match: 
                metadata["statement_total_debit"] = clean_currency_str(deb_match.group(1))
            if cred_match:
                metadata["statement_total_credit"] = clean_currency_str(cred_match.group(1))
        except:
            pass

        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Clean proper None values and newlines
                    clean_row = [str(cell).strip().replace("\\n", " ") if cell else "" for cell in row]
                    if any(clean_row): 
                         all_rows.append(clean_row)

    if not all_rows:
        print("DEBUG: No tables found in FCMB PDF.")
        return []

    final_txns = []
    
    for i, row in enumerate(all_rows):
        # Skip empty or short rows
        if not row or len(row) < 5: continue
        
        # Skip Headers (contain "DATE" and "PARTICULARS" etc)
        row_str = "".join(row).upper()
        if "DATE" in row_str and ("PARTICULARS" in row_str or "NARRATION" in row_str or "BALANCE" in row_str):
            continue

        # Check Date Column (Col 0)
        date_str = row[0]
        # Supports: 01/01/2023, 01-JAN-2023, 01 Jan 2024
        if not is_date(date_str):
             continue

        date_parsed = parse_date(date_str)
        
        # Identify Financials (Last 3)
        debit_str = row[-3]
        credit_str = row[-2]
        balance_str = row[-1]
        
        # Identify Description:
        # Usually index 2 to -3 (Date, ValueDate, ...Desc..., Deb, Cred, Bal)
        # But verify if Col 1 is ValueDate or part of Desc
        start_desc = 1
        # If Col 1 looks like a date, assume it's Value Date, so Desc starts at 2
        if is_date(row[1]):
            start_desc = 2
            
        desc_parts = row[start_desc:-3]
        description = " ".join([d for d in desc_parts if d]).strip()
        
        d_float = clean_currency_str(debit_str)
        c_float = clean_currency_str(credit_str)
        b_float = clean_currency_str(balance_str)
        
        if d_float == 0 and c_float == 0: continue

        txn = {
            "date": date_parsed,
            "value_date": parse_date(row[1]) if start_desc == 2 else "",
            "reference": "",
            "branch": "",
            "description": description,
            "debit": d_float,
            "credit": c_float,
            "balance": b_float,
            "category": "Unallocated",
            "is_reversal": False,
            "_page": 0,
            "_row": i
        }
        final_txns.append(txn)

    print(f"DEBUG: Extracted {len(final_txns)} transactions via FCMB Table strategy")
    return final_txns
             



def extract_access_consensus(pdf_path: Path, metadata: Dict) -> Tuple[List[Dict], Dict]:
    """
    Deterministic Global Layout Consensus Engine for Access Bank.
    Phase 1: Statistical scan to lock column zones.
    Phase 2: Deterministic extraction using locked zones.
    Phase 3: Mathematical reconciliation.
    """
    print("DEBUG: Using Deterministic Global Layout Consensus for Access Bank")
    
    date_coords = []
    money_coords = []
    
    # helper for mode calculation
    from collections import Counter
    
    with pdfplumber.open(pdf_path) as pdf:
        # Phase 1: Global Column Locking (Scan first 5 pages)
        scan_pages = pdf.pages[:5]
        for p in scan_pages:
            words = p.extract_words(x_tolerance=2, y_tolerance=2)
            for w in words:
                txt = w["text"].strip()
                # Track Date-like tokens
                if is_date(txt):
                    date_coords.append(round(w["x0"], 0))
                # Track Money-like tokens
                if MONEY_RE.match(txt):
                     money_coords.append(round(w["x1"], 0))

        if not date_coords:
            raise ValueError("Consensus Engine Error: No date columns found in scan.")

        # Lock Date Zone (Mode X0)
        date_mode = Counter(date_coords).most_common(1)[0][0]
        date_zone = (date_mode - 10, date_mode + 50)
        
        # Lock Financial Zones (Cluster X1s right of Date)
        potential_fin = [x for x in money_coords if x > date_zone[1]]
        if not potential_fin:
             raise ValueError("Consensus Engine Error: No financial columns found in scan.")
             
        # Simple Clustering: Group by proximity
        fin_clusters = []
        for x in sorted(set(potential_fin)):
            if not fin_clusters or x - fin_clusters[-1][-1] > 40:
                fin_clusters.append([x])
            else:
                fin_clusters[-1].append(x)
        
        # Take the mode of each cluster
        fin_modes = []
        for cluster in fin_clusters:
            counts = Counter([x for x in potential_fin if x in cluster])
            fin_modes.append(counts.most_common(1)[0][0])
        
        # Sort left to right
        fin_modes.sort()
        
        # Zones with ±30px tolerance
        TOL = 30
        zones = {
            "date": date_zone,
            "debit": (fin_modes[-3] - TOL, fin_modes[-3] + 10) if len(fin_modes) >= 3 else (0,0),
            "credit": (fin_modes[-2] - TOL, fin_modes[-2] + 10) if len(fin_modes) >= 2 else (0,0),
            "balance": (fin_modes[-1] - TOL, fin_modes[-1] + 10) if len(fin_modes) >= 1 else (0,0)
        }
        
        print(f"DEBUG: LOCKED ZONES: {zones}")

        # Phase 2: Deterministic Extraction
        all_transactions = []
        current_txn = None
        
        for page_num, page in enumerate(pdf.pages, 1):
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            row_groups = group_words_to_rows(words, y_tol=2.5)
            
            for rg in row_groups:
                row_text = " ".join([w["text"] for w in rg["words"]])
                
                # Noise Filtering
                if any(k in row_text.upper() for k in ["BALANCE BROUGHT FORWARD", "PAGE ", "TOTAL TURNOVER", "OPENING BALANCE", "CLOSING BALANCE"]):
                    continue
                
                # Assign words to zones
                row_data = {"date": "", "description_parts": [], "debit": "", "credit": "", "balance": ""}
                
                # First pass: Identify Date and Financials
                for w in rg["words"]:
                    x0, x1 = w["x0"], w["x1"]
                    txt = w["text"].strip()
                    
                    if zones["date"][0] <= x0 <= zones["date"][1] and is_date(txt):
                        row_data["date"] = txt
                    elif zones["debit"][0] <= x1 <= zones["debit"][1] and MONEY_RE.match(txt):
                        row_data["debit"] = txt
                    elif zones["credit"][0] <= x1 <= zones["credit"][1] and MONEY_RE.match(txt):
                        row_data["credit"] = txt
                    elif zones["balance"][0] <= x1 <= zones["balance"][1] and MONEY_RE.match(txt):
                        row_data["balance"] = txt
                    elif x0 > zones["date"][1] and (not fin_modes or x1 < fin_modes[0] - TOL):
                        # Description zone is between Date and first Financial
                        row_data["description_parts"].append(txt)
                
                description = " ".join(row_data["description_parts"]).strip()
                
                if row_data["date"]:
                    if current_txn:
                        all_transactions.append(current_txn)
                    
                    current_txn = {
                        "date": parse_date_smart(row_data["date"]),
                        "description": description,
                        "debit": parse_money(row_data["debit"]),
                        "credit": parse_money(row_data["credit"]),
                        "balance": parse_money(row_data["balance"]),
                        "_page": page_num,
                        "reconciliation_status": "Pending"
                    }
                elif current_txn and description:
                    current_txn["description"] = (current_txn["description"] + " " + description).strip()
        
        if current_txn:
            all_transactions.append(current_txn)

        # Phase 3: Mathematical Reconciliation
        reconciled_txns = []
        prev_bal = None
        
        if metadata.get("opening_balance"):
            prev_bal = clean_currency_str(metadata["opening_balance"])
            
        for txn in all_transactions:
            curr_deb = txn["debit"]
            curr_cred = txn["credit"]
            curr_bal = txn["balance"]
            
            if prev_bal is not None and curr_bal != 0:
                expected = round(prev_bal - curr_deb + curr_cred, 2)
                actual = round(curr_bal, 2)
                
                if abs(expected - actual) <= 0.02:
                    txn["reconciliation_status"] = "Success"
                else:
                    txn["reconciliation_status"] = "Anomaly"
                    print(f"DEBUG: Reconciliation FAIL at page {txn['_page']}: Expected {expected}, Got {actual}")
            
            if curr_bal != 0:
                prev_bal = curr_bal
            
            # Final formatting
            txn["originating_branch"] = ""
            txn["remarks"] = txn["description"]
            txn["category"] = "Unallocated"
            txn["is_reversal"] = False
            txn["_row"] = 0
            reconciled_txns.append(txn)

    return reconciled_txns, metadata


def extract_ecobank_via_tables(pdf_path: Path, metadata: Dict) -> List[Dict]:
    """
    Dedicated Ecobank extractor.

    Ecobank column layout (unusual — description comes FIRST):
        Remarks/Narration | Trans. Date | Debit | Credit | Balance

    Strategy:
        1. Try pdfplumber table extraction (works if PDF has grid lines).
        2. Fall back to word-based extraction using detect_ecobank_columns().
    Does NOT call repair_ref_branch_remarks (GTBank-specific — would corrupt Ecobank data).
    """
    print("DEBUG: Using Ecobank Dedicated Extractor")

    # ------------------------------------------------------------------ #
    # ATTEMPT 1 — pdfplumber table extraction                             #
    # ------------------------------------------------------------------ #
    table_txns = _ecobank_from_tables(pdf_path)
    if table_txns:
        print(f"DEBUG: Ecobank table strategy yielded {len(table_txns)} transactions")
        _attach_metadata(table_txns)
        return table_txns

    # ------------------------------------------------------------------ #
    # ATTEMPT 2 — word-based extraction with detect_ecobank_columns       #
    # ------------------------------------------------------------------ #
    print("DEBUG: Ecobank table extraction found no data, trying word-based fallback")
    return _ecobank_from_words(pdf_path, metadata)


def _attach_metadata(txns: List[Dict]) -> None:
    """Ensure every transaction has the mandatory output fields."""
    for t in txns:
        t.setdefault("value_date", "")
        t.setdefault("reference", "")
        t.setdefault("originating_branch", "")
        t.setdefault("remarks", t.get("description", ""))
        t.setdefault("category", "Unallocated")
        t.setdefault("is_reversal", False)
        t.setdefault("_page", 0)
        t.setdefault("_row", 0)


def _ecobank_from_tables(pdf_path: Path) -> List[Dict]:
    """
    Try pdfplumber's extract_table() for Ecobank.
    Returns [] if no usable tables are found.

    Expected column order in the table:
        Remarks | Trans Date | Debit | Credit | Balance
    """
    all_rows: List[List[str]] = []
    page_map: List[int] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    clean = [str(c or "").strip().replace("\n", " ") for c in row]
                    if any(clean):
                        all_rows.append(clean)
                        page_map.append(page_num)

    if not all_rows:
        return []

    df = pd.DataFrame(all_rows)

    # Locate table header — must contain DATE and (DEBIT or CREDIT)
    header_idx = -1
    col_date = col_desc = col_debit = col_credit = col_balance = None

    for i, row in df.iterrows():
        row_upper = [str(x).upper() for x in row]
        row_joined = " ".join(row_upper)
        if ("DATE" in row_joined or "TRANS" in row_joined) and (
            "DEBIT" in row_joined or "WITHDRAWAL" in row_joined
        ):
            header_idx = i
            # Map column indices from header text
            for j, cell in enumerate(row_upper):
                if re.search(r"REMARKS?|NARRATION|DESCRIPTION|PARTICULARS", cell):
                    col_desc = j
                elif re.search(r"TRANS|TRN\s*DATE|DATE", cell) and col_date is None:
                    col_date = j
                elif re.search(r"DEBIT|WITHDRAWAL|DR\b", cell):
                    col_debit = j
                elif re.search(r"CREDIT|DEPOSIT|CR\b", cell):
                    col_credit = j
                elif re.search(r"BALANCE|BAL\b", cell):
                    col_balance = j
            break

    # Validate: need at least date + debit + credit + balance
    if header_idx == -1 or any(v is None for v in [col_date, col_debit, col_credit, col_balance]):
        print(f"DEBUG: Ecobank table header map incomplete: date={col_date} deb={col_debit} cred={col_credit} bal={col_balance}")
        return []

    # If no description column found, guess it's the first column that isn't date/debit/credit/balance
    if col_desc is None:
        reserved = {col_date, col_debit, col_credit, col_balance}
        col_desc = next((j for j in range(len(df.columns)) if j not in reserved), None)

    df_data = df.iloc[header_idx + 1 :]
    txns: List[Dict] = []

    current: Dict = {}  # used for multi-line description merge

    for i, row in df_data.iterrows():
        row_list = row.tolist()
        if not any(str(x).strip() for x in row_list):
            continue  # blank row

        raw_date = str(row_list[col_date]).strip() if col_date is not None else ""
        raw_desc = str(row_list[col_desc]).strip() if col_desc is not None else ""
        raw_deb = str(row_list[col_debit]).strip() if col_debit is not None else ""
        raw_cred = str(row_list[col_credit]).strip() if col_credit is not None else ""
        raw_bal = str(row_list[col_balance]).strip() if col_balance is not None else ""

        # Sanitise
        raw_date = raw_date.replace("None", "").strip()
        raw_desc = raw_desc.replace("None", "").strip()
        raw_deb  = raw_deb.replace("None", "").strip()
        raw_cred = raw_cred.replace("None", "").strip()
        raw_bal  = raw_bal.replace("None", "").strip()

        # Stop at closing/opening balance rows
        combined_upper = " ".join([raw_date, raw_desc, raw_deb, raw_cred, raw_bal]).upper()
        if "CLOSING BALANCE" in combined_upper:
            break
        if "OPENING BALANCE" in combined_upper:
            continue

        parsed_date = parse_date_smart(raw_date)

        deb_val = clean_currency_str(raw_deb)
        cred_val = clean_currency_str(raw_cred)
        bal_val = clean_currency_str(raw_bal)

        if parsed_date:
            # New transaction anchor
            if current:
                txns.append(current)
            current = {
                "date": parsed_date,
                "description": raw_desc,
                "debit": deb_val,
                "credit": cred_val,
                "balance": bal_val,
                "_page": page_map[i] if i < len(page_map) else 0,
                "_row": i,
            }
        else:
            # Continuation line (multi-line narration)
            if current and raw_desc:
                current["description"] = (current["description"] + " " + raw_desc).strip()
            # Merge any amounts that appeared on continuation line
            if current:
                if not current["debit"] and deb_val:
                    current["debit"] = deb_val
                if not current["credit"] and cred_val:
                    current["credit"] = cred_val
                if not current["balance"] and bal_val:
                    current["balance"] = bal_val

    if current:
        txns.append(current)

    # Final filter: skip rows with zero movement
    result = []
    for t in txns:
        if t["debit"] == 0.0 and t["credit"] == 0.0:
            continue
        result.append({
            "date": t["date"],
            "value_date": "",
            "reference": "",
            "originating_branch": "",
            "remarks": t["description"],
            "description": t["description"],
            "debit": t["debit"],
            "credit": t["credit"],
            "balance": t["balance"],
            "category": "Unallocated",
            "is_reversal": False,
            "_page": t["_page"],
            "_row": t["_row"],
        })
    return result


def _ecobank_from_words(pdf_path: Path, metadata: Dict) -> List[Dict]:
    """
    Word-based Ecobank extraction using detect_ecobank_columns().
    Mirrors the generic extract_transactions pipeline but:
      - skips repair_ref_branch_remarks (GTBank-specific)
      - does NOT populate a 'reference' field from the date column
    """
    all_rows: List[Dict] = []
    base_cuts = None

    with pdfplumber.open(pdf_path) as pdf:
        # --- Phase 1: detect column boundaries ---
        for i, page in enumerate(pdf.pages):
            try:
                words = page.extract_words(x_tolerance=2, y_tolerance=2)
            except Exception as e:
                print(f"DEBUG: Ecobank word extraction failed on page {i}: {e}")
                continue
            if not words:
                continue
            base_cuts = detect_ecobank_columns(words)
            if base_cuts:
                print(f"DEBUG: Ecobank word-based: header on page {i+1}, cuts={base_cuts}")
                break

        if not base_cuts:
            raise ValueError("Ecobank word-based extractor: could not detect column header")

        # --- Phase 2: extract rows per page ---
        for page_num, page in enumerate(pdf.pages, 1):
            try:
                words = page.extract_words(x_tolerance=2, y_tolerance=2)
            except Exception:
                continue
            if not words:
                continue

            row_groups = group_words_to_rows(words, y_tol=2.5)

            for rg in row_groups:
                line_text = " ".join(w["text"] for w in rg["words"]).lower()

                # Skip table header rows
                if (
                    re.search(r"\btrans\.?\b|\btransaction\b", line_text, re.I)
                    and re.search(r"\bdebit\b|\bwithdrawal\b", line_text, re.I)
                    and re.search(r"\bcredit\b|\bdeposit\b", line_text, re.I)
                    and re.search(r"\bbalance\b", line_text, re.I)
                ):
                    continue
                # Skip noise
                if "computer generated" in line_text or "customer information" in line_text:
                    continue

                row = assign_row_to_cols(rg["words"], base_cuts)
                if is_noise_row(row):
                    continue

                def _has_content(r: dict) -> bool:
                    return any(isinstance(v, str) and v.strip() for v in r.values())

                if not _has_content(row):
                    continue

                row["_page"] = page_num
                all_rows.append(row)

    if not all_rows:
        return []

    # --- Phase 3: merge multiline rows ---
    merged = merge_multiline_rows(all_rows)

    # --- Phase 4: finalise (NO GTBank repair) ---
    result: List[Dict] = []
    for txn in sorted(merged, key=lambda t: (t.get("_page", 0), t.get("_row", 0))):
        deb_val  = parse_money(txn.get("debit", ""))
        cred_val = parse_money(txn.get("credit", ""))
        if deb_val == 0.0 and cred_val == 0.0:
            continue

        description = txn.get("description", "")

        result.append({
            "date": txn["date"],
            "value_date": txn.get("value_date", ""),
            "reference": "",          # Ecobank has no reference column
            "originating_branch": "",  # Ecobank has no branch column
            "remarks": description,
            "description": description,
            "debit": deb_val,
            "credit": cred_val,
            "balance": parse_money(txn.get("balance", "")),
            "category": "Unallocated",
            "is_reversal": False,
            "_page": txn.get("_page"),
            "_row": txn.get("_row"),
        })

    print(f"DEBUG: Ecobank word-based extractor yielded {len(result)} transactions")
    return result

