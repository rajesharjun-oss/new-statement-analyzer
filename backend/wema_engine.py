"""
WEMA Bank Dedicated Coordinate Extractor - Unified 2.1 (Billion-Naira Support)
"""
import pdfplumber
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
from utils import parse_date_smart

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    fitz = None
    PYMUPDF_AVAILABLE = False

def parse_wema_money(text: str) -> float | None:
    """Converts text to float. Uses length and character filtering for Reference IDs."""
    if not text: return None
    
    # Remove whitespace and punctuation for basic validation
    clean = text.replace(",", "").replace("₦", "").replace("N", "")
    clean = re.sub(r"\s+", "", clean).strip()
    
    # Filter out obvious non-financial noise
    if not any(c.isdigit() for c in clean): return None
    
    # REFERENCE ID PROTECTION (Unified 2.1)
    # Wema Ref IDs/Tran IDs often look like N-10153018596 or have letters.
    # If it contains any letter, it's a Reference ID, NOT an amount.
    if any(c.isalpha() for c in clean):
        return None

    try:
        val = float(clean)
        # Even NGN 999 Billion (999,999,999,999.99) is only 12 digits before decimal.
        # We ignore numeric strings with more than 15 digits total (protect against long phone/IDs)
        digit_count = sum(c.isdigit() for c in clean)
        if digit_count > 15:
            return None 
            
        return val
    except:
        return None

def detect_wema_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    header_keywords = ["TRAN", "DATE", "VALUE", "TRANSACTION", "NARRATION", "DESCRIPTION", "REMARKS", "DETAILS", "PARTICULARS", "ID", "REFERENCE", "REF", "CHEQUE", "WITHDRAWALS", "DEPOSITS", "BALANCE", "DEBIT", "CREDIT"]
    
    header_words = [w for w in words if any(k in w["text"].upper() for k in header_keywords)]
    if len(header_words) < 5: return None
        
    tops = [round(w['top'], 1) for w in header_words]
    best_top = max(set(tops), key=tops.count)
    band = sorted(
        [w for w in header_words if abs(w['top'] - best_top) < 3.0],
        key=lambda w: w["x0"],
    )
    
    if len(band) < 4: return None

    def find_x(sub: str):
        for w in band:
            if sub in w["text"].upper(): return w["x0"], w["x1"]
        return None, None

    x_date_l, _ = find_x("TRAN")
    x_val_l, _ = find_x("VALUE")
    x_desc_l, _ = find_x("TRANSACTION")
    if x_desc_l is None: x_desc_l, _ = find_x("NARRATION")
    if x_desc_l is None: x_desc_l, _ = find_x("DESCRIPTION")
    if x_desc_l is None: x_desc_l, _ = find_x("REMARKS")
    if x_desc_l is None: x_desc_l, _ = find_x("DETAILS")
    if x_desc_l is None: x_desc_l, _ = find_x("PARTICULARS")
    x_id_l, _   = find_x("ID")
    if x_id_l is None: x_id_l, _ = find_x("REFERENCE")
    if x_id_l is None: x_id_l, _ = find_x("REF")
    x_wid_l, x_wid_r = find_x("WITHDRAWALS")
    if x_wid_l is None: x_wid_l, x_wid_r = find_x("DEBIT")

    x_dep_l, x_dep_r = find_x("DEPOSITS")
    if x_dep_l is None: x_dep_l, x_dep_r = find_x("CREDIT")

    x_bal_l, _ = find_x("BALANCE")
    
    if x_date_l and os.getenv("WEMA_DEBUG_LAYOUT"):
         print(f"  [WEMA-LAYOUT] Header Audit - Date: {x_date_l}, Width: {x_wid_l}, Dep: {x_dep_l}")

    if x_date_l is None or x_wid_l is None or x_dep_l is None or x_bal_l is None: return None
    if x_desc_l is None:
        x_desc_l = x_date_l + 55

    # Column Slices (WIDENED for Billion-Naira Support - Extreme -32)
    cuts = {
        "date": (x_date_l - 4, x_date_l + 52),
        "description": (x_desc_l, x_wid_l - 28), 
        "debit": (x_wid_l - 32, x_dep_l - 5),    
        "credit": (x_dep_l - 8, x_bal_l - 8),   
        "balance": (x_bal_l - 12, 1000.0)
    }
    
    if x_id_l:
        cuts["tran_id"] = (x_id_l - 2, x_wid_l - 5)
        cuts["description"] = (x_desc_l, x_id_l - 2)

    return cuts

def pymupdf_wema_words(doc: Any, page_index: int) -> List[Dict[str, Any]]:
    """Return visible-page words in pdfplumber's word shape."""
    page = doc[page_index]
    page_height = float(page.rect.height)
    words = []
    for w in page.get_text("words"):
        text = (w[4] or "").strip()
        if not text:
            continue
        words.append({
            "text": text,
            "x0": float(w[0]),
            "top": float(w[1]),
            "x1": float(w[2]),
            "bottom": float(w[3]),
            "doctop": float(w[1]) + page_index * page_height,
        })
    return words

def get_wema_header_scan_limit(total_pages: int) -> int:
    try:
        configured = int(os.getenv("WEMA_HEADER_SCAN_PAGES", "12"))
    except (TypeError, ValueError):
        configured = 12
    configured = max(2, min(configured, 50))
    return min(max(total_pages, 0), configured)


def _wema_words_for_page(pdf_handle: Any, fast_doc: Any, use_fast_words: bool, page_index: int) -> List[Dict[str, Any]]:
    if use_fast_words and fast_doc is not None:
        return pymupdf_wema_words(fast_doc, page_index)
    return pdf_handle.pages[page_index].extract_words(x_tolerance=2, y_tolerance=2)


def detect_wema_columns_in_pages(
    pdf_handle: Any,
    fast_doc: Any = None,
    use_fast_words: bool = False,
    max_pages: int | None = None,
) -> Tuple[Dict[str, Tuple[float, float]] | None, int | None]:
    total_pages = len(pdf_handle.pages)
    scan_limit = min(total_pages, max_pages or get_wema_header_scan_limit(total_pages))
    for page_index in range(scan_limit):
        try:
            words = _wema_words_for_page(pdf_handle, fast_doc, use_fast_words, page_index)
        except Exception as exc:
            print(f"  [WEMA-HEADER] Could not read page {page_index + 1}: {exc}")
            continue
        cuts = detect_wema_columns(words or [])
        if cuts:
            return cuts, page_index
    return None, None


WEMA_DESC_NOISE_TOKENS = {
    "TRAN", "TRANS", "TRANSACTION", "DATE", "VALUE", "NARRATION",
    "ID", "CHEQUE", "WITHDRAWALS", "WITHDRAWAL", "DEPOSITS", "DEPOSIT",
    "DEBIT", "CREDIT", "BALANCE", "OPENING", "CLOSING", "TOTAL", "TOTALS",
}


def _is_wema_date_token(text: str) -> bool:
    token = (text or "").strip().strip(".,;:")
    if not token:
        return False
    if re.fullmatch(r"20\d{2}", token):
        return True
    if re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]?", token):
        return True
    if re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", token):
        return True
    if re.fullmatch(r"\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}", token):
        return True
    if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", token):
        return True
    return False


def infer_wema_statement_year(metadata: Dict[str, Any], pages: List[pdfplumber.page.Page]) -> int | None:
    candidates = [
        metadata.get("period"),
        metadata.get("period_start"),
        metadata.get("period_end"),
        metadata.get("statement_period"),
    ]
    try:
        if pages:
            candidates.append(pages[0].extract_text() or "")
    except Exception:
        pass
    for candidate in candidates:
        match = re.search(r"\b(20\d{2})\b", str(candidate or ""))
        if match:
            return int(match.group(1))
    return None


def parse_wema_date_token(date_text: str, statement_year: int | None) -> str | None:
    parsed = parse_date_smart(date_text)
    if parsed:
        return parsed
    text = (date_text or "").strip()
    match = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})[-/]?", text)
    if match and statement_year:
        candidate = f"{match.group(1).zfill(2)}-{match.group(2).zfill(2)}-{statement_year}"
        return parse_date_smart(candidate)
    return None


def clean_wema_description(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip(" -|;:,\t")
    if not text:
        return ""
    parts = []
    for part in text.split():
        stripped = part.strip(" -|;:,\t")
        upper = stripped.upper().replace(".", "")
        if not stripped:
            continue
        if upper in WEMA_DESC_NOISE_TOKENS:
            continue
        if _is_wema_date_token(stripped):
            continue
        parts.append(stripped)
    cleaned = " ".join(parts)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|;:,\t")
    return cleaned


def build_wema_description(
    row_words: List[Dict[str, Any]],
    cuts: Dict[str, Tuple[float, float]],
    row_data: Dict[str, str],
) -> str:
    desc_direct = clean_wema_description(row_data.get("description", ""))
    ref_direct = clean_wema_description(row_data.get("tran_id", ""))
    if desc_direct:
        if ref_direct and ref_direct not in desc_direct:
            return clean_wema_description(f"{desc_direct} {ref_direct}")
        return desc_direct

    date_end = cuts.get("date", (0.0, 0.0))[1]
    debit_start = cuts.get("debit", (1000.0, 1000.0))[0]
    fallback_parts: List[str] = []
    for word in sorted(row_words, key=lambda w: w.get("x0", 0.0)):
        text = str(word.get("text", "")).strip()
        if not text:
            continue
        if word.get("x0", 0.0) < date_end - 4:
            continue
        if word.get("x1", 0.0) > debit_start - 2:
            continue
        candidate = clean_wema_description(text)
        if candidate:
            fallback_parts.append(candidate)
    fallback = clean_wema_description(" ".join(fallback_parts))
    if fallback:
        if ref_direct and ref_direct not in fallback:
            return clean_wema_description(f"{fallback} {ref_direct}")
        return fallback
    return ref_direct

def repair_wema_transaction_descriptions(txns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for txn in txns:
        desc = clean_wema_description(txn.get("description", ""))
        ref = clean_wema_description(txn.get("reference", ""))
        if not desc and ref:
            desc = ref
        txn["description"] = desc
        txn["remarks"] = desc or ref
    return txns

def extract_wema_summary(pages: List[pdfplumber.page.Page], existing_summary: Dict[str, float] = None) -> Dict[str, float]:
    """
    Extract ground-truth summary totals across First 5 and Last 5 pages (Atomic Speed Scan).
    Keeps the absolute MAXIMUM values found to ignore 'Page Totals'.
    """
    summary = {
        "statement_total_debit": (existing_summary or {}).get("statement_total_debit"),
        "statement_total_credit": (existing_summary or {}).get("statement_total_credit"),
    }
    
    # Speed Optimization (V6): Scan only head and tail pages for corporate totals
    # This bypasses the 10-minute scan bottleneck for 1,238-page PDFs
    scan_pages = pages[:5] + pages[-5:] if len(pages) > 10 else pages
    
    for i, page in enumerate(scan_pages):
        # --- PATH A: Word-to-Row Bucketing (Coordinate-Guided) ---
        words = page.extract_words(x_tolerance=3, y_tolerance=3)
        rows_dict = {}
        for w in words:
            # Vertical Stabilization (V6): Bucket within 5 pixels to 'weld' misaligned label/values
            y = int(w['top'] / 5) * 5
            if y not in rows_dict: rows_dict[y] = []
            rows_dict[y].append(w)
            
        for y in sorted(rows_dict.keys()):
            row_words = sorted(rows_dict[y], key=lambda x: x['x0'])
            line_txt = " ".join([w['text'] for w in row_words])
            
            # Robust Regex Capture (V6): Support digit splitting and space-agnosticism
            import re
            line_txt_u = line_txt.upper()
            debit_segment = line_txt_u
            if "TOTAL DEBIT" in line_txt_u and "TOTAL CREDIT" in line_txt_u:
                debit_segment = line_txt_u.split("TOTAL CREDIT", 1)[0]
            match_debit = re.search(r"TOTAL\s+DEBIT.*?([0-9\s,.]+)", debit_segment)
            if match_debit:
                val = parse_wema_money(match_debit.group(1))
                cur_debit = summary.get("statement_total_debit")
                if val is not None and (cur_debit is None or val > cur_debit):
                     summary["statement_total_debit"] = val
                     print(f"  !!! [WEMA-STABLE-PATH-A] Found Max Debit: {val:,.2f} !!!")
            
            match_credit = re.search(r"TOTAL\s+CREDIT.*?([0-9\s,.]+)", line_txt_u)
            if match_credit:
                val = parse_wema_money(match_credit.group(1))
                cur_credit = summary.get("statement_total_credit")
                if val is not None and (cur_credit is None or val > cur_credit):
                     summary["statement_total_credit"] = val
                     print(f"  !!! [WEMA-STABLE-PATH-A] Found Max Credit: {val:,.2f} !!!")

            # Structured-topline capture for layouts where totals are split/wrapped, e.g.:
            # 45,567,533,642.  45,568,587,440.13
            # Total Debit:      Total Credit:
            # ... 72            (decimal tail for debit)
            if "TOTAL DEBIT" in line_txt_u and "TOTAL CREDIT" in line_txt_u:
                debit_label_x = None
                credit_label_x = None
                for w in row_words:
                    txt_u = w["text"].upper()
                    if "DEBIT" in txt_u and debit_label_x is None:
                        debit_label_x = w["x0"]
                    if "CREDIT" in txt_u and credit_label_x is None:
                        credit_label_x = w["x0"]

                if debit_label_x is not None and credit_label_x is not None:
                    near_words = [
                        w for w in words
                        if (y - 15) <= int(w["top"] / 5) * 5 <= (y + 15)
                    ]

                    debit_parts = []
                    credit_main = None

                    for w in sorted(near_words, key=lambda z: (z["x0"], z["top"])):
                        txt = (w.get("text") or "").strip()
                        if not txt:
                            continue
                        if re.fullmatch(r"[\d,]+(?:\.\d*)?", txt) is None:
                            continue

                        if debit_label_x + 70 <= w["x0"] < credit_label_x - 30:
                            debit_parts.append((txt, w["top"], w["x0"]))
                        elif w["x0"] >= credit_label_x + 40:
                            # Choose the widest/rightmost money-like token near Total Credit
                            cur = parse_wema_money(txt)
                            if cur is not None:
                                if credit_main is None or cur > credit_main:
                                    credit_main = cur

                    if debit_parts:
                        # Prefer the largest numeric chunk as main debit value.
                        debit_parts_sorted = sorted(
                            debit_parts,
                            key=lambda p: parse_wema_money(p[0]) or 0.0,
                            reverse=True,
                        )
                        main_txt, main_top, main_x = debit_parts_sorted[0]
                        main_val = parse_wema_money(main_txt)
                        if main_val is not None:
                            # Recover split decimal tail like ". 72" captured as nearby tiny token.
                            if main_txt.endswith("."):
                                frac = None
                                for txt, top, x0 in debit_parts:
                                    if x0 <= main_x + 25 and abs(top - main_top) <= 18 and re.fullmatch(r"\d{1,2}", txt):
                                        frac = txt
                                        break
                                if frac:
                                    try:
                                        main_val = float(f"{int(main_val)}.{frac.zfill(2)}")
                                    except Exception:
                                        pass

                            cur_debit = summary.get("statement_total_debit")
                            if cur_debit is None or main_val > cur_debit:
                                summary["statement_total_debit"] = main_val
                                print(f"  !!! [WEMA-TOPLINE] Found Max Debit: {main_val:,.2f} !!!")

                    if credit_main is not None:
                        cur_credit = summary.get("statement_total_credit")
                        if cur_credit is None or credit_main > cur_credit:
                            summary["statement_total_credit"] = credit_main
                            print(f"  !!! [WEMA-TOPLINE] Found Max Credit: {credit_main:,.2f} !!!")

        # --- PATH B: Atomic Text Weld (Stream-Guided Backup) ---
        full_text = page.extract_text()
        if full_text:
            full_text_u = full_text.upper()
            # Whole-page resilient capture for wrapped decimals, e.g. 45,567,533,642.\n72
            for label, key in [("TOTAL DEBIT", "statement_total_debit"), ("TOTAL CREDIT", "statement_total_credit")]:
                m_full = re.search(rf"{label}[^\d]{{0,60}}([\d,\s]+\.\s*\d{{2}})", full_text_u, flags=re.S)
                if m_full:
                    val = parse_wema_money(m_full.group(1))
                    cur = summary.get(key)
                    if val is not None and (cur is None or val > cur):
                        summary[key] = val
                        print(f"  !!! [WEMA-STABLE-PATH-BLOCK] Found Max {label.title()}: {val:,.2f} !!!")

            text_lines = full_text.split('\n')
            for line in text_lines:
                # FIX: Stricter summary total regex to avoid catching partial numbers
                line_u = line.upper()
                debit_line_segment = line_u
                if "TOTAL DEBIT" in line_u and "TOTAL CREDIT" in line_u:
                    debit_line_segment = line_u.split("TOTAL CREDIT", 1)[0]
                match_debit_b = re.search(r"TOTAL\s+DEBIT.*?([\d\s,]+\.\d{2})", debit_line_segment)
                if match_debit_b:
                    val = parse_wema_money(match_debit_b.group(1))
                    cur_debit = summary.get("statement_total_debit")
                    if val is not None and (cur_debit is None or val > cur_debit):
                         summary["statement_total_debit"] = val
                         print(f"  !!! [WEMA-STABLE-PATH-B-WELD] Found Max Debit: {val:,.2f} !!!")

                match_credit_b = re.search(r"TOTAL\s+CREDIT.*?([\d\s,]+\.\d{2})", line_u)
                if match_credit_b:
                    val = parse_wema_money(match_credit_b.group(1))
                    cur_credit = summary.get("statement_total_credit")
                    if val is not None and (cur_credit is None or val > cur_credit):
                         summary["statement_total_credit"] = val
                         print(f"  !!! [WEMA-STABLE-PATH-B-WELD] Found Max Credit: {val:,.2f} !!!")

                          
    return summary

def extract_wema_via_coordinates(pdf_path: Path, metadata: Dict[str, Any], pdf: pdfplumber.PDF = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    import time
    _start = time.time()
    txns = []
    
    print("\n" + "#"*40)
    print("!!! [WEMA ENGINE 2.1] ACTIVE !!!")
    print("#"*40 + "\n")
    
    _pdf_handle = pdf if pdf else pdfplumber.open(pdf_path)
    _total_pages = len(_pdf_handle.pages)
    print(f"\n>>> [WEMA ENGINE 2.1] Extraction Started for: {pdf_path.name} ({_total_pages} pages)")
    fast_doc = None
    use_fast_words = False
    if _total_pages > 100 and PYMUPDF_AVAILABLE:
        try:
            fast_doc = fitz.open(pdf_path)
            use_fast_words = True
            print("  [WEMA-FAST] Using PyMuPDF visible-page word extraction.")
        except Exception as exc:
            print(f"  [WEMA-FAST] PyMuPDF unavailable for this file: {exc}")
            fast_doc = None
            use_fast_words = False
    
    try:
        # 1. EXTRACT SUMMARY TOTALS GLOBALLY (Unified 2.1 FINAL)
        summary_meta = extract_wema_summary(_pdf_handle.pages, existing_summary={
            "statement_total_debit": metadata.get("statement_total_debit"),
            "statement_total_credit": metadata.get("statement_total_credit"),
        })
        for k, v in (summary_meta or {}).items():
            if v is not None:
                metadata[k] = v
        
        statement_year = infer_wema_statement_year(metadata, _pdf_handle.pages)
        summary_keywords = ["TOTAL DEBIT", "TOTAL CREDIT", "TOTAL WITHDRAWAL", "TOTAL DEPOSIT", "TOTALS", "CARRIED FORWARD"]
        
        # 2. Detect columns. Some Wema statements place account-summary pages before the ledger,
        # so scan deeper than the first two pages before giving up.
        header_scan_limit = get_wema_header_scan_limit(_total_pages)
        cuts, header_page_idx = detect_wema_columns_in_pages(
            _pdf_handle,
            fast_doc=fast_doc,
            use_fast_words=use_fast_words,
            max_pages=header_scan_limit,
        )
        if not cuts:
            raise ValueError(f"Wema column headers not found in first {header_scan_limit} pages.")
        if header_page_idx:
            print(f"  [WEMA-HEADER] Transaction header found on page {header_page_idx + 1}.")

        pending_desc_parts: List[str] = []
        last_txn = None
        for i, page in enumerate(_pdf_handle.pages):
            if (i + 1) % 50 == 0 or i == 0:
                print(f"  [WEMA-PROGRESS] Processing Page {i+1}/{_total_pages}...")
            last_txn_date = None
                
            p_words = pymupdf_wema_words(fast_doc, i) if use_fast_words and fast_doc is not None else page.extract_words(x_tolerance=2, y_tolerance=2)
            
            # Recalibrate cuts
            new_cuts = detect_wema_columns(p_words)
            if new_cuts: cuts = new_cuts
            
            rows_dict = {}
            for w in p_words:
                y = int(w['top'] / 5) * 5 
                if y not in rows_dict: rows_dict[y] = []
                rows_dict[y].append(w)
                
            for y in sorted(rows_dict.keys()):
                row_words = sorted(rows_dict[y], key=lambda x: x['x0'])
                
                row_data = {k: "" for k in cuts.keys()}
                for w in row_words:
                    # AREA-BASED INTERSECTION (Unified 2.1 STABLE)
                    # Instead of midpoint, we check if the word overlaps with the column zone
                    for col_name, (c_start, c_end) in cuts.items():
                        overlap = min(w['x1'], c_end) - max(w['x0'], c_start)
                        if overlap > (w['x1'] - w['x0']) * 0.5: # Over 50% overlap
                            row_data[col_name] = (row_data[col_name] + " " + w['text']).strip()
                            break
                            
                # Skip noise and summary rows (only if it's NOT a transaction)
                row_full_text = " ".join(row_data.values()).upper()
                
                # REINFORCE: The summary rows usually don't have dates in the transaction region.
                date_str = row_data.get("date", "")
                parsed_date = parse_wema_date_token(date_str, statement_year)
                if parsed_date:
                    last_txn_date = parsed_date
                
                # PROTECTION: Detect if this is a "Summary Header" block (often at top of page)
                is_summary_header = any(sk in row_full_text for sk in summary_keywords)
                
                # If "TOTAL" is found but no date exists, it's definitely noise.
                if is_summary_header and not parsed_date:
                    continue

                debit_val = parse_wema_money(row_data.get("debit", ""))
                credit_val = parse_wema_money(row_data.get("credit", ""))
                balance_val = parse_wema_money(row_data.get("balance", "")) or 0.0
                row_desc = build_wema_description(row_words, cuts, row_data)

                if not parsed_date and not (debit_val or credit_val) and row_desc:
                    if last_txn is not None and last_txn.get("page") == i + 1:
                        merged_desc = clean_wema_description((last_txn.get("description", "") + " " + row_desc).strip())
                        if merged_desc:
                            last_txn["description"] = merged_desc
                            last_txn["remarks"] = merged_desc
                    elif last_txn is not None:
                        pending_desc_parts.append(row_desc)
                    continue

                if not parsed_date and (debit_val or credit_val):
                    desc_probe = row_data.get("description", "").strip()
                    ref_probe = row_data.get("tran_id", "").strip()
                    probe_text = f"{desc_probe} {ref_probe}".strip()
                    has_alpha_context = any(c.isalpha() for c in probe_text)
                    compact_full = re.sub(r"\s+", " ", row_full_text).strip()
                    looks_page_counter = compact_full.isdigit() and len(compact_full) <= 4
                    has_header_noise = any(
                        kw in row_full_text
                        for kw in ["ADDRESS", "ACCOUNT", "STATEMENT", "TOTAL", "OPENING", "CLOSING", "CURRENT BAL", "EFF."]
                    )
                    has_large_amount = max((debit_val or 0.0), (credit_val or 0.0)) >= 1000000.0
                    stmt_d = metadata.get("statement_total_debit")
                    stmt_c = metadata.get("statement_total_credit")
                    summary_totals_echo = False
                    if stmt_d and abs((debit_val or 0.0) - float(stmt_d)) <= 0.01 and stmt_c and abs(balance_val - float(stmt_c)) <= 0.01:
                        summary_totals_echo = True

                    if (
                        last_txn_date
                        and not looks_page_counter
                        and not has_header_noise
                        and not summary_totals_echo
                        and (has_alpha_context or balance_val > 0.0 or has_large_amount)
                    ):
                        parsed_date = last_txn_date

                if parsed_date and (debit_val or credit_val):
                    # ADDITIONAL GUARD: If we have a massive number but no description or small description, 
                    # it might be a misaligned total from the header.
                    desc = row_desc
                    if pending_desc_parts:
                        desc = clean_wema_description(" ".join(pending_desc_parts + [desc]))
                        pending_desc_parts = []
                    if not desc:
                        desc = clean_wema_description(row_data.get("tran_id", ""))
                    
                    # If date exists but it's clearly a summary row (e.g. "Opening Balance" row might have a date printed in header)
                    if "OPENING BAL" in row_full_text or "CLOSING BAL" in row_full_text:
                        continue

                    
                    # LOG BILLIONS FOR VERIFICATION
                    if (debit_val or 0) > 1000000000 or (credit_val or 0) > 1000000000:
                         print(f"  [WEMA-BILLION] Page {i+1}: Captured {debit_val or credit_val:,.2f}")

                    txns.append({
                        "date": parsed_date,
                        "description": desc,
                        "remarks": desc,
                        "reference": row_data.get("tran_id", "").strip(),
                        "debit": debit_val or 0.0,
                        "credit": credit_val or 0.0,
                        "balance": balance_val,
                        "page": i + 1
                    })
                    last_txn = txns[-1]
                    last_txn_date = parsed_date

    finally:
        if fast_doc is not None:
            try:
                fast_doc.close()
            except Exception:
                pass
        if not pdf: _pdf_handle.close()

    # ── Balance inference: fill B=0 holes from known neighbours ──────────────
    # Some multi-line narration rows have their balance on a different PDF line
    # from the date/amount row, so balance arrives as 0.0.  We run alternating
    # forward / backward passes until the chain converges (or we hit 20 iters).
    def _infer_balances(txns, max_iter=20):
        changed = True
        itr = 0
        while changed and itr < max_iter:
            changed = False
            itr += 1
            # Forward: B[i] = B[i-1] - D[i] + C[i]
            for i in range(1, len(txns)):
                if txns[i]['balance'] == 0.0 and txns[i-1]['balance'] != 0.0:
                    inferred = round(txns[i-1]['balance'] - txns[i]['debit'] + txns[i]['credit'], 2)
                    txns[i]['balance'] = inferred
                    changed = True
            # Backward: B[i] = B[i+1] + D[i+1] - C[i+1]
            for i in range(len(txns)-2, -1, -1):
                if txns[i]['balance'] == 0.0 and txns[i+1]['balance'] != 0.0:
                    inferred = round(txns[i+1]['balance'] + txns[i+1]['debit'] - txns[i+1]['credit'], 2)
                    txns[i]['balance'] = inferred
                    changed = True
        n_zero = sum(1 for t in txns if t['balance'] == 0.0)
        print(f"  [WEMA BAL-INFER] {itr} passes, {n_zero} still-zero balances remain")
        return txns

    def _insert_chain_adjustments(txns: List[Dict[str, Any]], min_gap: float = 100000.0):
        """
        If the running balance drops/rises by a large amount not explained by the current row's
        debit/credit, insert an explicit inferred adjustment row before that row.
        This preserves a mathematically consistent chain for statements with split/missed amount rows.
        """
        if not txns:
            return txns, {"count": 0, "debit": 0.0, "credit": 0.0}

        adjusted = [txns[0]]
        prev_bal = txns[0].get("balance", 0.0) or 0.0
        adj_count = 0
        adj_debit = 0.0
        adj_credit = 0.0

        for i in range(1, len(txns)):
            row = txns[i]
            cur_bal = row.get("balance", 0.0) or 0.0
            row_debit = row.get("debit", 0.0) or 0.0
            row_credit = row.get("credit", 0.0) or 0.0

            if prev_bal != 0.0 and cur_bal != 0.0:
                expected_bal = round(prev_bal - row_debit + row_credit, 2)
                gap = round(cur_bal - expected_bal, 2)
                if abs(gap) >= min_gap:
                    if gap < 0:
                        inf_debit = round(-gap, 2)
                        inf_credit = 0.0
                        inf_desc = "Inferred WEMA chain adjustment (missing debit row in source layout)."
                    else:
                        inf_debit = 0.0
                        inf_credit = round(gap, 2)
                        inf_desc = "Inferred WEMA chain adjustment (missing credit row in source layout)."

                    inferred_balance = round(prev_bal - inf_debit + inf_credit, 2)
                    inferred = {
                        "date": row.get("date", ""),
                        "description": inf_desc,
                        "reference": "INFERRED_CHAIN_ADJUSTMENT",
                        "debit": inf_debit,
                        "credit": inf_credit,
                        "balance": inferred_balance,
                        "page": row.get("page"),
                        "_inferred": True,
                    }
                    adjusted.append(inferred)
                    prev_bal = inferred_balance
                    adj_count += 1
                    adj_debit += inf_debit
                    adj_credit += inf_credit

            adjusted.append(row)
            prev_bal = cur_bal if cur_bal != 0.0 else prev_bal

        return adjusted, {
            "count": adj_count,
            "debit": round(adj_debit, 2),
            "credit": round(adj_credit, 2),
        }

    txns = repair_wema_transaction_descriptions(txns)
    if txns:
        txns = _infer_balances(txns)
        txns, chain_adj = _insert_chain_adjustments(txns)
        if chain_adj["count"] > 0:
            metadata["chain_adjustment_rows"] = chain_adj["count"]
            metadata["chain_adjustment_debit"] = chain_adj["debit"]
            metadata["chain_adjustment_credit"] = chain_adj["credit"]
            print(
                "  [WEMA CHAIN-ADJ] Inserted "
                f"{chain_adj['count']} inferred rows "
                f"(Debit={chain_adj['debit']:,.2f}, Credit={chain_adj['credit']:,.2f})."
            )

        # Final tiny reconciliation against statement totals (kobo drift only).
        stmt_debit = metadata.get("statement_total_debit")
        stmt_credit = metadata.get("statement_total_credit")
        if stmt_debit is not None and stmt_credit is not None:
            cur_debit = round(sum((t.get("debit") or 0.0) for t in txns), 2)
            cur_credit = round(sum((t.get("credit") or 0.0) for t in txns), 2)
            opening_bal = metadata.get("opening_balance")
            closing_bal = metadata.get("closing_balance")
            if opening_bal is not None and closing_bal is not None:
                extracted_close = round(float(opening_bal) + cur_credit - cur_debit, 2)
                summary_close = round(float(opening_bal) + float(stmt_credit) - float(stmt_debit), 2)
                if (
                    abs(extracted_close - float(closing_bal)) <= 1.0
                    and abs(summary_close - float(closing_bal)) > 1.0
                    and abs(float(stmt_debit) - float(stmt_credit)) <= 0.01
                    and abs(float(stmt_debit) - cur_debit) > 1.0
                ):
                    metadata["statement_total_debit"] = None
                    metadata["wema_missing_debit_total"] = True
                    stmt_debit = None
                    print(
                        "  [WEMA SUMMARY] Ignoring copied debit total; source text only exposes credit total."
                    )

        stmt_debit = metadata.get("statement_total_debit")
        stmt_credit = metadata.get("statement_total_credit")
        if stmt_debit is not None and stmt_credit is not None:
            cur_debit = round(sum((t.get("debit") or 0.0) for t in txns), 2)
            cur_credit = round(sum((t.get("credit") or 0.0) for t in txns), 2)
            debit_gap = round(float(stmt_debit) - cur_debit, 2)
            credit_gap = round(float(stmt_credit) - cur_credit, 2)

            small_gap = lambda g: abs(g) >= 0.01 and abs(g) <= 1.0
            if small_gap(debit_gap) and abs(credit_gap) <= 0.01 and debit_gap > 0:
                base_bal = txns[-1].get("balance", 0.0) or 0.0
                txns.append({
                    "date": txns[-1].get("date", ""),
                    "description": "Inferred WEMA rounding adjustment (debit).",
                    "reference": "INFERRED_ROUNDING_ADJUSTMENT",
                    "debit": debit_gap,
                    "credit": 0.0,
                    "balance": round(base_bal - debit_gap, 2),
                    "page": txns[-1].get("page"),
                    "_inferred": True,
                })
                metadata["rounding_adjustment_debit"] = debit_gap
                print(f"  [WEMA ROUND-ADJ] Added debit {debit_gap:.2f} to align statement totals.")
            elif small_gap(credit_gap) and abs(debit_gap) <= 0.01 and credit_gap > 0:
                base_bal = txns[-1].get("balance", 0.0) or 0.0
                txns.append({
                    "date": txns[-1].get("date", ""),
                    "description": "Inferred WEMA rounding adjustment (credit).",
                    "reference": "INFERRED_ROUNDING_ADJUSTMENT",
                    "debit": 0.0,
                    "credit": credit_gap,
                    "balance": round(base_bal + credit_gap, 2),
                    "page": txns[-1].get("page"),
                    "_inferred": True,
                })
                metadata["rounding_adjustment_credit"] = credit_gap
                print(f"  [WEMA ROUND-ADJ] Added credit {credit_gap:.2f} to align statement totals.")

    _elapsed = time.time() - _start
    d = sum(t['debit'] for t in txns)
    c = sum(t['credit'] for t in txns)
    print(f">>> [WEMA ENGINE 2.1] Done: {len(txns)} txns, Debit={d:,.2f}, Credit={c:,.2f} in {_elapsed:.1f}s")
    return txns, metadata
