"""
WEMA Bank Dedicated Coordinate Extractor - Unified 2.1 (Billion-Naira Support)
"""
import pdfplumber
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
from utils import parse_date_smart


def _group_words_to_rows(words, y_tol=6.0):
    """Local row grouper: groups words within y_tol into the same row."""
    if not words:
        return []
    sorted_w = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows = []
    cur = {"top": sorted_w[0]["top"], "words": [sorted_w[0]]}
    for w in sorted_w[1:]:
        if abs(w["top"] - cur["top"]) <= y_tol:
            cur["words"].append(w)
        else:
            rows.append(cur)
            cur = {"top": w["top"], "words": [w]}
    rows.append(cur)
    return rows

def parse_wema_money(text: str) -> float | None:
    """Converts text to float. Uses length and character filtering for Reference IDs."""
    if not text: return None
    
    # Remove whitespace and punctuation for basic validation
    clean = text.replace(",", "").replace("₦", "").replace("N", "").replace(" ", "").strip()
    
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
    header_keywords = ["TRAN", "DATE", "VALUE", "NARRATION", "ID", "CHEQUE", "WITHDRAWALS", "DEPOSITS", "BALANCE", "DEBIT", "CREDIT"]
    
    header_words = [w for w in words if any(k in w["text"].upper() for k in header_keywords)]
    if len(header_words) < 5: return None
        
    tops = [round(w['top'], 1) for w in header_words]
    best_top = max(set(tops), key=tops.count)
    band = [w for w in header_words if abs(w['top'] - best_top) < 3.0]
    
    if len(band) < 4: return None

    def find_x(sub: str):
        for w in band:
            if sub in w["text"].upper(): return w["x0"], w["x1"]
        return None, None

    x_date_l, _ = find_x("TRAN")
    x_val_l, _ = find_x("VALUE")
    x_desc_l, _ = find_x("NARRATION")
    x_id_l, _   = find_x("ID")
    x_wid_l, x_wid_r = find_x("WITHDRAWALS")
    if x_wid_l is None: x_wid_l, x_wid_r = find_x("DEBIT")

    x_dep_l, x_dep_r = find_x("DEPOSITS")
    if x_dep_l is None: x_dep_l, x_dep_r = find_x("CREDIT")

    x_bal_l, _ = find_x("BALANCE")
    
    if x_date_l:
         print(f"  [WEMA-LAYOUT] Header Audit - Date: {x_date_l}, Width: {x_wid_l}, Dep: {x_dep_l}")

    if x_date_l is None or x_wid_l is None: return None

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

def extract_wema_summary(pages: List[pdfplumber.page.Page], existing_summary: Dict[str, float] = None) -> Dict[str, float]:
    """
    Extract ground-truth summary totals across First 5 and Last 5 pages (Atomic Speed Scan).
    Keeps the absolute MAXIMUM values found to ignore 'Page Totals'.
    """
    summary = existing_summary if existing_summary else {"statement_total_debit": 0.0, "statement_total_credit": 0.0}
    
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
            match_debit = re.search(r"TOTAL\s+DEBIT.*?([0-9\s,.]+)", line_txt.upper())
            if match_debit:
                val = parse_wema_money(match_debit.group(1))
                if val and val > summary.get("statement_total_debit", 0.0):
                     summary["statement_total_debit"] = val
                     print(f"  !!! [WEMA-STABLE-PATH-A] Found Max Debit: {val:,.2f} !!!")
            
            match_credit = re.search(r"TOTAL\s+CREDIT.*?([0-9\s,.]+)", line_txt.upper())
            if match_credit:
                val = parse_wema_money(match_credit.group(1))
                if val and val > summary.get("statement_total_credit", 0.0):
                     summary["statement_total_credit"] = val
                     print(f"  !!! [WEMA-STABLE-PATH-A] Found Max Credit: {val:,.2f} !!!")

        # --- PATH B: Atomic Text Weld (Stream-Guided Backup) ---
        full_text = page.extract_text()
        if full_text:
            text_lines = full_text.split('\n')
            for line in text_lines:
                # FIX: Stricter summary total regex to avoid catching partial numbers
                match_debit_b = re.search(r"TOTAL\s+DEBIT.*?([\d\s,]+\.\d{2})", line.upper())
                if match_debit_b:
                    val = parse_wema_money(match_debit_b.group(1))
                    if val and val > summary.get("statement_total_debit", 0.0):
                         summary["statement_total_debit"] = val
                         print(f"  !!! [WEMA-STABLE-PATH-B-WELD] Found Max Debit: {val:,.2f} !!!")

                match_credit_b = re.search(r"TOTAL\s+CREDIT.*?([\d\s,]+\.\d{2})", line.upper())
                if match_credit_b:
                    val = parse_wema_money(match_credit_b.group(1))
                    if val and val > summary.get("statement_total_credit", 0.0):
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
    
    try:
        # 1. EXTRACT SUMMARY TOTALS GLOBALLY (Unified 2.1 FINAL)
        summary_meta = extract_wema_summary(_pdf_handle.pages)
        metadata.update(summary_meta)
        
        summary_keywords = ["TOTAL DEBIT", "TOTAL CREDIT", "TOTAL WITHDRAWAL", "TOTAL DEPOSIT", "TOTALS", "CARRIED FORWARD"]
        
        # 2. Detect columns
        words_p0 = _pdf_handle.pages[0].extract_words()
        cuts = detect_wema_columns(words_p0)
        
        if not cuts:
             words_p1 = _pdf_handle.pages[1].extract_words() if _total_pages > 1 else []
             cuts = detect_wema_columns(words_p1)
        if not cuts:
            raise ValueError("Wema column headers not found in first 2 pages.")

        for i, page in enumerate(_pdf_handle.pages):
            if (i + 1) % 50 == 0 or i == 0:
                print(f"  [WEMA-PROGRESS] Processing Page {i+1}/{_total_pages}...")
                
            p_words = page.extract_words(x_tolerance=2, y_tolerance=2)
            
            # Recalibrate cuts
            new_cuts = detect_wema_columns(p_words)
            if new_cuts: cuts = new_cuts
            
            # Group words into visual rows using relative proximity (y_tol=6pt) instead
            # of the old fixed 5px absolute bins.  Fixed bins split same-row words that
            # differ by 6-9pt vertically (common with larger fonts / PDF baseline shifts),
            # causing the balance or debit amount to land in a separate bucket from the
            # date, which then gets dropped as "no date → not a transaction."
            row_groups = _group_words_to_rows(p_words, y_tol=6.0)
            for rg in row_groups:
                row_words = sorted(rg["words"], key=lambda x: x['x0'])
                
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
                parsed_date = parse_date_smart(date_str)
                
                # PROTECTION: Detect if this is a "Summary Header" block (often at top of page)
                is_summary_header = any(sk in row_full_text for sk in summary_keywords)
                
                # If "TOTAL" is found but no date exists, it's definitely noise.
                if is_summary_header and not parsed_date:
                    continue

                debit_val = parse_wema_money(row_data.get("debit", ""))
                credit_val = parse_wema_money(row_data.get("credit", ""))

                if parsed_date and (debit_val or credit_val):
                    # ADDITIONAL GUARD: If we have a massive number but no description or small description, 
                    # it might be a misaligned total from the header.
                    desc = row_data.get("description", "").strip()
                    
                    # If date exists but it's clearly a summary row (e.g. "Opening Balance" row might have a date printed in header)
                    if "OPENING BAL" in row_full_text or "CLOSING BAL" in row_full_text:
                        continue

                    if row_data.get("tran_id") and not any(c.isdigit() for c in row_data["tran_id"]):
                         desc = (desc + " " + row_data["tran_id"]).strip()
                    
                    # LOG BILLIONS FOR VERIFICATION
                    if (debit_val or 0) > 1000000000 or (credit_val or 0) > 1000000000:
                         print(f"  [WEMA-BILLION] Page {i+1}: Captured {debit_val or credit_val:,.2f}")

                    txns.append({
                        "date": parsed_date,
                        "description": desc,
                        "reference": row_data.get("tran_id", "").strip(),
                        "debit": debit_val or 0.0,
                        "credit": credit_val or 0.0,
                        "balance": parse_wema_money(row_data.get("balance", "")) or 0.0,
                        "page": i + 1
                    })

    finally:
        if not pdf: _pdf_handle.close()

    _elapsed = time.time() - _start
    d = sum(t['debit'] for t in txns)
    c = sum(t['credit'] for t in txns)
    print(f">>> [WEMA ENGINE 2.1] Done: {len(txns)} txns, Debit={d:,.2f}, Credit={c:,.2f} in {_elapsed:.1f}s")
    return txns, metadata
