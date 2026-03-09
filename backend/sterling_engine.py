import pdfplumber
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any

def detect_sterling_columns(words):
    """
    Detect Sterling Bank column bounds based on headers:
    Trans Date | Narration | Value Date | Money In | Money Out | Balance
    """
    header_keywords = ["DATE", "NARRATION", "MONEY", "IN", "OUT", "BALANCE", "TRANS", "VALUE"]
    header_words = [w for w in words if any(k in w['text'].upper() for k in header_keywords)]
    
    if len(header_words) < 3:
        return None
        
    from collections import defaultdict
    y_groups = defaultdict(list)
    for w in words:
        y_groups[round(w['top'])].append(w)

    # Find the anchor row containing "NARRATION" and "MONEY"
    anchor_row = None
    y_anchor = None
    for y in sorted(y_groups.keys()):
        row = sorted(y_groups[y], key=lambda w: w['x0'])
        row_text = " ".join([w['text'] for w in row]).upper()
        if "NARRATION" in row_text and "MONEY" in row_text:
            anchor_row = row
            y_anchor = y
            break
            
    if not anchor_row:
        return None

    # Sterling headers span 3 Y-lines:
    # Y=254: "Trans" + "Value" (the qualifier row)
    # Y=260: "Narration" + "Money In" + "Money Out" + "Balance" (the anchor row)
    # Y=266: "Date" + "Date" (the label row)
    # We need to find the qualifier row (with "Trans" and/or "Value")
    trans_value_row = anchor_row  # default
    for dy in [-10, -8, -6, -4, -2, 2, 4, 6, 8, 10, -12, -14, 12, 14]:
        y_test = y_anchor + dy
        if y_test in y_groups:
            test_text = " ".join([w['text'] for w in y_groups[y_test]]).upper()
            if "TRANS" in test_text or "VALUE" in test_text:
                trans_value_row = y_groups[y_test]
                break

    def find_x(snippets, target_row):
        matches = [w for w in target_row if any(s.upper() in w['text'].upper() for s in snippets)]
        if not matches: return None, None
        return min(m['x0'] for m in matches), max(m['x1'] for m in matches)

    # Use coordinates from respective rows
    x_date_l, _ = find_x(["DATE"], trans_value_row)
    x_narr_l, x_narr_r = find_x(["NARRATION"], anchor_row)
    
    # Find "Money In" and "Money Out" separately
    # "Money In" comes first (lower x), "Money Out" comes second (higher x)
    money_words = [w for w in anchor_row if "MONEY" in w['text'].upper()]
    in_words = [w for w in anchor_row if w['text'].upper() == "IN"]
    out_words = [w for w in anchor_row if w['text'].upper() == "OUT"]
    
    x_bal_l, x_bal_r = find_x(["BALANCE"], anchor_row)
    
    if x_narr_l is None or not money_words:
        return None
    
    # Sort money words by x to find Money In vs Money Out
    money_words_sorted = sorted(money_words, key=lambda w: w['x0'])
    
    if len(money_words_sorted) >= 2 and in_words and out_words:
        # Two separate "Money" labels
        money_in_x0 = money_words_sorted[0]['x0']
        money_in_x1 = max(w['x1'] for w in in_words if w['x0'] < money_words_sorted[1]['x0']) if in_words else money_words_sorted[0]['x1']
        money_out_x0 = money_words_sorted[1]['x0']
        money_out_x1 = max(w['x1'] for w in out_words) if out_words else money_words_sorted[1]['x1']
    elif len(money_words_sorted) == 1:
        # Single "Money" label — use In/Out words for boundaries
        if in_words and out_words:
            money_in_x0 = money_words_sorted[0]['x0']
            money_in_x1 = max(w['x1'] for w in in_words)
            money_out_x0 = min(w['x0'] for w in out_words) - 30
            money_out_x1 = max(w['x1'] for w in out_words)
        else:
            return None
    else:
        return None
    
    # Find Value Date position — the "Value" keyword is on the trans_value_row
    # It sits at x ~298, between Narration (ending ~280) and Money In (starting ~347)
    x_val_l, x_val_r = find_x(["VALUE"], trans_value_row)
    if x_val_l is None:
        x_val_l, x_val_r = find_x(["VALUE"], anchor_row)
    
    # Build cuts using ACTUAL DATA positions observed:
    # Trans Date: x:29-61
    # Narration/Description: x:80-282
    # Value Date: x:296-328
    # Money In (Credit): x:347-419
    # Money Out (Debit): x:421-492
    # Balance: x:508-567
    
    # Use midpoints between header groups as boundaries
    cuts = {}
    cuts['date'] = (0, x_narr_l - 2)
    
    # If we found Value Date, put it between Narration and Money In
    if x_val_l is not None:
        cuts['description'] = (x_narr_l - 2, x_val_l - 2)
        cuts['value_date'] = (x_val_l - 2, money_in_x0 - 2)
    else:
        cuts['description'] = (x_narr_l - 2, money_in_x0 - 2)
    
    # CRITICAL: Use midpoint between Money In right edge and Money Out left edge
    # to separate credit from debit
    credit_debit_boundary = (money_in_x1 + money_out_x0) / 2
    
    cuts['credit'] = (money_in_x0 - 2, credit_debit_boundary)
    cuts['debit'] = (credit_debit_boundary, money_out_x1 + 10)
    
    if x_bal_l:
        # Boundary between debit and balance
        debit_balance_boundary = (money_out_x1 + x_bal_l) / 2
        cuts['debit'] = (credit_debit_boundary, debit_balance_boundary)
        cuts['balance'] = (debit_balance_boundary, 1000)
    else:
        cuts['balance'] = (money_out_x1 + 10, 1000)
    
    print(f"DEBUG: Sterling column cuts: {cuts}")
    return cuts

def extract_sterling_via_coordinates(pdf_path: Path, config: dict):
    from pdf_extractor import parse_date_smart, first_money, is_noise_row
    
    transactions = []
    with pdfplumber.open(pdf_path) as pdf:
        cuts = None
        for i in range(min(5, len(pdf.pages))):
            words = pdf.pages[i].extract_words()
            print(f"DEBUG: Sterling Scan P{i} words: {len(words)}")
            cuts = detect_sterling_columns(words)
            if cuts: break
        
        if not cuts:
             return [], {}

        print(f"DEBUG: Sterling Cuts: {cuts}")
        
        col_list = [(name, b[0], b[1]) for name, b in cuts.items()]
        
        for pg_num, page in enumerate(pdf.pages):
            words = page.extract_words()
            
            # Update cuts per page if header found
            new_cuts = detect_sterling_columns(words)
            if new_cuts:
                cuts = new_cuts
                col_list = [(name, b[0], b[1]) for name, b in cuts.items()]

            # Group words by Y with tight tolerance
            rows_dict = {}
            for w in words:
                y = round(w['top'] / 2) * 2
                if y not in rows_dict: rows_dict[y] = []
                rows_dict[y].append(w)
            
            sorted_ys = sorted(rows_dict.keys())
            
            for y_idx, y in enumerate(sorted_ys):
                row_words = sorted(rows_dict[y], key=lambda w: w['x0'])
                row_data = {name: [] for name, _, _ in col_list}
                
                for w in row_words:
                    mid_x = (w['x0'] + w['x1']) / 2
                    for name, x0, x1 in col_list:
                        if x0 <= mid_x < x1:
                            row_data[name].append(w['text'])
                
                desc = " ".join(row_data.get('description', [])).strip()
                date_str = " ".join(row_data.get('date', [])).strip()
                val_date_str = " ".join(row_data.get('value_date', [])).strip()
                deb_str = " ".join(row_data.get('debit', [])).strip()
                cred_str = " ".join(row_data.get('credit', [])).strip()
                bal_str = " ".join(row_data.get('balance', [])).strip()
                
                # Sterling dates are split: "08-Jan-" on one line, "2024" on the next
                # Try to merge if date ends with "-" and next row has just a year
                if date_str.endswith('-'):
                    if y_idx + 1 < len(sorted_ys):
                        next_y = sorted_ys[y_idx + 1]
                        next_row = sorted(rows_dict[next_y], key=lambda w: w['x0'])
                        next_date_parts = [w['text'] for w in next_row if w['x0'] < cuts['date'][1]]
                        if next_date_parts:
                            year_candidate = next_date_parts[0].strip()
                            if re.match(r'^\d{4}$', year_candidate):
                                date_str = date_str + year_candidate
                
                # Also merge value dates that are split
                if val_date_str.endswith('-'):
                    if y_idx + 1 < len(sorted_ys):
                        next_y = sorted_ys[y_idx + 1]
                        next_row = sorted(rows_dict[next_y], key=lambda w: w['x0'])
                        if 'value_date' in cuts:
                            vd_lo, vd_hi = cuts['value_date']
                            next_val_parts = [w['text'] for w in next_row if vd_lo <= (w['x0'] + w['x1'])/2 < vd_hi]
                            if next_val_parts:
                                year_candidate = next_val_parts[0].strip()
                                if re.match(r'^\d{4}$', year_candidate):
                                    val_date_str = val_date_str + year_candidate
                
                parsed_date = parse_date_smart(date_str)
                parsed_val_date = parse_date_smart(val_date_str)
                
                # Skip standalone year lines (they've been merged above)
                if re.match(r'^\d{4}$', date_str.strip()) and not desc and not deb_str and not cred_str:
                    continue
                
                has_money = first_money(deb_str) or first_money(cred_str)
                
                # Skip noise rows
                full_text = (desc + " " + date_str).upper()
                if is_noise_row({'description': desc}):
                    continue
                if "Money In" in desc or "Narration" in desc:
                    continue
                # Skip summary/header rows
                if any(kw in full_text for kw in [
                    "OPENING BALANCE", "CLOSING BALANCE", "AVAILABLE BALANCE",
                    "TOTAL CREDIT", "TOTAL DEBIT", "DATE RANGE",
                    "OPENING", "CLOSING", "BUSINESS-MINIMUM",
                ]):
                    continue
                # Skip if description is just balance/summary text
                if re.match(r'^balance:', desc, re.I):
                    continue
                
                if not parsed_date and not has_money:
                    # Check if this is a continuation line (has description text)
                    if desc and transactions:
                        transactions[-1]['description'] = (transactions[-1]['description'] + " " + desc).strip()
                        transactions[-1]['remarks'] = transactions[-1]['description']
                    continue
                
                # If we have money but no date, it's likely a row where the date was on a previous line
                if has_money and not parsed_date and transactions:
                    # Attach to previous transaction if it has no money yet
                    if transactions[-1]['debit'] == 0.0 and transactions[-1]['credit'] == 0.0:
                        val_deb = float(first_money(deb_str).replace(',','')) if first_money(deb_str) else 0.0
                        val_cred = float(first_money(cred_str).replace(',','')) if first_money(cred_str) else 0.0
                        val_bal = float(first_money(bal_str).replace(',','')) if first_money(bal_str) else 0.0
                        transactions[-1]['debit'] = val_deb
                        transactions[-1]['credit'] = val_cred
                        transactions[-1]['balance'] = val_bal
                        if desc:
                            transactions[-1]['description'] = (transactions[-1]['description'] + " " + desc).strip()
                            transactions[-1]['remarks'] = transactions[-1]['description']
                        continue
                
                val_deb = float(first_money(deb_str).replace(',','')) if first_money(deb_str) else 0.0
                val_cred = float(first_money(cred_str).replace(',','')) if first_money(cred_str) else 0.0
                val_bal = float(first_money(bal_str).replace(',','')) if first_money(bal_str) else 0.0

                transactions.append({
                    'date': parsed_date or "",
                    'value_date': parsed_val_date or parsed_date or "",
                    'description': desc,
                    'debit': val_deb,
                    'credit': val_cred,
                    'balance': val_bal,
                    'reference': "",
                    'remarks': desc,
                    'category': 'Uncategorized',
                    '_page': pg_num + 1
                })

    # Post-process: remove transactions with no date AND no money (orphan continuation lines)
    transactions = [t for t in transactions if t['date'] or t['debit'] or t['credit']]
    
    return transactions, {}
