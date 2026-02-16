import json
from typing import List, Dict, Tuple, Any

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
            # Map JSON keys to our standard schema
            # Keys might vary slightly depending on OCR, so we try a few variants
            
            def get_val(keys):
                for k in keys:
                    if k in row and row[k]:
                        return row[k]
                return ""

            # Date
            trans_date = get_val(["Txn Date", "Trans Date", "Date", "TRANS DATE"])
            value_date = get_val(["Value Date", "Val Date", "VALUE DATE"]) or trans_date
            
            # Description
            desc = get_val(["Description", "Narration", "Details", "Particulars", "NARRATION"])
            
            # Reference
            ref = get_val(["Reference", "Ref", "Chq No", "Cheque No", "CHQ NO"])
            
            # Amounts
            def parse_amt(val):
                if not val: return 0.0
                if isinstance(val, (int, float)): return float(val)
                return float(str(val).replace(',', '').replace(' ', ''))

            debit = parse_amt(get_val(["Debit", "Dr", "DEBIT"]))
            credit = parse_amt(get_val(["Credit", "Cr", "CREDIT"]))
            balance = parse_amt(get_val(["Balance", "Bal", "BALANCE"]))
            
            if not trans_date:
                continue
            
            # USER REQUEST: Filter non-zero transactions
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
        # Logic to handle if it returned markdown json code block?
        # Typically "```json ... ```"
        if "```json" in json_text:
             try:
                 clean_json = json_text.split("```json")[1].split("```")[0].strip()
                 return parse_uba_ocr_text(clean_json)
             except:
                 pass
        print("DEBUG: Raw text was not valid JSON.")
        return []
        
    return transactions

def detect_uba_columns(words: List[Dict], bank_identifier: str) -> Dict[str, Tuple[float, float]] | None:
    # ... (Keep existing layout layouts logic)
    """
    Detect UBA column boundaries
    Headers: TRANS DATE | VALUE DATE | NARRATION | CHQ NO | DEBIT | CREDIT | BALANCE
    """
    if bank_identifier != "uba":
        return None
    
    # Look for UBA header tokens (7 columns)
    header_tokens = {
        "TRANS": [], "DATE": [], "VALUE": [], "NARRATION": [],
        "CHQ": [], "NO": [], "DEBIT": [], "CREDIT": [], "BALANCE": [],
        "REMARKS": [] # Fallback
    }
    
    for w in words:
        txt = w["text"].upper().strip()
        if txt in header_tokens:
            header_tokens[txt].append(w)
    
    # Build column candidates
    columns = []
    
    # 1. TRANS DATE
    if header_tokens["TRANS"] and header_tokens["DATE"]:
        # Find TRANS closest to left, then closest DATE to its right
        trans = min(header_tokens["TRANS"], key=lambda w: w["x0"])
        dates = [d for d in header_tokens["DATE"] if d["x0"] > trans["x0"] and d["top"] < trans["bottom"] + 10]
        if dates:
            date1 = min(dates, key=lambda w: w["x0"])
            columns.append(("date", trans["x0"], date1["x1"]))
            
    # 2. VALUE DATE
    if header_tokens["VALUE"] and len(header_tokens["DATE"]) >= 2:
        value = min(header_tokens["VALUE"], key=lambda w: w["x0"])
        dates = [d for d in header_tokens["DATE"] if d["x0"] > value["x0"] and d["top"] < value["bottom"] + 10]
        if dates:
            date2 = min(dates, key=lambda w: w["x0"])
            columns.append(("value_date", value["x0"], date2["x1"]))

    # 3. NARRATION (or Remarks)
    if header_tokens["NARRATION"]:
        narr = header_tokens["NARRATION"][0]
        columns.append(("description", narr["x0"], narr["x1"]))
    elif header_tokens["REMARKS"]:
        rem = header_tokens["REMARKS"][0]
        columns.append(("description", rem["x0"], rem["x1"]))

    # 4. CHQ NO
    # Sometimes it's split "CHQ" "NO"
    if header_tokens["CHQ"]:
        chq = header_tokens["CHQ"][0]
        # Check for NO
        no_candidates = [n for n in header_tokens["NO"] if n["x0"] > chq["x0"] and n["top"] < chq["bottom"] + 10]
        right_edge = chq["x1"]
        if no_candidates:
            no = min(no_candidates, key=lambda w: w["x0"])
            right_edge = no["x1"]
        
        columns.append(("reference", chq["x0"], right_edge))

    # 5. DEBIT
    if header_tokens["DEBIT"]:
        deb = header_tokens["DEBIT"][0]
        columns.append(("debit", deb["x0"], deb["x1"]))
    
    # 6. CREDIT
    if header_tokens["CREDIT"]:
        cred = header_tokens["CREDIT"][0]
        columns.append(("credit", cred["x0"], cred["x1"]))
    
    # 7. BALANCE
    if header_tokens["BALANCE"]:
        bal = header_tokens["BALANCE"][0]
        columns.append(("balance", bal["x0"], bal["x1"]))
    
    if len(columns) < 5:  # Allow missing CHQ NO but need basics
        return None
    
    # Sort by x0
    columns.sort(key=lambda c: c[1])
    
    # Assign names based on sorted order to be safe? 
    # Or trust the header finding. Trust headers.
    
    # Build cuts map: name -> (left_boundary, right_boundary)
    cuts = {}
    for i, (name, left_start, right_end) in enumerate(columns):
        # Left Bound:
        # If first column, 0.
        # Else, midpoint between prev_right and curr_left?
        # Or just use prev_right (tight packing).
         
        if i == 0:
            left_bound = 0
        else:
            prev_right = columns[i-1][2]
            # Give slightly more space to the description column if possible?
            # Standard approach: split difference
            left_bound = (prev_right + left_start) / 2
            
            # Correction: NARRATION is usually wide.
            # If prev is ValueDate and curr is Narration
            if columns[i-1][0] == "value_date" and name == "description":
                left_bound = prev_right + 2 # Tight to ValueDate
        
        # Right Bound
        # If last column, explicit right_end + margin (or page width)
        # Else, next column's left bound
        
        if i == len(columns) - 1:
             right_bound = 1000 # Max width
        else:
             # Next column's start
             next_left = columns[i+1][1]
             # Midpoint
             right_bound = (right_end + next_left) / 2
             
             # Correction: Narration end
             if name == "description":
                 right_bound = columns[i+1][1] - 5 # Give content to text, nums align right usually.
        
        cuts[name] = (left_bound, right_bound)

    return cuts
