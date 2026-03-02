"""
Access Bank Dedicated Coordinate Extractor
"""
import pdfplumber
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any

def detect_access_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for Access Bank
    """
    # Collect all potential header words first
    header_keywords = ["TRANSACTION", "DETAILS", "LODGEMENTS", "WITHDRAWALS", "REFERENCE", "BALANCE", "DATE"]
    header_words = []
    for w in words:
        txt = w["text"].upper().strip()
        if any(k in txt for k in header_keywords) or "DATE" in txt:
            header_words.append(w)
            
    if not header_words: return None

    # Access Bank often has multi-line headers (e.g. Y=250 and Y=258)
    # We collect all header words in the 240-270 range
    best_band = [w for w in header_words if 240 <= w['top'] <= 270]
    
    if len(best_band) < 3:
        # Fallback to the largest single-line band if the absolute range fails
        tops = [w['top'] for w in header_words]
        best_band = [] # Reset for fallback
        for t in set([round(x, 1) for x in tops]):
            band = [w for w in header_words if abs(w['top'] - t) < 3.0]
            if len(band) > len(best_band): best_band = band
            
    def find_col(sub: str):
        for w in best_band:
            if sub in w["text"].upper(): return w["x0"], w["x1"]
        return None, None

    # Find both edges for each column with broader match
    headers = []
    def add_h(name, sub, alt=None):
        l, r = find_col(sub)
        if l is None and alt: l, r = find_col(alt)
        if l is not None: headers.append((name, l, r))

    add_h("date", "DATE")
    add_h("description", "DETAILS", "TRANSACTION")
    add_h("reference", "REFERENCE", "REF")
    add_h("value_date", "VALUE", "VAL")
    add_h("debit", "WITHDRAWALS", "DEBIT")
    add_h("credit", "LODGEMENTS", "CREDIT")
    add_h("balance", "BALANCE", "BAL")
    
    headers = sorted(headers, key=lambda x: x[1])
    
    # Check if we have enough headers to be dynamic
    if len(headers) >= 4:
        # Calculate cuts at the midpoint of GAPS
        cuts = {}
        for i in range(len(headers)):
            name, x0, x1 = headers[i]
            # Use actual x1 if available, else x0+gap
            start = cuts[headers[i-1][0]][1] if i > 0 else -math.inf
            
            if i < len(headers) - 1:
                next_name, next_x0, next_x1 = headers[i+1]
                end = (x1 + next_x0) / 2
            else:
                end = math.inf
            cuts[name] = (start, end)
    else:
        # Robust fallback to standard Access coordinates
        print(f"WARN [Access]: Deep header search failed (found {len(headers)}). Using standard fallbacks.")
        cuts = {
            "date": (-math.inf, 185),
            "description": (185, 405),
            "reference": (405, 478),
            "value_date": (478, 540),
            "debit": (540, 610),
            "credit": (610, 680),
            "balance": (680, math.inf)
        }
    
    print(f"DEBUG [Access]: Detected headers {headers}")
    print(f"DEBUG [Access]: Derived cuts: {cuts}")
        
    return cuts

def extract_access_via_coordinates(pdf_path: Path, metadata: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import parse_date_smart, first_money, is_noise_row
    txns = []
    
    with pdfplumber.open(pdf_path) as pdf:
        words_p0 = pdf.pages[0].extract_words()
        cuts = detect_access_columns(words_p0)
        
        if not cuts:
             # Try page 1 if page 0 failed (sometimes cover page)
             if len(pdf.pages) > 1:
                words_p1 = pdf.pages[1].extract_words()
                cuts = detect_access_columns(words_p1)
             
             if not cuts:
                return [], {}
             
        print(f"DEBUG: Active Access Cuts: {cuts}")
        
        pending_description = ""
        pending_reference = ""
        
        for pg_num, page in enumerate(pdf.pages):
            words = page.extract_words()
            
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
                parsed_date = parse_date_smart(date_str)
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
                        "value_date": parse_date_smart(row_dict.get("value_date", "")) or parsed_date,
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

    return txns, metadata
