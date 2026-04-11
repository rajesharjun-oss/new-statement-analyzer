import json
import re
from typing import List, Dict, Tuple, Any

# Import shared utilities from pdf_extractor
try:
    from pdf_extractor import group_words_to_rows
except ImportError:
    # Fallback if running standalone
    def group_words_to_rows(words, y_tol=3.0):
        if not words:
            return []
        sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
        rows = []
        current_row = {"top": sorted_words[0]["top"], "words": [sorted_words[0]]}
        for w in sorted_words[1:]:
            if abs(w["top"] - current_row["top"]) <= y_tol:
                current_row["words"].append(w)
            else:
                rows.append(current_row)
                current_row = {"top": w["top"], "words": [w]}
        rows.append(current_row)
        return rows


def parse_uba_ocr_text(json_text: str) -> List[Dict[str, Any]]:
    """
    Parse UBA transactions from OCR JSON output.
    Expected JSON structure: { "header": [...], "rows": [ {"Txn Date": "...", ...} ] }
    """
    transactions = []
    
    try:
        data = json.loads(json_text)
        rows = data.get("rows", [])
        
        print(f"DEBUG: Parsed {len(rows)} JSON rows from OCR")
        
        for row in rows:
            def get_val(keys):
                for k in keys:
                    if k in row and row[k]:
                        return row[k]
                return ""

            trans_date = get_val(["Txn Date", "Trans Date", "Date", "TRANS DATE"])
            value_date = get_val(["Value Date", "Val Date", "VALUE DATE"]) or trans_date
            desc = get_val(["Description", "Narration", "Details", "Particulars", "NARRATION",
                            "Transaction Remarks", "Remarks"])
            ref = get_val(["Reference", "Ref", "Chq No", "Cheque No", "CHQ NO",
                           "Cheque Number"])

            def parse_amt(val):
                if not val or str(val).isspace(): return 0.0
                try:
                    s = str(val).replace(',', '').strip()
                    v = float(s)
                    # Safety Clamp: Reject hallucinated massive amounts (>10 Billion)
                    if abs(v) > 10000000000.0:
                        return 0.0
                    return v
                except: return 0.0

            debit = parse_amt(get_val(["Debit", "Dr", "DEBIT", "Withdrawal", "WITHDRAWAL"]))
            credit = parse_amt(get_val(["Credit", "Cr", "CREDIT", "Deposit", "DEPOSIT"]))
            balance = parse_amt(get_val(["Balance", "Bal", "BALANCE"]))
            
            if not trans_date:
                continue
            if debit == 0.0 and credit == 0.0:
                continue

            txn = {
                "date": trans_date,
                "value_date": value_date,
                "description": desc,
                "debit": debit,
                "credit": credit,
                "balance": balance,
                "reference": ref
            }
            transactions.append(txn)
            
    except json.JSONDecodeError as e:
        print(f"DEBUG: JSON parse error: {e}")
        if "```json" in json_text:
             try:
                 clean_json = json_text.split("```json")[1].split("```")[0].strip()
                 return parse_uba_ocr_text(clean_json)
             except:
                 pass
        print("DEBUG: Raw text was not valid JSON.")
        return []
        
    return transactions


def detect_uba_columns(words: List[Dict], bank_identifier: str = "") -> Dict[str, Tuple[float, float]] | None:
    """
    Detect UBA column boundaries from header row.
    Supports two template variants:
      Template A: TRANS DATE | VALUE DATE | NARRATION | CHQ NO | DEBIT | CREDIT | BALANCE
      Template B: Transaction | Value Date | Cheque Number | Transaction Remarks | Withdrawal | Deposit | Balance
    """
    if not words:
        return None

    # --- Step 1: Find the header row by scoring ---
    keywords = [
        "TRANSACTION", "TRANS", "VALUE", "DATE", "NARRATION", "REMARKS",
        "CHQ", "CHEQUE", "NUMBER", "DEBIT", "CREDIT", "BALANCE",
        "WITHDRAWAL", "DEPOSIT"
    ]

    rows = group_words_to_rows(words, y_tol=3.0)

    best_row = None
    best_row_idx = -1
    max_score = 0

    for idx, r in enumerate(rows):
        row_text_upper = " ".join([w["text"].upper() for w in r["words"]])

        # Mandatory: must have DATE and BALANCE
        if "DATE" not in row_text_upper:
            continue
        if "BALANCE" not in row_text_upper:
            continue
        # Must have at least one amount keyword
        if not any(x in row_text_upper for x in ["DEBIT", "CREDIT", "WITHDRAWAL", "DEPOSIT"]):
            continue

        score = 0
        for w in r["words"]:
            for k in keywords:
                if k in w["text"].upper():
                    score += 1

        if score > max_score:
            max_score = score
            best_row = r
            best_row_idx = idx

    if not best_row or max_score < 4:
        return None

    print(f"DEBUG: Found UBA Header Row: {[w['text'] for w in best_row['words']]}")

    # --- Step 2: Also check the row immediately below for multi-line headers ---
    # UBA Template B splits "Transaction" + "Date" and "Cheque" + "Number" across two rows
    header_words = list(best_row["words"])
    if best_row_idx + 1 < len(rows):
        next_row = rows[best_row_idx + 1]
        next_text = " ".join([w["text"].upper() for w in next_row["words"]])
        # If next row has "DATE" or "NUMBER" it's likely continuation
        if any(k in next_text for k in ["DATE", "NUMBER"]):
            header_words.extend(next_row["words"])
            print(f"DEBUG: UBA multi-line header, added row: {[w['text'] for w in next_row['words']]}")

    # Sort header words by x0
    sorted_words = sorted(header_words, key=lambda w: w["x0"])

    # --- Step 3: Find column anchors ---
    def find_word(text_part, start_idx=0):
        for i in range(start_idx, len(sorted_words)):
            if text_part in sorted_words[i]["text"].upper():
                return i, sorted_words[i]
        return -1, None

    bounds = {}

    # 1. Transaction Date / Trans Date
    idx_td, w_td = find_word("TRANS")
    if not w_td:
        idx_td, w_td = find_word("DATE")
    if w_td:
        bounds["date"] = (w_td["x0"], w_td["x1"])

    # 2. Value Date
    idx_vd, w_vd = find_word("VALUE")
    if w_vd:
        bounds["value_date"] = (w_vd["x0"], w_vd["x1"])

    # 3. Description (Narration / Transaction Remarks / Remarks / Description)
    idx_desc, w_desc = find_word("NARRATION")
    if not w_desc:
        idx_desc, w_desc = find_word("REMARKS")
    if not w_desc:
        idx_desc, w_desc = find_word("DESCRIPTION")
    if w_desc:
        bounds["description"] = (w_desc["x0"], w_desc["x1"])

    # 4. Reference (CHQ NO / Cheque Number)
    idx_ref, w_ref = find_word("CHQ")
    if not w_ref:
        idx_ref, w_ref = find_word("CHEQUE")
    if w_ref:
        bounds["reference"] = (w_ref["x0"], w_ref["x1"])

    # 5. Debit / Withdrawal
    idx_deb, w_deb = find_word("DEBIT")
    if not w_deb:
        idx_deb, w_deb = find_word("WITHDRAWAL")
    if w_deb:
        bounds["debit"] = (w_deb["x0"], w_deb["x1"])

    # 6. Credit / Deposit
    idx_cred, w_cred = find_word("CREDIT")
    if not w_cred:
        idx_cred, w_cred = find_word("DEPOSIT")
    if w_cred:
        bounds["credit"] = (w_cred["x0"], w_cred["x1"])

    # 7. Balance
    idx_bal, w_bal = find_word("BALANCE")
    if w_bal:
        bounds["balance"] = (w_bal["x0"], w_bal["x1"])

    # Mandatory: need at least date + one amount + balance
    if "date" not in bounds or ("debit" not in bounds and "credit" not in bounds):
        print("DEBUG: UBA detected header but missing critical columns")
        return None

    # --- Step 4: Build cuts with right-edge bias for numeric columns ---
    sorted_cols = sorted(bounds.items(), key=lambda item: item[1][0])

    cuts = {}
    for i in range(len(sorted_cols)):
        col_name, (l, r) = sorted_cols[i]

        if i == 0:
            start = 0.0
        else:
            prev_name, (prev_l, prev_r) = sorted_cols[i-1]
            # Tight boundary for description → give it max room
            if col_name == "description" and prev_name == "value_date":
                start = prev_r + 2
            elif col_name in ["debit", "credit", "balance"] and prev_name in ["debit", "credit"]:
                start = (prev_r + r) / 2
            else:
                start = (prev_r + l) / 2

        if i == len(sorted_cols) - 1:
            end = 1000.0
        else:
            next_name, (next_l, next_r) = sorted_cols[i+1]
            # Wide boundary for description
            if col_name == "description":
                end = next_l - 5
            elif col_name in ["debit", "credit"] and next_name in ["debit", "credit", "balance"]:
                end = (r + next_r) / 2
            else:
                end = (r + next_l) / 2

        cuts[col_name] = (start, end)

    print(f"DEBUG: UBA Column boundaries: {[(n, f'{l:.1f}-{r:.1f}') for n, (l, r) in cuts.items()]}")
    return cuts

import pdfplumber
from pathlib import Path

def extract_uba_via_coordinates(pdf_path: Path, metadata: Dict[str, Any], pdf: pdfplumber.PDF = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import parse_date_smart, parse_money, is_noise_row, group_words_to_rows, assign_row_to_cols, merge_multiline_rows
    
    # If pdf handle is provided, use it, otherwise open
    _auto_close = False
    if pdf is None:
        pdf = pdfplumber.open(pdf_path)
        _auto_close = True
        
    all_rows = []
    cuts = None
    
    try:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            if not words: continue
            
            # Re-detect cuts on every page to be safe
            page_cuts = detect_uba_columns(words)
            if page_cuts: cuts = page_cuts
            
            if not cuts: continue
            
            row_groups = group_words_to_rows(words, y_tol=3.0)
            for rg in row_groups:
                row = assign_row_to_cols(rg["words"], cuts)
                if is_noise_row(row): continue
                row["_page"] = page_num
                all_rows.append(row)
                
        txns = merge_multiline_rows(all_rows)
        # Final cleanup/parsing happens in map_uba_records or returning to extractor
        return txns, metadata
    finally:
        if _auto_close:
            pdf.close()
