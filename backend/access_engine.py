"""
Access Bank Dedicated Coordinate Extractor
"""
import pdfplumber
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any

def detect_access_columns(words: List[Dict[str, Any]], bank_identifier: str = None) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for Access Bank.
    Handles multiple template variants including:
    - Standard: TRANSACTION DETAILS | REFERENCE | WITHDRAWALS | LODGEMENTS | BALANCE
    - Variant 2: Date | Transaction Details | Reference | Value Date | Withdrawals | Lodgements | Balance
    """
    if not words: return None

    # 1. FIND HEADER BANDS
    keywords = ["DATE", "TRANSACTION", "DETAILS", "DESCRIPTION", "NARRATION", "REFERENCE", "REF", "VALUE", "WITHDRAWALS", "DEBIT", "LODGEMENTS", "CREDIT", "BALANCE", "BAL"]
    
    header_words = []
    for w in words:
        txt = (w.get("text") or "").upper().strip()
        for k in keywords:
            if k in txt:
                header_words.append(w)
                break
            
    if not header_words: return None

    rows = {}
    for w in header_words:
        y = round(w['top'])
        if y not in rows: rows[y] = []
        rows[y].append(w)
    
    best_y = -1
    max_indicators = 0
    for y, row_words in rows.items():
        band = [w for w in header_words if abs(w['top'] - y) < 8.0]
        inds = set()
        for wb in band:
            t = wb["text"].upper()
            for k in keywords:
                if k in t: inds.add(k)
        
        if len(inds) >= max_indicators:
            max_indicators = len(inds)
            best_y = y
            
    if max_indicators < 4:
        return None

    active_band = [w for w in header_words if abs(w['top'] - best_y) < 8.0]
    
    def find_x(subs, is_right=False):
        found_matches = []
        for word_dict in active_band:
            original_text = word_dict.get("text", "")
            if original_text is None:
                continue
            
            upper_text = str(original_text).upper().strip()
            
            for s in subs:
                search_term = str(s).upper().strip()
                match = search_term in upper_text
                if match:
                    found_matches.append(word_dict)
                    break # Found a match for this word
                    
        if not found_matches: 
            return None
        val = max(m["x1"] for m in found_matches) if is_right else min(m["x0"] for m in found_matches)
        return val

    # 2. EXTRACT COORDINATES
    x_date = find_x(["Date"])
    x_details = find_x(["Details", "Transaction", "Description", "Narration"])
    x_ref = find_x(["Ref", "Reference"])
    x_val = find_x(["Value"])
    x_with = find_x(["Withdrawals", "Debit"], is_right=True)
    x_lodge = find_x(["Lodgements", "Credit"], is_right=True)
    x_bal = find_x(["Balance", "Bal"], is_right=True)

    if not all([x_date, x_details, x_ref, x_with or x_lodge, x_bal]):
        print(f"DEBUG [Access]: Missing core columns: Date={x_date}, Details={x_details}, Ref={x_ref}, With={x_with}, Lodge={x_lodge}, Bal={x_bal}")
        return None

    # 3. CONSTRUCT CUTS (Midpoint based for max width)
    # Goal: Use the space between headers as boundaries to avoid clipping large numbers
    
    # Sort detected headers by their x-coordinate to build a sequence
    # We use (name, left, right)
    header_anchors = []
    if x_date is not None: header_anchors.append(("date", x_date, x_date + 40))
    if x_details is not None: header_anchors.append(("description", x_details, x_details + 60))
    if x_ref is not None: header_anchors.append(("reference", x_ref, x_ref + 40))
    if x_val is not None: header_anchors.append(("value_date", x_val, x_val + 40))
    
    # Money columns are usually right-aligned or centered under wide headers
    # For Access 2.0: Withdrawals (320-385), Lodgements (420-466), Balance (509-562)
    if x_with is not None: header_anchors.append(("debit", x_with - 60, x_with))
    if x_lodge is not None: header_anchors.append(("credit", x_lodge - 60, x_lodge))
    if x_bal is not None: header_anchors.append(("balance", x_bal - 60, x_bal))
    
    header_anchors.sort(key=lambda x: x[1])
    
    cuts = {}
    for i in range(len(header_anchors)):
        name, h_left, h_right = header_anchors[i]
        
        # Left boundary: midpoint to previous anchor's right, or 0
        if i == 0:
            start = 0.0
        else:
            prev_name, prev_l, prev_r = header_anchors[i-1]
            start = (prev_r + h_left) / 2
            
        # Right boundary: midpoint to next anchor's left, or 1000
        if i == len(header_anchors) - 1:
            end = 1000.0
        else:
            next_name, next_l, next_r = header_anchors[i+1]
            end = (h_right + next_l) / 2
            
        cuts[name] = (start, end)

    print(f"DEBUG [Access]: Generated cuts: {cuts}")
    return cuts

def extract_access_via_coordinates(pdf_path: Path, metadata: Dict[str, Any], pdf: pdfplumber.PDF = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import parse_date_smart, first_money, is_noise_row
    import pandas as pd
    
    def _parse_access_date(date_str: str) -> str | None:
        """
        Access Bank uses M/D/YYYY (US format) for transaction dates.
        e.g. 10/1/2025 = October 1, 2025 (NOT January 10, 2025)
        But Value Date uses DD-MMM-YYYY (e.g. 01-Oct-2025).
        """
        s = (date_str or "").strip()
        if not s or len(s) < 6:
            return None
        
        # If it contains slashes, treat as M/D/YYYY (Access Bank US format)
        if "/" in s:
            try:
                dt = pd.to_datetime(s, dayfirst=False, errors='coerce')
                if pd.notna(dt):
                    return dt.strftime("%d-%b-%Y")
            except:
                pass
            
        # Otherwise fallback to the standard parser
        return parse_date_smart(s)
    
    txns = []
    
    # If pdf handle is provided, use it, otherwise open
    if pdf is None:
        _pdf_handle = pdfplumber.open(pdf_path)
        _auto_close = True
    else:
        _pdf_handle = pdf
        _auto_close = False
        
    try:
        # Dynamic cuts: start with None, then update on each page if a header is found
        cuts = None
        
        # We still do a pre-scan of first 5 pages just to see if we can identify it at all
        for pg_idx in range(min(5, len(_pdf_handle.pages))):
            words = _pdf_handle.pages[pg_idx].extract_words()
            if detect_access_columns(words):
                print(f"DEBUG [Access]: Initial header signature found on page {pg_idx}")
                break
        else:
            print(f"DEBUG [Access]: No Access header signature found in first 5 pages.")
            return [], metadata
             
        print(f"DEBUG: Active Access Cuts: {cuts}")
        
        pending_description = ""
        pending_reference = ""
        
        txns = []
        for pg_num, page in enumerate(_pdf_handle.pages):
            words = page.extract_words()
            
            # Update cuts for THIS page if a header is present
            new_cuts = detect_access_columns(words)
            if new_cuts:
                cuts = new_cuts
                print(f"DEBUG [Access]: Cuts updated for page {pg_num}")
            
            if not cuts:
                continue
                
            # Group by Y
            rows_dict = {}
            for w in words:
                y = round(w['top'] / 2) * 2 # Tighter tolerance for Access
                if y not in rows_dict: rows_dict[y] = []
                rows_dict[y].append(w)
                
            for y in sorted(rows_dict.keys()):
                row_words = rows_dict[y]
                
                # Assign words to columns
                row_dict = {name: [] for name in cuts.keys()}
                for w in sorted(row_words, key=lambda w: w['x0']):
                    for col_name, (min_x, max_x) in cuts.items():
                        # Use x1 for numeric, x0 for text
                        val = w['x1'] if any(k in col_name for k in ["debit", "credit", "balance"]) else w['x0']
                        
                        if min_x <= val < max_x:
                            row_dict[col_name].append(w['text'])
                            break
                
                # Join bucket contents
                row_dict = {k: " ".join(v).strip() for k, v in row_dict.items()}
                
                if not any(row_dict.values()):
                    continue
                    
                date_str = row_dict.get("date", "")
                parsed_date = _parse_access_date(date_str)
                desc = row_dict.get("description", "")
                ref = row_dict.get("reference", "")
                
                # Access often has multi-line descriptions
                # If row has NO date and NO money, it's a continuation
                is_pure_cont = desc and not parsed_date and not any([row_dict.get("debit"), row_dict.get("credit"), row_dict.get("balance")])
                
                if is_pure_cont:
                    if txns:
                        txns[-1]["description"] = (txns[-1]["description"] + " " + desc).strip()
                        if ref:
                            txns[-1]["reference"] = (txns[-1]["reference"] + " " + ref).strip()
                        txns[-1]["remarks"] = txns[-1]["description"]
                    continue

                if parsed_date:
                    debit_str = first_money(row_dict.get("debit", ""))
                    credit_str = first_money(row_dict.get("credit", ""))
                    bal_str = first_money(row_dict.get("balance", ""))
                    
                    debit = float(debit_str.replace(",", "")) if debit_str else 0.0
                    credit = float(credit_str.replace(",", "")) if credit_str else 0.0
                    bal = float(bal_str.replace(",", "")) if bal_str else 0.0
                    
                    txn = {
                        "date": parsed_date,
                        "value_date": _parse_access_date(row_dict.get("value_date", "")) or parsed_date,
                        "description": desc,
                        "reference": ref,
                        "debit": debit,
                        "credit": credit,
                        "balance": bal,
                        "category": "Uncategorized",
                        "remarks": desc
                    }
                    
                    if not is_noise_row(txn):
                        txns.append(txn)
                        
                elif txns and desc:
                    # Final fallback for any other text
                    txns[-1]["description"] = (txns[-1]["description"] + " " + desc).strip()
                    txns[-1]["remarks"] = txns[-1]["description"]

    finally:
        if _auto_close:
            _pdf_handle.close()

    return txns, metadata
