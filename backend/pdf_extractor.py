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

# OCR fallback
try:
    from ocr_helper import extract_header_with_openai_vision, VISION_AVAILABLE
except ImportError:
    VISION_AVAILABLE = False
    def extract_header_with_openai_vision(*args, **kwargs):
        return ""

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
    cols = [("TransDate", x_txn)]
    
    if x_val is not None:
        cols.append(("ValueDate", x_val))
    if x_rem is not None:
        cols.append(("Remarks", x_rem))
    if x_deb is not None:
        cols.append(("Debit", x_deb))
    if x_cred is not None:
        cols.append(("Credit", x_cred))
    if x_bal is not None:
        cols.append(("Balance", x_bal))
        
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
    Parse various date formats into standard DD-MM-YYYY string.
    Returns None if invalid.
    """
    s = (date_str or "").strip()
    if not s:
        return None
        
    # Standard: 01-Jan-2023 -> Keep as is (backend handles it)
    if DATE_DMY_RE.match(s):
        return s
        
    # Access: 10/1/2025 (MM/DD/YYYY) -> 01-Oct-2025
    if DATE_MDY_SL_RE.match(s):
        try:
            parts = s.split('/')
            mm, dd, yyyy = int(parts[0]), int(parts[1]), int(parts[2])
            # Convert to standard format for consistency if needed, 
            # or just return as is if the frontend/excel handles it.
            # Let's normalize to DD-MMM-YYYY for consistency with existing regexes
            months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            if 1 <= mm <= 12:
                return f"{dd:02d}-{months[mm]}-{yyyy}"
        except:
            pass
            
    # Fidelity: 15-Jan-21 (DD-MMM-YY) -> 15-Jan-2021
    if DATE_DMY_YY_RE.match(s):
        parts = s.split('-')
        if len(parts) == 3:
            # Assume 20xx for 2-digit year
            return f"{parts[0]}-{parts[1]}-20{parts[2]}"

    return None

# Date Regexes
DATE_DMY_DOT_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")      # 13.01.2023
DATE_DMY_SL_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")         # 13/01/2023 (Zenith/Generic)

def parse_date_smart(date_str: str) -> str | None:
    """
    Parse various date formats into standard DD-MM-YYYY string.
    Returns None if invalid.
    """
    s = (date_str or "").strip()
    if not s:
        return None
        
    # Standard: 01-Jan-2023 -> Keep as is
    if DATE_DMY_RE.match(s):
        return s
        
    # Zenith/Generic: 13/01/2023 (DD/MM/YYYY)
    if DATE_DMY_SL_RE.match(s):
        try:
            parts = s.split('/')
            p0, p1, p2 = int(parts[0]), int(parts[1]), int(parts[2])
            
            # Heuristic: If first part > 12, it's definitely DD/MM
            # If both <= 12, assume DD/MM for Nigerian banks (British standard)
            # UNLESS it's specifically marked as Access Bank which might use MDY (rare here but kept in mind)
            
            dd, mm, yyyy = p0, p1, p2
            
            # Basic validation
            months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            if 1 <= mm <= 12 and 1 <= dd <= 31:
                return f"{dd:02d}-{months[mm]}-{yyyy}"
        except:
            pass
            
    # Fidelity: 15-Jan-21 (DD-MMM-YY) -> 15-Jan-2021
    if DATE_DMY_YY_RE.match(s):
        parts = s.split('-')
        if len(parts) == 3:
            return f"{parts[0]}-{parts[1]}-20{parts[2]}"

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
    return DATE_RE.match((row.get("TransDate") or row.get("Date") or "").strip()) is not None

def is_noise_row(row: dict) -> bool:
    """Check if row is Account Summary/totals block"""
    text = " ".join([
        row.get("Remarks","") or "",
        row.get("Description","") or "",
        row.get("Reference","") or "",
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
        
    # --- 0) Special Case: Zenith Table Strategy
    if bank_identifier == "zenith":
        try:
             # Try table strategy first
             zenith_txns = extract_zenith_via_tables(Path(pdf_path), metadata)
             if zenith_txns:
                 return zenith_txns, metadata
             print("DEBUG: Zenith table strategy returned no transactions, falling back to standard...")
        except Exception as e:
             print(f"DEBUG: Zenith table strategy failed: {e}")

    # --- 0b) Special Case: FCMB Table Strategy
    if bank_identifier == "fcmb":
        try:
             fcmb_txns = extract_fcmb_via_tables(Path(pdf_path), metadata)
             if fcmb_txns:
                 return fcmb_txns, metadata
             print("DEBUG: FCMB table strategy returned no transactions, falling back to standard...")
        except Exception as e:
             print(f"DEBUG: FCMB table strategy failed: {e}")

    # --- 0c) Special Case: Ecobank Table Strategy
    if bank_identifier == "ecobank":
        try:
             ecobank_txns = extract_ecobank_via_tables(Path(pdf_path), metadata)
             if ecobank_txns:
                 return ecobank_txns, metadata
             print("DEBUG: Ecobank table strategy returned no transactions, falling back to standard...")
        except Exception as e:
             print(f"DEBUG: Ecobank table strategy failed: {e}")

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
                
        # --- OpenAI Vision OCR Fallback: Try if standard detection completely failed ---
        if not base_cuts:
            print("DEBUG: Standard detection failed on all pages. Trying OpenAI Vision OCR fallback...")
            
            # Check if OpenAI API key is available
            if not os.getenv("OPENAI_API_KEY"):
                raise ValueError("Could not detect column header after scanning all pages. OpenAI Vision not available (set OPENAI_API_KEY in .env for OCR fallback)")
            
            try:
                from pdf_render import render_page_png
                from openai_vision import ocr_pdf_page_image
                
                ocr_text = ""
                for i in range(min(2, len(pdf.pages))):
                    print(f"DEBUG: Attempting Vision OCR on page {i}...")
                    png = render_page_png(str(pdf_path), i)
                    ocr_text += "\n" + ocr_pdf_page_image(png)
                
                print("DEBUG: OCR TEXT SAMPLE:", ocr_text[:800])
                
                # Convert OCR text to fake 'words' is hard; fastest approach:
                # use OCR only to identify bank + header variant OR just error clearly.
                raise ValueError(
                    "Header not detected by pdfplumber. OCR successfully extracted text (see DEBUG output), "
                    "but OCR-to-rows parsing is not yet implemented. Please use text-based PDFs or contact support."
                )
            except ImportError as ie:
                raise ValueError(f"Could not detect column header and OCR fallback unavailable: {ie}")
            except Exception as vision_error:
                print(f"DEBUG: Vision OCR fallback failed: {vision_error}")
                raise ValueError(f"Could not detect column header after scanning all pages. Vision OCR also failed: {vision_error}")
        
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
        if txn.get("remarks"):
            desc_parts.append(txn["remarks"])
        description = " ".join(desc_parts).strip()
        
        # Keep fields SEPARATE for Excel, but include description for categorization
        final_transactions.append({
            "date": txn["date"],
            "value_date": txn.get("value_date", ""),
            "reference": txn.get("reference", ""),
            "originating_branch": txn.get("branch", ""),  # Note: internally "branch", externally "originating_branch"
            "remarks": txn.get("remarks", ""),
            "description": description,  # For categorization only
            "debit": parse_money(txn["debit"]),
            "credit": parse_money(txn["credit"]),
            "balance": parse_money(txn["balance"]),
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
    Build structured transaction description from reference, branch, and remarks
    
    Rules:
    - Ignore placeholder refs like '', "'", "'GAP", "GAP"
    - Don't duplicate branch if already in remarks
    - Keep long reference IDs
    """
    ref = (tx.get("reference") or "").strip()
    branch = (tx.get("branch") or "").strip()
    remarks = (tx.get("remarks") or "").strip()

    # Ignore placeholder references
    if ref in {"", "'", "'GAP", "GAP"}:
        ref = ""

    parts = []
    if ref:
        parts.append(ref)
    if branch and branch not in remarks:  # Don't duplicate branch
        parts.append(branch)
    if remarks:
        parts.append(remarks)

    return " ".join(parts).strip()


def repair_ref_branch_remarks(tx: dict) -> dict:
    """
    Repair column mixing between Reference, Originating Branch, and Remarks (GTBank-specific)
    
    This handles common issues where:
    - Branch code (e.g., "635 AKIN ADESOLA") spills into Remarks or Reference
    - Reference ID spills into Remarks
    - Multi-part references get split across columns
    """
    ref = (tx.get("reference") or "").strip()
    br = (tx.get("originating_branch") or tx.get("branch") or "").strip()
    rm = (tx.get("remarks") or "").strip()

    # 1) If branch is at the start of remarks, move it out
    m = BRANCH_PREFIX.match(rm)
    if m and (not br or not BRANCH_LIKE.match(br)):
        br = m.group(1).strip()
        rm = m.group(2).strip()

    # 2) If reference accidentally contains branch, move branch out
    if BRANCH_LIKE.match(ref) and not br:
        br, ref = ref, ""

    # 3) If remarks starts with a reference token and ref is empty/placeholder, extract it
    # Use looks_like_ref to ensure it contains digits (prevents VATCHARGES, etc.)
    first = rm.split()[0] if rm else ""
    if (not ref or ref in {"'", "GAP", "'GAP"}) and first and looks_like_ref(first):
        ref = first
        rm = rm[len(first):].strip()

    # 4) If ref contains multiple tokens, keep first as ref, push rest into remarks
    if ref and " " in ref:
        parts = ref.split()
        ref = parts[0]
        spill = " ".join(parts[1:]).strip()
        if spill:
            rm = (spill + " " + rm).strip()
    
    # 5) Clean placeholder references
    if ref in {"'", "GAP", "'GAP"}:
        ref = ""

    # Update transaction with INTERNAL field names (branch, not originating_branch)
    tx["reference"] = ref
    tx["branch"] = br  # Use 'branch' internally
    tx["remarks"] = rm
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
        # Clean up: stop at "Total Debit" or "Total Credit" or "Currency" or "Account No" if captured
        stop_patterns = ["TOTAL DEBIT", "TOTAL CREDIT", "CURRENCY", "ACCOUNT NO", "ACC NO"]
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


def group_words_to_rows(words: List[Dict[str, Any]], y_tol: float = 3.5) -> List[Dict[str, Any]]:
    """
    Group words into physical rows (by Y coordinate)
    Increased tolerance to capture slightly misaligned text (e.g. scanners)
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

def assign_row_to_cols(row_words: List[Dict[str, Any]], cuts: Dict[str, Tuple[float, float]]) -> Dict[str, str]:

    # Capture full raw text for fallback parsing
    row_words.sort(key=lambda w: w["x0"])
    full_line_text = " ".join([w["text"] for w in row_words])

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
    
    # REPAIR 1: TransDate mixed into Remarks (Ecobank/GTBank/Zenith)
    if "TransDate" in bucket and not bucket["TransDate"] and bucket.get("Remarks"):
        w_text = bucket["Remarks"][0]
        # Regex update: Allow numeric month (e.g. 13/01/2023) or alpha month (DD-MMM-YYYY)
        if re.match(r"^\d{1,2}[-/\.]\w+[-/\.]\d{2,4}$", w_text): 
            bucket["TransDate"].append(bucket["Remarks"].pop(0))
            
    # REPAIR 2: Reference mixed into Remarks (GTBank)
    if "Reference" in bucket and not bucket["Reference"] and bucket.get("Remarks"):
        w_text = bucket["Remarks"][0]
        if looks_like_ref(w_text) and re.search(r"\d", w_text):
             bucket["Reference"].append(bucket["Remarks"].pop(0))

    # REPAIR 3: Branch Code mixed into Remarks (GTBank)
    if "Branch" in bucket and not bucket["Branch"] and bucket.get("Remarks"):
        w_text = bucket["Remarks"][0]
        if re.match(r"^\d{3}$", w_text):
            bucket["Branch"].append(bucket["Remarks"].pop(0))

    # REPAIR 4: Orphan Amount in Remarks (e.g. Debit shifted left into Remarks)
    # Check if Remarks ends with something that looks like money, and Debit/Credit are empty
    # This happens when the column cut is slightly too far to the right
    if bucket.get("Remarks") and (not bucket.get("Debit") or not bucket.get("Credit")):
        w_text = bucket["Remarks"][-1]
        
        # Is it a money value? (simple check: digits, dot/comma, no letters)
        if re.match(r"^-?[\d,]+\.\d{2}$", w_text):
            # Check geometric proximity to Debit/Credit column LEFT edge
            # We need the word object for this... but we only stored text in buckets.
            # Workaround: Find the word in row_words that matches this text and is generally at the end
            # This is slightly risky if the same amount appears twice, but acceptable for repair.
            
            # Find candidate word (last one matching text)
            candidate_word = None
            for w in reversed(row_words):
                if w["text"] == w_text:
                    candidate_word = w
                    break
            
            if candidate_word:
                x1 = candidate_word["x1"]
                
                # Check Debit
                if "Debit" in cuts and not bucket["Debit"]:
                    deb_l, deb_r = cuts["Debit"]
                    # If the word ends *near* the debit column (within 30px of left edge, or inside it)
                    if deb_l - 30 <= x1 <= deb_r:
                        print(f"DEBUG: Moved orphan Debit from Remarks: {w_text}")
                        bucket["Debit"].append(bucket["Remarks"].pop())

                # Check Credit (only if we didn't just move it to Debit)
                elif "Credit" in cuts and not bucket["Credit"]:
                    cred_l, cred_r = cuts["Credit"]
                    if cred_l - 30 <= x1 <= cred_r:
                        print(f"DEBUG: Moved orphan Credit from Remarks: {w_text}")
                        bucket["Credit"].append(bucket["Remarks"].pop())

    # REPAIR 5: Aggressive Numeric Snapping
    # If Debit/Credit still empty, look for ANY unassigned word (or words in Remarks) 
    # that strongly resemble amounts and are geometrically closest to the column.
    # This covers cases where the column boundary is wildly off.
    for target_col in ["Debit", "Credit", "Balance"]:
        if target_col in cuts and not bucket[target_col]:
            target_center = (cuts[target_col][0] + cuts[target_col][1]) / 2
            
            # Look at words in Remarks (often where they end up if cuts are wrong)
            # or any other bucket? No, usually just Remarks or "unassigned" if we had that.
            if bucket.get("Remarks"):
                best_word_idx = -1
                min_dist = float('inf')
                
                for i, w_text in enumerate(bucket["Remarks"]):
                    # Is it a money value?
                    if re.match(r"^-?[\d,]+\.\d{2}$", w_text):
                        # Find the word object
                        cand_w = next((w for w in reversed(row_words) if w["text"] == w_text), None)
                        if cand_w:
                            # Distance from word center to column center
                            w_center = (cand_w["x0"] + cand_w["x1"]) / 2
                            dist = abs(w_center - target_center)
                            
                            # Threshold: must be reasonably close (e.g. within 50pts)
                            if dist < 50 and dist < min_dist:
                                min_dist = dist
                                best_word_idx = i
                
                if best_word_idx != -1:
                    print(f"DEBUG: Snapped {bucket['Remarks'][best_word_idx]} to {target_col} (dist={min_dist:.1f})")
                    bucket[target_col].append(bucket["Remarks"].pop(best_word_idx))


    # CLEANUP: Remove internal spaces from numeric columns (e.g. "1, 500, 000.00" -> "1,500,000.00")
    for col in ["Debit", "Credit", "Balance"]:
        if col in bucket and bucket[col]:
            # Join parts, then remove spaces
            full_str = "".join(bucket[col])
            # If it's a valid number with spaces, clean it
            # But be careful not to merge completely separate numbers (though typicaly only one amount per col)
            bucket[col] = [full_str.replace(" ", "")]

    return {col: " ".join(vals).strip() for col, vals in bucket.items()}


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

    # 1. TransDate (DATE POSTED or just DATE at start)
    # Usually the first "DATE"
    idx_td, w_td = find_word_x("DATE")
    if w_td: 
        bounds["TransDate"] = (w_td["x0"], w_td["x1"])
    
    # 2. ValueDate (Look for "VALUE")
    idx_vd, w_vd = find_word_x("VALUE")
    if w_vd:
        bounds["ValueDate"] = (w_vd["x0"], w_vd["x1"])
        
        # Refine TransDate: ensure TransDate is to the LEFT of ValueDate
        if w_td and w_td["x0"] > w_vd["x0"]:
             # Oops, we picked the "DATE" from "VALUE DATE" as transdate?
             # But "VALUE" is usually before "DATE".
             # If we mapped TransDate to the DATE in VALUE DATE, fix it.
             pass 

    # 3. Remarks (NARRATION / DESCRIPTION)
    idx_rem, w_rem = find_word_x("NARRATION")
    if not w_rem: idx_rem, w_rem = find_word_x("DESCRIPTION")
    if not w_rem: idx_rem, w_rem = find_word_x("PARTICULARS")
    if w_rem: bounds["Remarks"] = (w_rem["x0"], w_rem["x1"])

    # 4. Debit/Credit/Balance
    for col in ["DEBIT", "CREDIT", "BALANCE"]:
        idx, w = find_word_x(col)
        # Handle "DR" or "CR"
        if not w and col == "DEBIT": idx, w = find_word_x("DR")
        if not w and col == "CREDIT": idx, w = find_word_x("CR")
        if not w and col == "BALANCE": idx, w = find_word_x("BAL")
        
        if w:
            bounds[col.title()] = (w["x0"], w["x1"])

    # Mandatory check
    if "TransDate" not in bounds or "Debit" not in bounds:
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
        "TransDate": r"(?:Trans(?:action)?\s*Date|Trans\.?\s*Date|Trn\s*Date|Date\b)",
        "ValueDate": r"(?:Value\s*Date|Val\s*Date)",
        "Remarks": r"(?:Description|Narration|Remarks?|Details|Particulars)",
        "Debit": r"(?:Debit|Withdrawal|Dr\b)",
        "Credit": r"(?:Credit|Deposit|Cr\b)",
        "Balance": r"(?:Balance|Bal\b)"
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
    x_value_l = find_left(header_terms["ValueDate"])
    x_value_r = find_right(header_terms["ValueDate"])

    # Detect TransDate, but exclude matches that overlap ValueDate
    # (Because regex "Date" matches "Value Date")
    trans_words = [w for w in header_words if re.search(header_terms["TransDate"], w["text"], re.I)]
    
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

    x_desc_l  = find_left(header_terms["Remarks"])
    x_desc_r  = find_right(header_terms["Remarks"])

    x_deb_l   = find_left(header_terms["Debit"])
    x_deb_r   = find_right(header_terms["Debit"])

    x_cred_l  = find_left(header_terms["Credit"])
    x_cred_r  = find_right(header_terms["Credit"])

    x_bal_l   = find_left(header_terms["Balance"])
    x_bal_r   = find_right(header_terms["Balance"])

    # require core columns
    if any(v is None for v in [x_trans_l, x_desc_l, x_deb_l, x_cred_l, x_bal_l]):
        return None

    cols = []
    cols.append(("TransDate", x_trans_l, x_trans_r))
    cols.append(("Remarks", x_desc_l, x_desc_r))
    if x_value_l is not None:
        cols.append(("ValueDate", x_value_l, x_value_r))
    cols.append(("Debit", x_deb_l, x_deb_r))
    cols.append(("Credit", x_cred_l, x_cred_r))
    cols.append(("Balance", x_bal_l, x_bal_r))

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
        if name1 == "TransDate" and name2 == "Debit":
            # "Transaction Date" header is wide (contains "Transaction" + "Date").
            # Detection only caught "Date" (at ~324).
            # "Debit" header is narrow but data spills left.
            
            # Anchor: Right edge of "Date" word (r1).
            # We want to cut slightly left of the "Date" word ends?
            # No, keep the "Date" word. Cut left of "One space after Date".
            # Shift left by 25pts from r1.
            proposed_cut = r1 - 25
            
            # Safety: Ensure we don't cut into the "Date" word itself too much.
            # l1 is start of "Date".
            # Allow at least 20pts for "Date".
            if (proposed_cut - l1) < 20:
                 proposed_cut = l1 + 20
                 
            mid = proposed_cut
            
        # 2. "Remarks" -> "TransDate"
        elif name1 == "Remarks" and name2 == "TransDate":
            # TransDate detected only "Date" at ~324.
            # But the column really starts at "Transaction" (~257) or data (~260).
            # Standard mid (r1 + l2)/2 = (200 + 324)/2 = 262.
            # 262 might clip '31-May'.
            # We treat l2 as if it were 'Transaction' start (e.g. l2 - 30).
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
    cuts["Date"] = (0, x_details - 5)
    
    # Details: Date to Ref (or Value if Ref missing)
    next_col = x_ref if x_ref else x_val
    cuts["Remarks"] = (x_details - 5, next_col - 5)
    
    # Reference
    if x_ref and x_val:
        cuts["Reference"] = (x_ref - 5, x_val - 5)
    elif x_ref:
        cuts["Reference"] = (x_ref - 5, x_with - 50) # Fallback

    # Value Date
    if x_val:
        cuts["ValueDate"] = (x_val - 5, x_with - 10)

    # Withdrawals (Debit)
    cuts["Debit"] = (x_with - 80, x_with + 5)
    
    # Lodgements (Credit)
    cuts["Credit"] = (x_lodge - 80, x_lodge + 5)
    
    # Balance
    cuts["Balance"] = (x_bal - 80, x_bal + 5)

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
    cols.append(("TransDate", trans_date.get("x0", 0)))
    if val_date: cols.append(("ValueDate", val_date.get("x0", 0)))
    if channel: cols.append(("Channel", channel.get("x0", 0)))
    cols.append(("Remarks", details.get("x0", 0)))
    
    # Note: Fidelity puts Pay In (Credit) before Pay Out? Check template?
    # Template: Pay In | Pay Out | Balance
    # Wait, template img shows: Pay In | Pay Out | Balance
    # But wait, usually Pay Out is Debit.
    # Let's map robustly by x-coord
    
    if pay_in: cols.append(("Credit", pay_in.get("x0", 0)))
    if pay_out: cols.append(("Debit", pay_out.get("x0", 0)))
    cols.append(("Balance", bal.get("x0", 0)))

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
    cuts["Txn Date"] = (0, x_gl - 10) # call it Txn Date to match standard map later
    cuts["Remarks"] = (x_gl - 10, x_deb - 100) # GL Description
    
    cuts["Debit"] = (x_deb - 80, x_deb + 5)
    cuts["Credit"] = (x_cred - 80, x_cred + 5)
    cuts["Balance"] = (x_bal - 80, x_bal + 5)

    print(f"DEBUG: APT columns: {cuts.keys()}")
    return cuts


def detect_uba_columns(words: List[Dict], bank_identifier: str) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect UBA column boundaries
    Headers: TRANS DATE | VALUE DATE | NARRATION | CHQ NO | DEBIT | CREDIT | BALANCE
    """
    if bank_identifier != "uba":
        return None
    
    # Look for UBA header tokens (7 columns)
    header_tokens = {
        "TRANS": [], "DATE": [], "VALUE": [], "NARRATION": [],
        "CHQ": [], "NO": [], "DEBIT": [], "CREDIT": [], "BALANCE": []
    }
    
    for w in words:
        txt = w["text"].upper().strip()
        if txt in header_tokens:
            header_tokens[txt].append(w)
    
    # Build column candidates
    # TRANS DATE = 1 column, VALUE DATE = 1 column, NARRATION = 1, CHQ NO = 1, DEBIT = 1, CREDIT = 1, BALANCE = 1
    columns = []
    
    # Find "TRANS" + "DATE" pair
    if header_tokens["TRANS"] and header_tokens["DATE"]:
        trans = min(header_tokens["TRANS"], key=lambda w: w["x0"])
        date1 = [d for d in header_tokens["DATE"] if d["x0"] > trans["x0"]]
        if date1:
            date1 = min(date1, key=lambda w: w["x0"])
            columns.append(("TransDate", trans["x0"], date1["x1"]))
    
    # Find "VALUE" + "DATE" pair
    if header_tokens["VALUE"] and len(header_tokens["DATE"]) >= 2:
        value = min(header_tokens["VALUE"], key=lambda w: w["x0"])
        date2 = [d for d in header_tokens["DATE"] if d["x0"] > value["x0"]]
        if date2:
            date2 = min(date2, key=lambda w: w["x0"])
            columns.append(("ValueDate", value["x0"], date2["x1"]))
    
    # Find single-word columns
    if header_tokens["NARRATION"]:
        narr = header_tokens["NARRATION"][0]
        columns.append(("Remarks", narr["x0"], narr["x1"]))
    
    # Find "CHQ" + "NO" pair
    if header_tokens["CHQ"] and header_tokens["NO"]:
        chq = min(header_tokens["CHQ"], key=lambda w: w["x0"])
        no = [n for n in header_tokens["NO"] if n["x0"] > chq["x0"]]
        if no:
            no = min(no, key=lambda w: w["x0"])
            columns.append(("Reference", chq["x0"], no["x1"]))
    
    if header_tokens["DEBIT"]:
        deb = header_tokens["DEBIT"][0]
        columns.append(("Debit", deb["x0"], deb["x1"]))
    
    if header_tokens["CREDIT"]:
        cred = header_tokens["CREDIT"][0]
        columns.append(("Credit", cred["x0"], cred["x1"]))
    
    if header_tokens["BALANCE"]:
        bal = header_tokens["BALANCE"][0]
        columns.append(("Balance", bal["x0"], bal["x1"]))
    
    if len(columns) < 6:  # Need at least 6 columns for valid UBA format
        return None
    
    # Sort by x0 and build edge-based boundaries
    columns.sort(key=lambda c: c[1])
    
    cuts = {}
    for i, (name, left, right) in enumerate(columns):
        # Left boundary: previous column's right edge or page start
        left_bound = columns[i-1][2] if i > 0 else 0
        # Right boundary: next column's left edge or current right
        right_bound = columns[i+1][1] if i < len(columns) - 1 else right + 50
        cuts[name] = (left_bound, right_bound)
    
    print(f"DEBUG: UBA columns detected: {list(cuts.keys())}")
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

    # Build column list - only include columns that exist
    # Use ACTUAL header positions (not adjusted) for correct boundary calculation
    cols = [
        ("TransDate", x_trans),
    ]
    
    if x_value is not None:
        cols.append(("ValueDate", x_value))
    
    if x_ref is not None:
        cols.append(("Reference", x_ref))
    
    # For right-aligned numeric columns, use the actual header position
    # The boundary calculation will handle the midpoints correctly
    cols.extend([
        ("Debit", x_deb),      # Use actual right edge position
        ("Credit", x_cred),    # Use actual right edge position
        ("Balance", x_bal),    # Use actual right edge position
    ])
    
    # Add Originating Branch if present (comes AFTER Balance, BEFORE Remarks)
    if x_branch is not None:
        cols.append(("Branch", x_branch))
    
    # Estimate Remarks column position if not explicitly found
    if x_rem is not None:
        cols.append(("Remarks", x_rem))
    elif x_branch is not None:
        # Remarks typically comes after Branch
        cols.append(("Remarks", x_branch + 100))
    elif x_bal is not None:
        # Fallback: place Remarks after Balance
        cols.append(("Remarks", x_bal + 120))
    
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
    
    # REPAIR 1: TransDate mixed into Remarks (Ecobank/GTBank)
    # If TransDate empty but Remarks starts with a Date-like token -> Move it
    if "TransDate" in bucket and not bucket["TransDate"] and bucket.get("Remarks"):
        w_text = bucket["Remarks"][0]
        # Regex for dd-MMM-yy, dd/mm/yyyy, etc.
        if re.match(r"^\d{1,2}[-/\.]\w{3,}[-/\.]\d{2,4}$", w_text):
            bucket["TransDate"].append(bucket["Remarks"].pop(0))
            
    # REPAIR 2: Reference mixed into Remarks (GTBank)
    # If Reference empty but Remarks starts with a Ref-like token -> Move it
    if "Reference" in bucket and not bucket["Reference"] and bucket.get("Remarks"):
        w_text = bucket["Remarks"][0]
        # Use robust check (must have digits to avoid moving words like "PAYMENT")
        # looks_like_ref is defined globally in this file
        if looks_like_ref(w_text) and re.search(r"\d", w_text):
             bucket["Reference"].append(bucket["Remarks"].pop(0))

    # REPAIR 3: Branch Code mixed into Remarks (GTBank)
    # If Branch empty but Remarks starts with "001" etc. -> Move it
    if "Branch" in bucket and not bucket["Branch"] and bucket.get("Remarks"):
        w_text = bucket["Remarks"][0]
        if re.match(r"^\d{3}$", w_text):
            bucket["Branch"].append(bucket["Remarks"].pop(0))

    # REPAIR 4: Orphan Amount in Remarks (e.g. Debit shifted left into Remarks)
    if bucket.get("Remarks") and (not bucket.get("Debit") or not bucket.get("Credit")):
        w_text = bucket["Remarks"][-1]
        if re.match(r"^-?[\d,]+\.\d{2}$", w_text):
            candidate_word = None
            for w in reversed(row_words):
                if w["text"] == w_text:
                    candidate_word = w
                    break
            
            if candidate_word:
                x1 = candidate_word["x1"]
                if "Debit" in cuts and not bucket["Debit"]:
                    deb_l, deb_r = cuts["Debit"]
                    if deb_l - 30 <= x1 <= deb_r:
                        print(f"DEBUG: Moved orphan Debit from Remarks: {w_text}")
                        bucket["Debit"].append(bucket["Remarks"].pop())
                elif "Credit" in cuts and not bucket["Credit"]:
                    cred_l, cred_r = cuts["Credit"]
                    if cred_l - 30 <= x1 <= cred_r:
                        print(f"DEBUG: Moved orphan Credit from Remarks: {w_text}")
                        bucket["Credit"].append(bucket["Remarks"].pop())

    # REPAIR 5: Aggressive Numeric Snapping
    for target_col in ["Debit", "Credit", "Balance"]:
        if target_col in cuts and not bucket[target_col]:
            target_center = (cuts[target_col][0] + cuts[target_col][1]) / 2
            if bucket.get("Remarks"):
                best_word_idx = -1
                min_dist = float('inf')
                for i, w_text in enumerate(bucket["Remarks"]):
                    # FIX 1: Flexible money regex (no digit limit, optional decimal)
                    if re.match(r"^-?[\d,]+(\.\d+)?$", w_text):
                        cand_w = next((w for w in reversed(row_words) if w["text"] == w_text), None)
                        if cand_w:
                            w_center = (cand_w["x0"] + cand_w["x1"]) / 2
                            dist = abs(w_center - target_center)
                            if dist < 60 and dist < min_dist: # Increased reach to 60
                                min_dist = dist
                                best_word_idx = i
                
                if best_word_idx != -1:
                    print(f"DEBUG: Snapped {bucket['Remarks'][best_word_idx]} to {target_col} (dist={min_dist:.1f})")
                    bucket[target_col].append(bucket["Remarks"].pop(best_word_idx))

    # CLEANUP: Remove internal spaces
    for col in ["Debit", "Credit", "Balance"]:
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
        
        # Extract fields
        tdate = (r.get("TransDate") or r.get("Date") or "").strip()
        ref = (r.get("Reference") or "").strip()
        rem = (r.get("Remarks") or "").strip()
        deb = (r.get("Debit") or "").strip()
        cred = (r.get("Credit") or "").strip()
        bal = (r.get("Balance") or "").strip()
        branch = (r.get("Branch") or "").strip()
        
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
            next_deb = (next_r.get("Debit") or "").strip()
            next_cred = (next_r.get("Credit") or "").strip()
            next_bal = (next_r.get("Balance") or "").strip()
            
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
            if m_d: deb = m_d; rows[i+1]["Debit"] = ""
            m_c = try_merge_dec(cred, next_cred)
            if m_c: cred = m_c; rows[i+1]["Credit"] = ""
            m_b = try_merge_dec(bal, next_bal)
            if m_b: bal = m_b; rows[i+1]["Balance"] = ""

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
                "value_date": (r.get("ValueDate") or "").strip(),
                "reference": ref,
                "debit": deb,
                "credit": cred,
                "balance": bal,
                "remarks": rem,
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
                    current["remarks"] = (current["remarks"] + " " + rem).strip()
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

    # 1. Trans Date
    idx_td, w_td = find_word_x("TRANS")
    if not w_td: idx_td, w_td = find_word_x("DATE") # Fallback
    if w_td: bounds["TransDate"] = (w_td["x0"], w_td["x1"])

    # 2. Ref Number 
    idx_ref, w_ref = find_word_x("REF")
    if w_ref: bounds["Reference"] = (w_ref["x0"], w_ref["x1"])

    # 3. Remarks (Transaction Details)
    idx_rem, w_rem = find_word_x("DETAILS")
    if w_rem: bounds["Remarks"] = (w_rem["x0"], w_rem["x1"])

    # 4. Value Date
    # Find "VALUE" specifically
    idx_vd, w_vd = find_word_x("VALUE")
    if w_vd: bounds["ValueDate"] = (w_vd["x0"], w_vd["x1"])

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

    # 1. Tran Date
    idx_td, w_td = find_word_x("TRAN")
    if w_td:
         bounds["TransDate"] = (w_td["x0"], w_td["x1"])
    else:
         idx_td, w_td = find_word_x("DATE") # Fallback
         if w_td: bounds["TransDate"] = (w_td["x0"], w_td["x1"])

    # 2. Value Date (Find VALUE)
    idx_vd, w_vd = find_word_x("VALUE")
    if w_vd: bounds["ValueDate"] = (w_vd["x0"], w_vd["x1"])

    # 3. Narration
    idx_rem, w_rem = find_word_x("NARRATION")
    if w_rem: bounds["Remarks"] = (w_rem["x0"], w_rem["x1"])

    # 4. Tran ID & Cheque No (Optional but good for bounding)
    idx_ref, w_ref = find_word_x("ID") # TRAN ID
    if w_ref: bounds["Reference"] = (w_ref["x0"], w_ref["x1"])
    
    # 5. Withdrawals (Debit) - Match WITHDRAWAL or WITHDRAWALS or DR
    idx_deb, w_deb = find_word_x("WITHDRAWAL") 
    if not w_deb: idx_deb, w_deb = find_word_x("DR")
    if w_deb: bounds["Debit"] = (w_deb["x0"], w_deb["x1"])

    # 6. Deposits (Credit) - Match DEPOSIT or DEPOSITS or CR
    idx_cred, w_cred = find_word_x("DEPOSIT")
    if not w_cred: idx_cred, w_cred = find_word_x("CR")
    if w_cred: bounds["Credit"] = (w_cred["x0"], w_cred["x1"])

    # 7. Balance
    idx_bal, w_bal = find_word_x("BALANCE")
    if w_bal: bounds["Balance"] = (w_bal["x0"], w_bal["x1"])

    # Mandatory
    if "TransDate" not in bounds or "Debit" not in bounds:
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

    # 1. Tran. Date (tran. date in image)
    idx_td, w_td = find_word_x("TRAN")
    if w_td:
         bounds["TransDate"] = (w_td["x0"], w_td["x1"])
    else:
         idx_td, w_td = find_word_x("DATE") # Fallback
         if w_td: bounds["TransDate"] = (w_td["x0"], w_td["x1"])

    # 2. Value Date (Find VALUE)
    idx_vd, w_vd = find_word_x("VALUE")
    if w_vd: bounds["ValueDate"] = (w_vd["x0"], w_vd["x1"])

    # 3. Ref
    idx_ref, w_ref = find_word_x("REF")
    if w_ref: bounds["Reference"] = (w_ref["x0"], w_ref["x1"])

    # 4. Remarks (Transaction Details)
    idx_rem, w_rem = find_word_x("DETAILS")
    if w_rem: bounds["Remarks"] = (w_rem["x0"], w_rem["x1"])
    
    # 5. Debit
    idx_deb, w_deb = find_word_x("DEBIT") 
    if w_deb: bounds["Debit"] = (w_deb["x0"], w_deb["x1"])

    # 6. Credit
    idx_cred, w_cred = find_word_x("CREDIT")
    if w_cred: bounds["Credit"] = (w_cred["x0"], w_cred["x1"])

    # 7. Balance
    idx_bal, w_bal = find_word_x("BALANCE")
    if w_bal: bounds["Balance"] = (w_bal["x0"], w_bal["x1"])

    # Mandatory
    if "TransDate" not in bounds or "Debit" not in bounds:
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
            "value_date": "", # Skipped for now or could parse row_list[1]
            "reference": "",
            "originating_branch": "",
            "remarks": description,
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
            "originating_branch": "",
            "remarks": description,
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


def extract_ecobank_via_tables(pdf_path: Path, metadata: Dict) -> List[Dict]:
    """
    Extract Ecobank transactions using 'Date Anchor' grouping with table extraction.
    Replaces word-based logic for Ecobank to handle split decimals via row stitching.
    """
    print("DEBUG: Using Ecobank Table-Based Extraction Strategy (Date Anchor)")
    transactions = []
    
    # EcoBank Date Format is usually DD-Mon-YYYY (e.g., 31-May-2025)
    date_pattern = re.compile(r'^\d{2}-[A-Za-z]{3}-\d{4}')
    
    with pdfplumber.open(pdf_path) as pdf:
        all_rows = []
        
        # 1. Extract all table rows across all pages
        for page in pdf.pages:
            # table_settings usually help with "ghost columns"
            # vertical_strategy="text" helps when columns aren't ruled lines
            table = page.extract_table({
                "vertical_strategy": "text", 
                "horizontal_strategy": "text",
                "intersection_y_tolerance": 5 
            })
            
            if table:
                all_rows.extend(table)

    # 2. Iterate and Group (The "Stitching" Logic)
    current_txn = None
    headers_found = False
    
    # Defaults
    idx_date = 0
    idx_desc = 1
    # value date is usually 2, but we might skip it in capture if not needed
    idx_debit = 3 # Typical
    idx_credit = 4 # Typical
    idx_bal = 5 # Typical
    
    for row in all_rows:
        # Clean row: remove None values
        row = [str(x).strip() if x else '' for x in row]
        
        # Safety: Need at least a few columns
        if len(row) < 3:
            continue

        # A. Detect Header
        if not headers_found:
            row_upper = [x.upper() for x in row]
            if 'DATE' in row_upper and ('BALANCE' in row_upper or 'BAL' in row_upper):
                headers_found = True
                print(f"DEBUG: Found Ecobank Header: {row}")
                try:
                    # Find indices dynamically
                    for i, col in enumerate(row_upper):
                        if 'TRANS' in col and 'DATE' in col: idx_date = i
                        elif 'DATE' in col and i == 0: idx_date = i 
                        
                        if 'DESCRIPTION' in col or 'PARTICULARS' in col or 'NARRATION' in col: idx_desc = i
                        if 'DEBIT' in col or 'WITHDRAWAL' in col: idx_debit = i
                        if 'CREDIT' in col or 'DEPOSIT' in col: idx_credit = i
                        if 'BALANCE' in col: idx_bal = i
                except ValueError:
                    pass
            continue 

        # B. Check if this is a "New Transaction" (starts with a valid date)
        # Check boundary
        if idx_date >= len(row): continue
        
        first_col_val = row[idx_date]
        is_new_date = date_pattern.match(first_col_val)
        
        # Helper to get safe value
        def get_val(idx): return row[idx] if idx < len(row) else ""
        
        desc = get_val(idx_desc)
        debit = get_val(idx_debit)
        credit = get_val(idx_credit)
        bal = get_val(idx_bal)

        if is_new_date:
            # Save previous
            if current_txn:
                transactions.append(current_txn)
            
            # Start new
            current_txn = {
                'Date': first_col_val,
                'Description': desc,
                'Debit_Raw': debit, 
                'Credit_Raw': credit,
                'Balance_Raw': bal
            }
        
        # C. Wrapped Row (Stitching)
        elif current_txn:
            # Append text
            if desc: current_txn['Description'] += " " + desc
            if debit: current_txn['Debit_Raw'] += debit   # Concatenate for split decimals
            if credit: current_txn['Credit_Raw'] += credit
            if bal: current_txn['Balance_Raw'] += bal

    # Last one
    if current_txn:
        transactions.append(current_txn)

    # 3. Clean and Standardize for Backend using Pandas (Aggressive Cleaning)
    if not transactions:
        print("DEBUG: No transactions found for Ecobank table strategy.")
        return []

    # Rename keys to map to user's desired column names for processing then to standard output
    cleaned_txns_data = []
    for t in transactions:
        cleaned_txns_data.append({
            'Date': t['Date'],
            'Description': t['Description'],
            'Debit': t['Debit_Raw'],
            'Credit': t['Credit_Raw'],
            'Balance': t['Balance_Raw']
        })

    df = pd.DataFrame(cleaned_txns_data)
    
    # --- USER CLEANUP LOGIC START ---
    # 1. Drop the junk rows that interrupt page breaks
    invalid_noise = ['Account Statement', 'Transaction Date', 'Opening Balance', 'Page', 'Ecobank']
    # Ensure Date is string for contains check
    df = df[~df['Date'].astype(str).str.contains('|'.join(invalid_noise), case=False, na=False)]

    # 2. Fix shifted columns at page breaks
    # If Debit is empty/0 but we know it's a valid row, check if the amount shifted into the Description or Value Date
    # Note: Our dataframe keys are Date, Description, Debit, Credit, Balance (all from _Raw)
    # The user's code references 'Value Date' which we didn't map in the DF yet.
    # We will map 'Description' as the primary search area since we concatenated everything there.
    
    def recover_shifted_amounts(row):
        debit_val = str(row.get('Debit', '0')).strip()
        
        # If Debit looks empty or zero, but it's a real transaction
        if debit_val in ['', '0', '0.0', 'None', 'nan']:
            # Search the Description column for orphaned large numbers (e.g., 8,000,000.00)
            # The user's snippet checked 'Value Date' + 'Description'. 
            # We only have 'Description' populated in our keymap currently, so we use that.
            search_area = str(row.get('Description', ''))
            
            # Regex finds numbers with commas and two decimal places (e.g., 8,000,000.00)
            hidden_amount = re.search(r'\b\d{1,3}(?:,\d{3})*\.\d{2}\b', search_area)
            if hidden_amount:
                print(f"DEBUG: Recovered shifted debit: {hidden_amount.group()} from {search_area[:20]}...")
                return hidden_amount.group() # Return the found amount to the Debit column
                
        return debit_val

    # Apply the recovery function
    df['Debit'] = df.apply(recover_shifted_amounts, axis=1)
    # --- USER CLEANUP LOGIC END ---
    
    def aggressive_clean(val):
        if pd.isna(val):
            return 0.0
        
        val = str(val)
        # Strip letters, spaces, and hidden PDF characters, keep digits and dots
        # The user's regex was r'[^\d.]'
        cleaned_val = re.sub(r'[^\d.]', '', val)
        
        try:
            return float(cleaned_val) if cleaned_val else 0.0
        except ValueError:
            # If it still fails (e.g., multiple decimal points), return 0.0
            return 0.0

    # Apply aggressive cleaning as requested
    for col in ['Debit', 'Credit', 'Balance']:
        if col in df.columns:
            df[col] = df[col].apply(aggressive_clean)
        else:
            df[col] = 0.0

    final_txns = []
    
    # Convert back to standard list of dicts for the application
    for i, row in df.iterrows():
        std_txn = {
            "date": parse_date(row.get('Date', '')),
            "value_date": "", 
            "reference": "",
            "originating_branch": "",
            "remarks": row.get('Description', ''),
            "description": row.get('Description', ''),
            "debit": row['Debit'],
            "credit": row['Credit'],
            "balance": row['Balance'],
            "category": "Unallocated",
            "is_reversal": False,
            "_page": 0,
            "_row": i
        }
        final_txns.append(std_txn)

    print(f"DEBUG: Extracted {len(final_txns)} transactions via Ecobank Table strategy")
    return final_txns
             


