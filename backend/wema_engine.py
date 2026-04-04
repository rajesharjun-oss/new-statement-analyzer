"""
WEMA Bank Dedicated Coordinate Extractor - Unified 2.1 (Billion-Naira Support)
"""
import pdfplumber
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
from utils import parse_date_smart

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
    header_keywords = ["TRAN", "DATE", "VALUE", "NARRATION", "ID", "CHEQUE", "WITHDRAWALS", "DEPOSITS", "BALANCE"]
    
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
    x_dep_l, x_dep_r = find_x("DEPOSITS")
    x_bal_l, _ = find_x("BALANCE")

    if x_date_l is None or x_wid_l is None: return None

    # Column Slices (WIDENED for Billion-Naira Support)
    cuts = {
        "date": (x_date_l - 4, x_date_l + 52),
        "description": (x_desc_l, x_wid_l - 8), 
        "debit": (x_wid_l - 12, x_dep_l - 5),    
        "credit": (x_dep_l - 8, x_bal_l - 8),   
        "balance": (x_bal_l - 12, 1000.0)
    }
    
    if x_id_l:
        cuts["tran_id"] = (x_id_l - 2, x_wid_l - 5)
        cuts["description"] = (x_desc_l, x_id_l - 2)

    return cuts

def extract_wema_summary(words: List[Dict[str, Any]]) -> Dict[str, float]:
    """Extract ground-truth summary totals from Page 1 header table."""
    summary = {}
    rows = {}
    for w in words:
        y = round(w['top'])
        if y not in rows: rows[y] = []
        rows[y].append(w)
    
    for y in sorted(rows.keys()):
        line_txt = " ".join([w['text'] for w in sorted(rows[y], key=lambda x: x['x0'])])
        
        # Look for "Total Debit: 45,567,533,642.72"
        if "TOTAL DEBIT" in line_txt.upper():
            parts = line_txt.split(":")
            if len(parts) > 1:
                val = parse_wema_money(parts[-1])
                if val: summary["statement_total_debit"] = val
                
        if "TOTAL CREDIT" in line_txt.upper():
            parts = line_txt.split(":")
            if len(parts) > 1:
                val = parse_wema_money(parts[-1])
                if val: summary["statement_total_credit"] = val
                
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
        # Detect columns and summary from first page
        words_p0 = _pdf_handle.pages[0].extract_words()
        cuts = detect_wema_columns(words_p0)
        
        # EXTRACT SUMMARY TOTALS (Unified 2.1)
        summary_meta = extract_wema_summary(words_p0)
        metadata.update(summary_meta)
        
        # If not on P0, check P1
        if not cuts and len(_pdf_handle.pages) > 1:
            words_p1 = _pdf_handle.pages[1].extract_words()
            cuts = detect_wema_columns(words_p1)
            summary_meta_p1 = extract_wema_summary(words_p1)
            metadata.update(summary_meta_p1)
            
        if not cuts:
            raise ValueError("Wema column headers not found in first 2 pages.")

        summary_keywords = [
            "TOTAL", "CURRENT BAL", "PAYMENTS", "RECEIPTS", "BAL B/F", "BAL C/F", 
            "BROUGHT FORWARD", "CARRIED FORWARD", "ACCOUNT NO:", "ACCOUNT SUMMARY",
            "PAGE TOTAL", "SUB TOTAL", "OPENING BAL", "CLOSING BAL"
        ]

        for i, page in enumerate(_pdf_handle.pages):
            if i % 100 == 0:
                print(f"  [WEMA] Processing page {i+1}/{_total_pages} ({len(txns)} txns so far, {time.time()-_start:.0f}s)")
            p_words = page.extract_words(x_tolerance=2, y_tolerance=2)
            
            # Recalibrate cuts
            new_cuts = detect_wema_columns(p_words)
            if new_cuts: cuts = new_cuts
            
            rows_dict = {}
            for w in p_words:
                y = round(w['top'] / 3) * 3 
                if y not in rows_dict: rows_dict[y] = []
                rows_dict[y].append(w)
                
            for y in sorted(rows_dict.keys()):
                row_words = sorted(rows_dict[y], key=lambda x: x['x0'])
                
                row_data = {k: "" for k in cuts.keys()}
                for w in row_words:
                    word_mid = (w['x0'] + w['x1']) / 2.0
                    for col_name, (c_start, c_end) in cuts.items():
                        if c_start <= word_mid < c_end:
                            row_data[col_name] = (row_data[col_name] + " " + w['text']).strip()
                            break
                            
                # Skip noise and summary rows (only if it's NOT a transaction)
                row_full_text = " ".join(row_data.values()).upper()
                if any(sk in row_full_text for sk in summary_keywords):
                    # Special case: don't skip if it has a valid date and amount
                    # (Wema sometimes includes "TOTAL" in the description)
                    pass
                
                date_str = row_data.get("date", "")
                parsed_date = parse_date_smart(date_str)
                debit_val = parse_wema_money(row_data.get("debit", ""))
                credit_val = parse_wema_money(row_data.get("credit", ""))
                
                # REINFORCE: The summary rows usually don't have dates in the transaction region.
                # If "TOTAL" is found but no date exists, it's noise.
                if any(sk in row_full_text for sk in summary_keywords) and not parsed_date:
                    continue

                if parsed_date and (debit_val or credit_val):
                    desc = row_data.get("description", "").strip()
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
