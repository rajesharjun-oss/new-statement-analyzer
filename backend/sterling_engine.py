import pdfplumber
import re
from pathlib import Path

def detect_sterling_columns(words):
    """
    Detect Sterling Bank column bounds based on headers:
    Date, VALUE Date, Narration, Money In, Money Out, Balance
    """
    header_keywords = ["DATE", "NARRATION", "MONEY IN", "MONEY OUT", "BALANCE"]
    header_words = [w for w in words if any(k in w['text'].upper() for k in header_keywords)]
    
    if len(header_words) < 3:
        return None
        
    from collections import defaultdict
    y_groups = defaultdict(list)
    for w in words:
        y_groups[round(w['top'])].append(w)

    anchor_row = None
    y_anchor = None
    for y in sorted(y_groups.keys()):
        row = sorted(y_groups[y], key=lambda w: w['x0'])
        row_text = " ".join([w['text'] for w in row]).upper()
        if "NARRATION" in row_text and "MONEY" in row_text:
            anchor_row = row
            y_anchor = y
            break
            
    if not anchor_row: return None

    # Find the Date row (usually slightly below/above the anchor)
    date_row = anchor_row
    for dy in [-10, -8, -6, -4, -2, 2, 4, 6, 8, 10]:
        y_test = y_anchor + dy
        if y_test in y_groups:
            test_text = " ".join([w['text'] for w in y_groups[y_test]]).upper()
            if "DATE" in test_text:
                date_row = y_groups[y_test]
                break

    def find_x(snippets, target_row):
        matches = [w for w in target_row if any(s.upper() in w['text'].upper() for s in snippets)]
        if not matches: return None, None
        return min(m['x0'] for m in matches), max(m['x1'] for m in matches)

    # Use coordinates from respective rows
    x_date_l, _ = find_x(["DATE"], date_row)
    x_narr_l, _ = find_x(["NARRATION"], anchor_row)
    x_in_l, x_in_r = find_x(["MONEY", "IN"], anchor_row)
    x_out_l, x_out_r = find_x(["MONEY", "OUT"], anchor_row)
    x_bal_l, x_bal_r = find_x(["BALANCE"], anchor_row)

    if x_narr_l is None or x_in_l is None: return None
    
    cuts = {}
    # Define boundaries
    cuts['date'] = (0, x_narr_l - 2)
    cuts['description'] = (x_narr_l - 2, x_in_l - 2 if x_in_l else x_out_l - 2)
    
    # MONEY IN = CREDIT, MONEY OUT = DEBIT
    if x_in_l:
        cuts['credit'] = (x_in_l - 2, x_in_r + 5)
    else:
        cuts['credit'] = (0, 0)
        
    if x_out_l:
        cuts['debit'] = (x_out_l - 2, x_out_r + 5)
    else:
        cuts['debit'] = (0, 0)

    cuts['balance'] = (x_bal_l - 2, 1000)
    
    return cuts

def extract_sterling_via_coordinates(pdf_path: Path, config: dict):
    from pdf_extractor import parse_date_smart, first_money, is_noise_row
    
    transactions = []
    with pdfplumber.open(pdf_path) as pdf:
        cuts = None
        for i in range(min(3, len(pdf.pages))):
            words = pdf.pages[i].extract_words()
            print(f"DEBUG: Sterling Scan P{i} words: {len(words)}")
            cuts = detect_sterling_columns(words)
            if cuts: break
        
        if not cuts:
             return [], {}

        print(f"DEBUG: Sterling Cuts: {cuts}")
        
        last_date = None
        
        for pg_num, page in enumerate(pdf.pages):
            words = page.extract_words()
            
            # Update cuts per page if header found
            new_cuts = detect_sterling_columns(words)
            if new_cuts:
                cuts = new_cuts

            col_list = [(name, b[0], b[1]) for name, b in cuts.items()]
            
            rows_dict = {}
            for w in words:
                y = round(w['top'] / 2) * 2 # Slight tolerance
                if y not in rows_dict: rows_dict[y] = []
                rows_dict[y].append(w)
            
            for y in sorted(rows_dict.keys()):
                row_words = sorted(rows_dict[y], key=lambda w: w['x0'])
                row_data = {name: [] for name, _, _ in col_list}
                
                for w in row_words:
                    mid_x = (w['x0'] + w['x1']) / 2
                    for name, x0, x1 in col_list:
                        if x0 <= mid_x < x1:
                            row_data[name].append(w['text'])
                
                desc = " ".join(row_data['description']).strip()
                date_str = " ".join(row_data['date']).strip()
                deb_str = " ".join(row_data['debit']).strip()
                cred_str = " ".join(row_data['credit']).strip()
                bal_str = " ".join(row_data['balance']).strip()
                
                parsed_date = parse_date_smart(date_str)
                if parsed_date:
                    last_date = parsed_date
                
                # Validation: must have either date OR money
                has_money = first_money(deb_str) or first_money(cred_str)
                
                if not parsed_date and not has_money:
                    continue
                    
                val_deb = float(first_money(deb_str).replace(',','')) if first_money(deb_str) else 0.0
                val_cred = float(first_money(cred_str).replace(',','')) if first_money(cred_str) else 0.0
                val_bal = float(first_money(bal_str).replace(',','')) if first_money(bal_str) else 0.0
                
                if is_noise_row({'description': desc}):
                    continue
                
                # Check for table headers specifically
                if "Money In" in desc or "Balance" in desc or "Narration" in desc:
                    continue

                transactions.append({
                    'date': last_date if last_date else "",
                    'description': desc,
                    'debit': val_deb,
                    'credit': val_cred,
                    'balance': val_bal,
                    'reference': "",
                    'remarks': desc,
                    'category': 'Uncategorized',
                    '_page': pg_num + 1
                })

    return transactions, {}
