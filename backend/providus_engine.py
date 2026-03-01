"""
Providus Bank Dedicated Table Extractor
"""
import pdfplumber
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any

def detect_providus_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for Providus Bank (TXN DATE | VAL DATE | REMARKS | DEBIT | CREDIT | BALANCE)
    """
    header_keywords = ["TXN", "DATE", "VAL", "REMARKS", "DEBIT", "CREDIT", "BALANCE"]
    
    header_words = []
    for w in words:
        txt = w["text"].upper().strip()
        if any(k in txt for k in header_keywords):
            header_words.append(w)
            
    if len(header_words) < 3:
        return None
        
    # Group by Y to find the main header line (typically around top=153)
    # Using a simple Y tolerance grouping
    tops = [w['top'] for w in header_words]
    tops.sort()
    
    best_band = []
    for t in set([round(x, 1) for x in tops]):
        band = [w for w in header_words if abs(w['top'] - t) < 3.0]
        if len(band) > len(best_band):
            best_band = band
            
    if len(best_band) < 3:
        return None

    def find_col(sub: str):
        for w in best_band:
            if sub in w["text"].upper():
                return w["x0"], w["x1"]
        return None, None

    x_txn_l, x_txn_r   = find_col("TXN")
    x_val_l, x_val_r   = find_col("VAL")
    x_rem_l, x_rem_r   = find_col("REMARKS")
    x_deb_l, x_deb_r   = find_col("DEBIT")
    x_cred_l, x_cred_r = find_col("CREDIT")
    x_bal_l, x_bal_r   = find_col("BALANCE")

    if x_txn_l is None:
        return None

    cols = [("date", x_txn_l, x_txn_r if x_txn_r else x_txn_l + 50)]
    
    if x_val_l is not None:
        cols.append(("value_date", x_val_l, x_val_r if x_val_r else x_val_l + 50))
    if x_rem_l is not None:
        cols.append(("description", x_rem_l, x_rem_r if x_rem_r else x_rem_l + 60))
    if x_deb_l is not None:
        cols.append(("debit", x_deb_l, x_deb_r if x_deb_r else x_deb_l + 40))
    if x_cred_l is not None:
        cols.append(("credit", x_cred_l, x_cred_r if x_cred_r else x_cred_l + 40))
    if x_bal_l is not None:
        cols.append(("balance", x_bal_l, x_bal_r if x_bal_r else x_bal_l + 40))
        
    cols = sorted(cols, key=lambda x: x[1])
    
    # Calculate cuts intelligently
    cut_points = []
    for i in range(len(cols) - 1):
        name1, l1, r1 = cols[i]
        name2, l2, r2 = cols[i+1]
        
        # Give previous column maximum space by cutting right before the next column starts
        mid = l2 - 3
        
        cut_points.append(mid)

    cuts = {}
    for i, (name, l, r) in enumerate(cols):
        start = cut_points[i-1] if i > 0 else -math.inf
        end = cut_points[i] if i < len(cut_points) else math.inf
        cuts[name] = (start, end)
        
    return cuts

def extract_providus_via_tables(pdf_path: Path, metadata: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import parse_date_smart, first_money, is_noise_row
    txns = []
    
    with pdfplumber.open(pdf_path) as pdf:
        # Step 1: Find the global table cuts across all pages using the first page
        words = pdf.pages[0].extract_words()
        cuts = detect_providus_columns(words)
        
        if not cuts:
             raise ValueError("Could not detect Providus column bounds")
             
        print(f"DEBUG: Active Providus Cuts: {cuts}")
        
        # Build column bounds list for easy lookup
        # Each item is (name, min_x, max_x)
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
                    for name, min_x, max_x in col_list:
                        if min_x <= w['x0'] < max_x:
                            row_dict[name].append(w['text'])
                            break
                            
                # Join words in each column
                for name in row_dict:
                    row_dict[name] = " ".join(row_dict[name]).strip()
                    
                # Check if it's a valid date row or continuation row
                if not any(row_dict.values()):
                    continue
                    
                date_str = row_dict.get("date", "")
                parsed_date = parse_date_smart(date_str)
                
                desc = row_dict.get("description", "")
                
                if parsed_date:
                    # New transaction
                    debit_str = first_money(row_dict.get("debit", ""))
                    credit_str = first_money(row_dict.get("credit", ""))
                    bal_str = first_money(row_dict.get("balance", ""))
                    
                    debit = float(debit_str.replace(",", "")) if debit_str else 0.0
                    credit = float(credit_str.replace(",", "")) if credit_str else 0.0
                    bal = float(bal_str.replace(",", "")) if bal_str else 0.0
                    
                    # Extract reference if present (often /digits at the end)
                    ref = ""
                    ref_match = re.search(r'/(\d{10,})$', desc.strip())
                    if ref_match:
                        ref = ref_match.group(1)
                    
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
                        
                elif txns and desc and not any([row_dict.get("debit"), row_dict.get("credit")]):
                    # Continuation row: merge description into the last transaction
                    txns[-1]["description"] += " " + desc
                    txns[-1]["remarks"] = txns[-1]["description"]

    return txns, metadata
