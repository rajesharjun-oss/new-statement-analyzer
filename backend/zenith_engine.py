"""
Zenith Bank Dedicated Coordinate Extractor
"""
import pdfplumber
import math
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

    cols = [("date", x_date_l, x_date_l + 50)]
    
    if x_val_l is not None:
        cols.append(("value_date", x_val_l, x_val_l + 50))
    if x_desc_l is not None:
        cols.append(("description", x_desc_l, x_desc_l + 60))
    if x_deb_l is not None:
        cols.append(("debit", x_deb_l, x_deb_l + 40))
    if x_cred_l is not None:
        cols.append(("credit", x_cred_l, x_cred_l + 40))
    if x_bal_l is not None:
        cols.append(("balance", x_bal_l, x_bal_l + 40))
        
    cols = sorted(cols, key=lambda x: x[1])
    
    # Calculate cuts
    cut_points = []
    for i in range(len(cols) - 1):
        name1, l1, r1 = cols[i]
        name2, l2, r2 = cols[i+1]
        
        # Give previous column maximum space by cutting just before next column
        mid = l2 - 3
        cut_points.append(mid)

    cuts = {}
    for i, (name, l, r) in enumerate(cols):
        start = cut_points[i-1] if i > 0 else -math.inf
        end = cut_points[i] if i < len(cut_points) else math.inf
        cuts[name] = (start, end)
        
    return cuts

def extract_zenith_via_coordinates(pdf_path: Path, metadata: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import parse_date_smart, first_money, is_noise_row
    txns = []
    
    with pdfplumber.open(pdf_path) as pdf:
        # Step 1: Find the global table cuts across all pages using the first page
        words = pdf.pages[0].extract_words()
        cuts = detect_zenith_columns(words)
        
        if not cuts:
             raise ValueError("Could not detect Zenith column bounds")
             
        print(f"DEBUG: Active Zenith Cuts: {cuts}")
        
        col_list = []
        for name, bounds in cuts.items():
             col_list.append((name, bounds[0], bounds[1]))
             
        for pg_num, page in enumerate(pdf.pages):
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
                row_dict = {name: [] for name, _, _ in col_list}
                for w in sorted(row_words, key=lambda w: w['x0']):
                    word_mid = (w['x0'] + w['x1']) / 2
                    for name, min_x, max_x in col_list:
                        if min_x <= word_mid < max_x:
                            row_dict[name].append(w['text'])
                            break
                            
                # Join words in each column
                for name in row_dict:
                    row_dict[name] = " ".join(row_dict[name]).strip()
                    
                if not any(row_dict.values()):
                    continue
                    
                date_str = row_dict.get("date", "")
                parsed_date = parse_date_smart(date_str)
                desc = row_dict.get("description", "")
                
                if parsed_date and len(date_str) > 6 and ("/" in date_str or "-" in date_str):
                    # New transaction if Date is strongly valid
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
                        "reference": "", # Often embedded in desc
                        "debit": debit,
                        "credit": credit,
                        "balance": bal,
                        "category": "Uncategorized",
                        "remarks": desc # Fallback
                    }
                    
                    if not is_noise_row(txn):
                        txns.append(txn)
                        
                elif txns and desc and not any([row_dict.get("debit"), row_dict.get("credit"), row_dict.get("balance"), row_dict.get("date")]):
                    # Multi-line description (Zenith specific style)
                    txns[-1]["description"] += " " + desc
                    txns[-1]["remarks"] = txns[-1]["description"]

    return txns, metadata
