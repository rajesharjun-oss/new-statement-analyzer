import pdfplumber
import re
from pathlib import Path
from collections import defaultdict

def _clean_header_text(text):
    return re.sub(r"\s+", " ", (text or "").replace("\x00", "")).strip().upper()

def _detect_fcmb_layout(words):
    if not words:
        return None

    header_keywords = [
        "TRAN", "DATE", "VALUE", "REF", "DETAILS", "DESCRIP",
        "DEBIT", "CREDIT", "DEPOSIT", "WITHDRAWAL", "BALANCE",
    ]
    header_words = [
        w for w in words
        if any(k in _clean_header_text(w.get("text")) for k in header_keywords)
    ]

    if len(header_words) < 3:
        return None

    y_groups = defaultdict(list)
    for w in words:
        y_groups[round(w["top"])].append(w)

    header_row = None
    for y in sorted(y_groups.keys()):
        row = sorted(y_groups[y], key=lambda w: w["x0"])
        row_text = _clean_header_text(" ".join(w.get("text", "") for w in row))
        has_date = "DATE" in row_text
        has_desc = "DETAIL" in row_text or "DESCRIP" in row_text
        has_amount = any(k in row_text for k in ["DEBIT", "CREDIT", "DEPOSIT", "WITHDRAW"])
        if has_date and has_desc and has_amount and "BALANCE" in row_text:
            header_row = row
            print(f"DEBUG: FCMB Header Found on Y={y}: {row_text}")
            break

    if not header_row:
        return None

    sorted_words = sorted(header_row, key=lambda w: w["x0"])

    def find_word(*keywords):
        for w in sorted_words:
            clean = _clean_header_text(w.get("text"))
            if any(k in clean for k in keywords):
                return w
        return None

    def add_bound(bounds, name, word):
        if word:
            bounds[name] = (float(word["x0"]), float(word["x1"]))

    bounds = {}
    date_word = None
    for w in sorted_words:
        clean = _clean_header_text(w.get("text"))
        if clean == "DATE" or "TRAN" in clean:
            date_word = w
            break
    add_bound(bounds, "date", date_word)
    add_bound(bounds, "reference", find_word("REF"))
    add_bound(bounds, "description", find_word("DETAIL", "DESCRIP"))
    add_bound(bounds, "value_date", find_word("VALUE"))
    add_bound(bounds, "credit", find_word("CREDIT", "DEPOSIT"))
    add_bound(bounds, "debit", find_word("DEBIT", "WITHDRAW"))
    add_bound(bounds, "balance", find_word("BALANCE"))

    if not all(k in bounds for k in ["date", "description", "debit", "credit", "balance"]):
        return None

    sorted_cols = sorted(bounds.items(), key=lambda item: item[1][0])
    cuts = {}
    for i, (col_name, (left, right)) in enumerate(sorted_cols):
        if i == 0:
            start = 0.0
        else:
            _prev_name, (_prev_left, prev_right) = sorted_cols[i - 1]
            start = (prev_right + left) / 2

        if i == len(sorted_cols) - 1:
            end = 1000.0
        else:
            _next_name, (next_left, _next_right) = sorted_cols[i + 1]
            end = (right + next_left) / 2

        cuts[col_name] = (start, end)

    return cuts, max(float(w.get("bottom", w["top"])) for w in header_row)

def detect_fcmb_columns(words):
    layout = _detect_fcmb_layout(words)
    if not layout:
        return None
    cuts, _header_bottom = layout
    return cuts

def extract_fcmb_via_coordinates(pdf_path: Path, metadata: dict, pdf: pdfplumber.PDF = None):
    from pdf_extractor import parse_date_smart, first_money, is_noise_row, parse_statement_metadata
    
    transactions = []
    
    # If pdf handle is provided, use it, otherwise open
    if pdf is None:
        _pdf_handle = pdfplumber.open(pdf_path)
        _auto_close = True
    else:
        _pdf_handle = pdf
        _auto_close = False
        
    try:
        try:
            first_text = _pdf_handle.pages[0].extract_text() or ""
            parsed_meta = parse_statement_metadata(first_text)
            metadata.update({k: v for k, v in parsed_meta.items() if v not in (None, "")})
        except Exception as e:
            print(f"DEBUG: FCMB metadata parse skipped: {e}")

        cuts = None
        header_bottom = None
        for i in range(min(3, len(_pdf_handle.pages))):
            words = _pdf_handle.pages[i].extract_words()
            print(f"DEBUG: FCMB Scan P{i} words: {len(words)}")
            layout = _detect_fcmb_layout(words)
            if layout:
                cuts, header_bottom = layout
                break
            
        if not cuts: return [], {}

        last_date = None
        for pg_num, page in enumerate(_pdf_handle.pages):
            words = page.extract_words()
            layout = _detect_fcmb_layout(words)
            page_header_bottom = None
            if layout:
                cuts, page_header_bottom = layout
                header_bottom = page_header_bottom

            rows = defaultdict(list)
            for w in words:
                rows[round(w['top'])].append(w)
            
            for y in sorted(rows.keys()):
                if page_header_bottom is not None and y <= page_header_bottom + 1:
                    continue

                row_words = sorted(rows[y], key=lambda w: w['x0'])
                data = {k: [] for k in cuts}
                
                for w in row_words:
                    x_pos = (w['x0'] + w['x1']) / 2
                    
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
                value_date = " ".join(data.get('value_date', [])).strip()
                reference = " ".join(data.get('reference', [])).strip()

                parsed_date = parse_date_smart(date_str)
                if parsed_date: last_date = parsed_date
                
                if not (deb or cred): continue
                if not parsed_date and not last_date: continue
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
                    'value_date': value_date,
                    'reference': reference,
                    'description': desc,
                    'debit': safe_float(deb),
                    'credit': safe_float(cred),
                    'balance': safe_float(bal),
                    'remarks': " ".join(p for p in [reference, desc] if p).strip(),
                    'category': 'Uncategorized'
                })
    finally:
        if _auto_close:
            _pdf_handle.close()

    return transactions, metadata
