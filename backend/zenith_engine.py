"""
Zenith Bank Dedicated Coordinate Extractor
"""
import pdfplumber
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any

def detect_zenith_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for Zenith Bank (DATE POSTED | VALUE DATE | DESCRIPTION | DEBIT | CREDIT | BALANCE)
    """
    header_keywords = ["DATE", "POSTED", "VALUE", "DESCRIPTION", "DEBIT", "CREDIT", "BALANCE"]
    
    header_words = []
    for w in words:
        txt = w["text"].upper().strip()
        if any(k in txt for k in header_keywords):
            header_words.append(w)
            
    if len(header_words) < 4:
        return None
        
    # Group by Y to find the main header line
    tops = [w['top'] for w in header_words]
    tops.sort()
    
    best_band = []
    for t in set([round(x, 1) for x in tops]):
        band = [w for w in header_words if abs(w['top'] - t) < 3.0]
        if len(band) > len(best_band):
            best_band = band
            
    if len(best_band) < 4:
        return None

    def find_col(sub: str):
        for w in best_band:
            if sub in w["text"].upper():
                return w["x0"], w["x1"]
        return None, None

    x_date_l, _   = find_col("DATE")
    x_val_l, _    = find_col("VALUE")
    x_desc_l, _   = find_col("DESCRIPTION")
    x_deb_l, _    = find_col("DEBIT")
    x_cred_l, _   = find_col("CREDIT")
    x_bal_l, _    = find_col("BALANCE")

    if x_date_l is None or x_deb_l is None:
        return None

    # Find both edges for each column
    headers = []
    if x_date_l is not None: headers.append(("date", x_date_l, find_col("DATE")[1]))
    if x_val_l is not None: headers.append(("value_date", x_val_l, find_col("VALUE")[1]))
    if x_desc_l is not None: headers.append(("description", x_desc_l, find_col("DESCRIPTION")[1]))
    if x_deb_l is not None: headers.append(("debit", x_deb_l, find_col("DEBIT")[1]))
    if x_cred_l is not None: headers.append(("credit", x_cred_l, find_col("CREDIT")[1]))
    if x_bal_l is not None: headers.append(("balance", x_bal_l, find_col("BALANCE")[1]))
    
    headers = sorted(headers, key=lambda x: x[1])
    
    # Calculate cuts — give description column extra width since Zenith
    # descriptions often start well to the left of the DESCRIPTION header
    cuts = {}
    for i in range(len(headers)):
        name, x0, x1 = headers[i]
        start = cuts[headers[i-1][0]][1] if i > 0 else -math.inf
        
        if i < len(headers) - 1:
            next_name, next_x0, next_x1 = headers[i+1]
            
            if next_name == "description":
                # Give description maximum room — cut right after value_date's right edge
                end = x1 + 5
            elif name == "description":
                # Description's right edge: cut close to the debit header's left edge
                end = next_x0 - 10
            else:
                # Use the midpoint between current right edge and next left edge
                end = (x1 + next_x0) / 2
        else:
            end = math.inf
            
        cuts[name] = (start, end)
    
    print(f"DEBUG [Zenith]: Detected headers {headers}")
    print(f"DEBUG [Zenith]: Gap-based cuts derived: {cuts}")
        
    return cuts

def extract_zenith_via_coordinates(pdf_path: Path, metadata: Dict[str, Any], pdf: pdfplumber.PDF = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import parse_date_smart, first_money, is_noise_row
    txns = []
    
    # If pdf handle is provided, use it, otherwise open
    if pdf is None:
        _pdf_handle = pdfplumber.open(pdf_path)
        _auto_close = True
    else:
        _pdf_handle = pdf
        _auto_close = False
        
    try:
        # Step 1: Find the global table cuts across all pages using the first page
        words = _pdf_handle.pages[0].extract_words()
        cuts = detect_zenith_columns(words)
        
        if not cuts:
             raise ValueError("Could not detect Zenith column bounds")
             
        print(f"DEBUG: Active Zenith Cuts: {cuts}")
        
        col_list = []
        for name, bounds in cuts.items():
             col_list.append((name, bounds[0], bounds[1]))
             
        pending_description = ""
        last_date_y = -999  # Y position of the last date/money row
        
        for pg_num, page in enumerate(_pdf_handle.pages):
            words = page.extract_words()
            
            # Group words by Y coordinate (lines)
            rows_dict = {}
            for w in words:
                y = round(w['top'] / 3) * 3 # 3pt tolerance
                if y not in rows_dict:
                    rows_dict[y] = []
                rows_dict[y].append(w)
                
            for y in sorted(rows_dict.keys()):
                row_words = rows_dict[y]
                
                # Assign words to columns
                row_dict = {name: [] for name in cuts.keys()}
                for w in sorted(row_words, key=lambda w: w['x0']):
                    # For numeric words (amounts), ALWAYS use x1 (right-aligned)
                    # This prevents amounts near column boundaries from being
                    # swallowed by the description column
                    text = w['text'].replace(',', '')
                    is_numeric = bool(re.match(r'^[\d,]+\.\d{2}$', w['text'])) or \
                                 bool(re.match(r'^[\d.]+$', text) and len(text) > 2)
                    
                    for name, (min_x, max_x) in cuts.items():
                        if is_numeric:
                            val = w['x1']  # Right-align all amounts
                        else:
                            val = w['x1'] if name in ["debit", "credit", "balance"] else w['x0']
                        if min_x <= val < max_x:
                            row_dict[name].append(w['text'])
                            break
                    
                # Join bucket contents
                row_dict = {k: " ".join(v).strip() for k, v in row_dict.items()}
                
                if not any(row_dict.values()):
                    continue
                    
                date_str = row_dict.get("date", "").strip()
                parsed_date = parse_date_smart(date_str)
                desc = row_dict.get("description", "").strip()
                
                has_money = any([row_dict.get("debit"), row_dict.get("credit"), row_dict.get("balance")])
                
                # Description-only row (no date, no money)
                is_pure_desc = desc and not parsed_date and not has_money
                
                if is_pure_desc:
                    # Decide: is this a CONTINUATION of the last txn (close Y)
                    # or a LEAD-IN for the next txn (far Y)?
                    y_gap = y - last_date_y
                    
                    if txns and y_gap <= 6:
                        # Close to last date row = continuation of previous transaction
                        txns[-1]["description"] = (txns[-1]["description"] + " " + desc).strip()
                        txns[-1]["remarks"] = txns[-1]["description"]
                    else:
                        # Far from last date row = lead-in for next transaction
                        if pending_description:
                            pending_description += " "
                        pending_description += desc
                    continue

                if parsed_date and len(date_str) > 6:
                    last_date_y = y
                    
                    # New transaction
                    debit_str = first_money(row_dict.get("debit", ""))
                    credit_str = first_money(row_dict.get("credit", ""))
                    bal_str = first_money(row_dict.get("balance", ""))
                    
                    debit = float(debit_str.replace(",", "")) if debit_str else 0.0
                    credit = float(credit_str.replace(",", "")) if credit_str else 0.0
                    bal = float(bal_str.replace(",", "")) if bal_str else 0.0
                    
                    # Combine with buffered description
                    full_desc = desc
                    if pending_description:
                        full_desc = f"{pending_description} {desc}".strip()
                        pending_description = ""
                    
                    txn = {
                        "date": parsed_date,
                        "value_date": parse_date_smart(row_dict.get("value_date", "")) or parsed_date,
                        "description": full_desc,
                        "reference": "",
                        "debit": debit,
                        "credit": credit,
                        "balance": bal,
                        "category": "Uncategorized",
                        "remarks": full_desc
                    }
                    
                    if not is_noise_row(txn):
                        txns.append(txn)
                else:
                    if txns and desc:
                        # Trailing multi-line description
                        txns[-1]["description"] = (txns[-1]["description"] + " " + desc).strip()
                        txns[-1]["remarks"] = txns[-1]["description"]

    finally:
        if _auto_close:
            _pdf_handle.close()

    return txns, metadata
