import pdfplumber
import re
from pathlib import Path
from collections import defaultdict

def detect_fcmb_columns(words):
    header_keywords = ["TRAN.", "DETAILS", "DEBIT", "CREDIT", "BALANCE"]
    header_words = [w for w in words if any(k in w['text'].upper() for k in header_keywords)]
    
    if len(header_words) < 3:
        return None
        
    from collections import defaultdict
    y_groups = defaultdict(list)
    for w in words:
        y_groups[round(w['top'])].append(w)
        
    header_row = None
    for y in sorted(y_groups.keys()):
        row = sorted(y_groups[y], key=lambda w: w['x0'])
        row_text = " ".join([w['text'] for w in row]).upper()
        if all(k in row_text for k in ["DATE", "DETAILS", "BALANCE"]):
            header_row = row
            print(f"DEBUG: FCMB Header Found on Y={y}: {row_text}")
            break
            
    if not header_row:
        return None

    cuts = {}
    def find_x(keywords):
        for w in header_row:
            if any(k in w['text'].upper() for k in keywords):
                return w['x0'], w['x1']
        return None, None

    x_dt_l, _ = find_x(["TRAN", "DATE"])
    x_val_l, _ = find_x(["VALUE"])
    x_ref_l, _ = find_x(["REF"])
    x_det_l, _ = find_x(["DETAILS", "TRANSACTION"])
    x_deb_l, x_deb_r = find_x(["DEBIT"])
    x_cred_l, x_cred_r = find_x(["CREDIT"])
    x_bal_l, x_bal_r = find_x(["BALANCE"])

    if None in [x_dt_l, x_det_l, x_deb_l, x_cred_l, x_bal_l]: 
        return None

    date_right = x_val_l or x_ref_l or x_det_l
    cuts['date'] = (0, date_right - 2)
    cuts['description'] = (x_det_l - 2, x_deb_l - 5)
    cuts['debit'] = (x_deb_l - 5, x_cred_l - 5)
    cuts['credit'] = (x_cred_l - 5, x_bal_l - 5)
    cuts['balance'] = (x_bal_l - 5, 1000)
    
    return cuts

def extract_fcmb_via_coordinates(pdf_path: Path, config: dict):
    from pdf_extractor import parse_date_smart, first_money, is_noise_row
    
    transactions = []
    with pdfplumber.open(pdf_path) as pdf:
        cuts = None
        for i in range(min(3, len(pdf.pages))):
            words = pdf.pages[i].extract_words()
            print(f"DEBUG: FCMB Scan P{i} words: {len(words)}")
            cuts = detect_fcmb_columns(words)
            if cuts: break
            
        if not cuts: return [], {}

        last_date = None
        for pg_num, page in enumerate(pdf.pages):
            words = page.extract_words()
            new_cuts = detect_fcmb_columns(words)
            if new_cuts: cuts = new_cuts

            rows = defaultdict(list)
            for w in words:
                rows[round(w['top'])].append(w)
            
            for y in sorted(rows.keys()):
                row_words = sorted(rows[y], key=lambda w: w['x0'])
                data = {k: [] for k in cuts}
                
                for w in row_words:
                    # RIGHT-ALIGNED check for money
                    is_money = any(c.isdigit() for c in w['text']) and (',' in w['text'] or '.' in w['text'])
                    x_pos = w['x1'] if is_money else (w['x0'] + w['x1']) / 2
                    
                    for name, x0, x1 in [(k, v[0], v[1]) for k, v in cuts.items()]:
                        if x0 <= x_pos < x1:
                            data[name].append(w['text'])
                
                date_str = " ".join(data['date']).strip()
                desc = " ".join(data['description']).strip()
                
                # CRITICAL: Pick only ONE money string per row to avoid concatenation
                def pick_one(parts):
                    nums = [p for p in parts if any(c.isdigit() for c in p) and (',' in p or '.' in p)]
                    return nums[0] if nums else ""

                deb = pick_one(data['debit'])
                cred = pick_one(data['credit'])
                bal = pick_one(data['balance'])

                parsed_date = parse_date_smart(date_str)
                if parsed_date: last_date = parsed_date
                
                if not parsed_date and not (deb or cred): continue
                if is_noise_row({'description': desc}): continue
                if "DEBIT" in desc.upper() and "CREDIT" in desc.upper(): continue
                if "BALANCE BROUGHT FORWARD" in desc.upper().replace("  ", " "): continue
                if "BALANCE CARRIED FORWARD" in desc.upper().replace("  ", " "): continue
                
                # FCMB-specific: skip percentages at the end or empty descriptions
                if not desc.strip(): continue
                if '%' in deb or '%' in cred: continue

                if deb or cred:
                    print(f"DEBUG: FCMB Row P{pg_num+1} | Date: {last_date} | Deb: {deb} | Cred: {cred}")

                def safe_float(val_str):
                    if not val_str: return 0.0
                    clean = re.sub(r'[^\d.-]', '', val_str.replace('(', '-').replace(')', ''))
                    try:
                        return float(clean)
                    except ValueError:
                        return 0.0

                transactions.append({
                    'date': last_date if last_date else "",
                    'description': desc,
                    'debit': safe_float(deb),
                    'credit': safe_float(cred),
                    'balance': safe_float(bal),
                    'remarks': desc,
                    'category': 'Uncategorized'
                })
    return transactions, {}
