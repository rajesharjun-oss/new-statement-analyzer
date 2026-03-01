"""
WEMA Bank Dedicated Coordinate Extractor
"""
import pdfplumber
import math
from pathlib import Path
from typing import Dict, List, Tuple, Any

def detect_wema_columns(words: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for WEMA Bank (Tran Date | Value Date | Narration | Tran ID | Cheque No | Withdrawals | Deposits | Balance)
    """
    header_keywords = ["TRAN", "DATE", "VALUE", "NARRATION", "ID", "CHEQUE", "WITHDRAWALS", "DEPOSITS", "BALANCE"]
    
    header_words = []
    for w in words:
        txt = w["text"].upper().strip()
        if any(k in txt for k in header_keywords):
            header_words.append(w)
            
    if len(header_words) < 5:
        return None
        
    tops = [w['top'] for w in header_words]
    tops.sort()
    
    best_band = []
    for t in set([round(x, 1) for x in tops]):
        band = [w for w in header_words if abs(w['top'] - t) < 3.0]
        if len(band) > len(best_band):
            best_band = band
            
    if len(best_band) < 5:
        return None

    def find_col(sub: str):
        for w in best_band:
            if sub in w["text"].upper():
                return w["x0"], w["x1"]
        return None, None

    x_tran_l, _   = find_col("TRAN")
    x_val_l, _    = find_col("VALUE")
    x_nar_l, _    = find_col("NARRATION")
    x_id_l, _     = find_col("ID")
    x_wid_l, _    = find_col("WITHDRAWALS")
    x_dep_l, _    = find_col("DEPOSITS")
    x_bal_l, _    = find_col("BALANCE")

    if x_tran_l is None or x_wid_l is None:
        return None

    cols = [("date", x_tran_l, x_tran_l + 50)]
    
    if x_val_l is not None:
        cols.append(("value_date", x_val_l, x_val_l + 50))
    if x_nar_l is not None:
         # Include ID & Cheque No inside narration block, we'll strip or merge them
        cols.append(("description", x_nar_l, x_nar_l + 60))
    if x_id_l is not None:
        cols.append(("tran_id", x_id_l, x_id_l + 30))
    if x_wid_l is not None:
        cols.append(("debit", x_wid_l, x_wid_l + 40))
    if x_dep_l is not None:
        cols.append(("credit", x_dep_l, x_dep_l + 40))
    if x_bal_l is not None:
        cols.append(("balance", x_bal_l, x_bal_l + 40))
        
    cols = sorted(cols, key=lambda x: x[1])
    
    cut_points = []
    for i in range(len(cols) - 1):
        name1, l1, r1 = cols[i]
        name2, l2, r2 = cols[i+1]
        mid = (r1 + l2) / 2  # True midpoint for WEMA
        cut_points.append(mid)

    cuts = {}
    for i, (name, l, r) in enumerate(cols):
        start = cut_points[i-1] if i > 0 else -math.inf
        end = cut_points[i] if i < len(cut_points) else math.inf
        cuts[name] = (start, end)
        
    return cuts

def extract_wema_via_coordinates(pdf_path: Path, metadata: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import parse_date_smart, first_money, is_noise_row
    txns = []
    
    with pdfplumber.open(pdf_path) as pdf:
        words = pdf.pages[0].extract_words()
        cuts = detect_wema_columns(words)
        
        if not cuts:
             raise ValueError("Could not detect WEMA column bounds on page 0")
             
        print(f"DEBUG: Active WEMA Cuts P0: {cuts}")
        
        for pg_num, page in enumerate(pdf.pages):
            words = page.extract_words()
            
            new_cuts = detect_wema_columns(words)
            if new_cuts:
                cuts = new_cuts
                
            col_list = []
            for name, bounds in cuts.items():
                 col_list.append((name, bounds[0], bounds[1]))
                 
            rows_dict = {}
            for w in words:
                y = round(w['top'] / 3) * 3 
                if y not in rows_dict:
                    rows_dict[y] = []
                rows_dict[y].append(w)
                
            for y in sorted(rows_dict.keys()):
                row_words = rows_dict[y]
                
                row_dict = {name: [] for name, _, _ in col_list}
                for w in sorted(row_words, key=lambda w: w['x0']):
                    word_mid = w['x1'] - 5
                    for name, min_x, max_x in col_list:
                        if min_x <= word_mid < max_x:
                            row_dict[name].append(w['text'])
                            break
                            
                for name in row_dict:
                    row_dict[name] = " ".join(row_dict[name]).strip()
                    
                if not any(row_dict.values()):
                    continue
                    
                date_str = row_dict.get("date", "")
                parsed_date = parse_date_smart(date_str)
                desc = row_dict.get("description", "")
                
                if parsed_date and len(date_str) > 6 and ("/" in date_str or "-" in date_str):
                    pass # Valid new date
                else:
                    # Inherit date if we have financials
                    if txns and (row_dict.get("debit") or row_dict.get("credit")):
                        parsed_date = txns[-1]["date"]
                        
                debit_str = first_money(row_dict.get("debit", ""))
                credit_str = first_money(row_dict.get("credit", ""))
                bal_str = first_money(row_dict.get("balance", ""))
                
                if parsed_date and (debit_str or credit_str or ("/" in date_str and len(date_str) > 6)):
                    debit = float(debit_str.replace(",", "")) if debit_str else 0.0
                    credit = float(credit_str.replace(",", "")) if credit_str else 0.0
                    bal = float(bal_str.replace(",", "")) if bal_str else 0.0
                    
                    txn = {
                        "date": parsed_date,
                        "value_date": parse_date_smart(row_dict.get("value_date", "")) or parsed_date,
                        "description": desc,
                        "reference": "",
                        "debit": debit,
                        "credit": credit,
                        "balance": bal,
                        "category": "Uncategorized",
                        "remarks": desc
                    }
                    
                    if not is_noise_row(txn):
                        txns.append(txn)
                        
                elif txns and desc:
                    txns[-1]["description"] += " " + desc
                    txns[-1]["remarks"] = txns[-1]["description"]

    return txns, metadata
