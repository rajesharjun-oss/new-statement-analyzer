import os
import google.generativeai as genai
from PIL import Image
import io
import fitz
from dotenv import load_dotenv
from pathlib import Path
from typing import Dict, List, Tuple, Any
import re
import pdfplumber

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

def detect_columns_via_vision(pdf_path: Path, page_index: int = 0) -> Dict[str, Tuple[float, float]] | None:
    """Uses Gemini Vision to identify column boundaries when text-based parsing fails."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("DEBUG [Access-Vision]: No GEMINI_API_KEY found.")
        return None
    
    try:
        genai.configure(api_key=api_key)
        # Using gemini-2.0-flash for speed/quota
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        doc = fitz.open(str(pdf_path))
        page = doc[page_index]
        # High DPI for better recognition
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        
        prompt = """
        Identify the horizontal (x) boundaries for these columns in the bank statement:
        Date, Description, Reference, Value Date, Debit/Withdrawal, Credit/Deposit, Balance.
        Return ONLY a JSON object: {"date": [x0, x1], "description": [x0, x1], "reference": [x0, x1], "value_date": [x0, x1], "debit": [x0, x1], "credit": [x0, x1], "balance": [x0, x1]}
        Use a scale of 0 to 600 (standard PDF points). If a column is missing, omit it from JSON.
        """
        
        response = model.generate_content([prompt, img])
        raw_text = response.text
        # Extract JSON from potential markdown
        import json
        match = re.search(r"({.*})", raw_text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            # Conver to Tuples
            return {k: (float(v[0]), float(v[1])) for k, v in data.items()}
    except Exception as e:
        print(f"DEBUG [Access-Vision]: Vision detection failed: {e}")
    return None

def detect_access_columns(words: List[Dict[str, Any]], bank_identifier: str = None, pdf_path: Path = None) -> Dict[str, Tuple[float, float]] | None:
    """
    Detect column boundaries for Access Bank.
    Handles multiple template variants including:
    - Standard: TRANSACTION DETAILS | REFERENCE | WITHDRAWALS | LODGEMENTS | BALANCE
    - Variant 2: Date | Transaction Details | Reference | Value Date | Withdrawals | Lodgements | Balance
    - Variant 3: Posted Date | Value Date | Description/Remarks | Reference | Debit | Credit | Balance
    """
    if not words: 
        print("DEBUG [Access]: detect_access_columns received 0 words.")
        return None
    
    import sys
    print(f"DEBUG [Access]: detect_access_columns received {len(words)} words.")
    sys.stdout.flush()

    # 1. FIND HEADER BANDS
    keywords = [
        "DATE", "TRANSACTION", "DETAILS", "DESCRIPTION", "NARRATION",
        "REFERENCE", "REF", "VALUE", "WITHDRAWAL", "WITHDRAWALS", "DEBIT",
        "LODGEMENT", "LODGEMENTS", "CREDIT", "DEPOSIT", "DEPOSITS",
        "BALANCE", "BAL", "POSTED", "REMARKS"
    ]
    
    header_words = []
    for w in words:
        txt = (w.get("text") or "").upper().strip()
        for k in keywords:
            if k in txt:
                header_words.append(w)
                break
    
    if not header_words:
        if pdf_path:
            print("DEBUG [Access]: No header words found. Trying AI Vision Fallback...")
            sys.stdout.flush()
            vision_cuts = detect_columns_via_vision(pdf_path)
            if vision_cuts:
                return vision_cuts
        return None

    rows = {}
    for w in header_words:
        y = round(w['top'])
        if y not in rows: rows[y] = []
        rows[y].append(w)
    
    best_y = -1
    max_indicators = 0
    for y, row_words in rows.items():
        band = [w for w in header_words if abs(w['top'] - y) < 8.0]
        inds = set()
        for wb in band:
            t = wb["text"].upper()
            for k in keywords:
                if k in t: inds.add(k)
        
        if len(inds) >= max_indicators:
            max_indicators = len(inds)
            best_y = y
            
    if max_indicators < 4:
        if pdf_path:
            print(f"DEBUG [Access]: Rule-based detection weak ({max_indicators} indicators). Trying AI Vision Fallback...")
            vision_cuts = detect_columns_via_vision(pdf_path)
            if vision_cuts:
                return vision_cuts
        return None

    active_band = [w for w in header_words if abs(w['top'] - best_y) < 8.0]
    
    def find_x(subs, is_right=False):
        found_matches = []
        for word_dict in active_band:
            original_text = word_dict.get("text", "")
            if original_text is None:
                continue
            
            upper_text = str(original_text).upper().strip()
            
            for s in subs:
                search_term = str(s).upper().strip()
                match = search_term in upper_text
                if match:
                    found_matches.append(word_dict)
                    break # Found a match for this word
                    
        if not found_matches: 
            return None
        val = max(m["x1"] for m in found_matches) if is_right else min(m["x0"] for m in found_matches)
        return val

    # 2. EXTRACT COORDINATES
    x_date = find_x(["Date", "Posted"])
    x_details = find_x(["Details", "Transaction", "Description", "Narration", "Remarks"])
    x_ref = find_x(["Ref", "Reference"])
    x_val = find_x(["Value"])
    x_with = find_x(["Withdrawal", "Withdrawals", "Debit"], is_right=True)
    x_lodge = find_x(["Lodgement", "Lodgements", "Credit", "Deposit", "Deposits"], is_right=True)
    x_bal = find_x(["Balance", "Bal"], is_right=True)

    if not all([x_date, x_details, x_ref, x_with or x_lodge, x_bal]):
        if pdf_path:
            print(f"DEBUG [Access]: Missing core columns. Trying AI Vision Fallback...")
            sys.stdout.flush()
            vision_cuts = detect_columns_via_vision(pdf_path)
            if vision_cuts:
                return vision_cuts
        return None

    # 3. CONSTRUCT CUTS (Midpoint based for max width)
    # Goal: Use the space between headers as boundaries to avoid clipping large numbers
    
    # Sort detected headers by their x-coordinate to build a sequence
    # We use (name, left, right)
    header_anchors = []
    if x_date is not None: header_anchors.append(("date", x_date, x_date + 40))
    if x_details is not None: header_anchors.append(("description", x_details, x_details + 60))
    if x_ref is not None: header_anchors.append(("reference", x_ref, x_ref + 40))
    if x_val is not None: header_anchors.append(("value_date", x_val, x_val + 40))
    
    # Money columns are usually right-aligned or centered under wide headers
    # For Access 2.0: Withdrawals (320-385), Lodgements (420-466), Balance (509-562)
    # WIDENING to 100 to avoid clipping large amounts (e.g. 100,000,000.00)
    if x_with is not None: header_anchors.append(("debit", x_with - 100, x_with + 20))
    if x_lodge is not None: header_anchors.append(("credit", x_lodge - 100, x_lodge + 20))
    if x_bal is not None: header_anchors.append(("balance", x_bal - 100, x_bal + 20))
    
    header_anchors.sort(key=lambda x: x[1])
    
    cuts = {}
    for i in range(len(header_anchors)):
        name, h_left, h_right = header_anchors[i]
        
        # Left boundary: midpoint to previous anchor's right, or 0
        if i == 0:
            start = 0.0
        else:
            prev_name, prev_l, prev_r = header_anchors[i-1]
            start = (prev_r + h_left) / 2
            
        # Right boundary: midpoint to next anchor's left, or 1000
        if i == len(header_anchors) - 1:
            end = 1000.0
        else:
            next_name, next_l, next_r = header_anchors[i+1]
            end = (h_right + next_l) / 2
            
        cuts[name] = (start, end)

    print(f"DEBUG [Access]: Generated cuts: {cuts}")
    return cuts

def extract_access_via_coordinates(pdf_path: Path, metadata: Dict[str, Any], pdf: pdfplumber.PDF = None, max_pages: int = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import parse_date_smart, first_money, is_noise_row
    import pandas as pd
    money_token_re = re.compile(r"\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})\)?|\(?-?\d+(?:\.\d{1,2})\)?")

    def _first_money_token(text: str) -> str:
        tokens = money_token_re.findall((text or "").replace("?", ""))
        return tokens[0] if tokens else ""

    def _last_money_token(text: str) -> str:
        tokens = money_token_re.findall((text or "").replace("?", ""))
        return tokens[-1] if tokens else ""

    def _money_to_float(tok: str) -> float:
        s = (tok or "").strip()
        if not s:
            return 0.0
        neg = s.startswith("(") and s.endswith(")")
        if neg:
            s = s[1:-1]
        s = s.replace(",", "")
        try:
            val = float(s)
            return -val if neg else val
        except Exception:
            return 0.0
    
    def _parse_access_date(date_str: str) -> str | None:
        """
        Access Bank uses M/D/YYYY (US format) for transaction dates.
        e.g. 10/1/2025 = October 1, 2025 (NOT January 10, 2025)
        But Value Date uses DD-MMM-YYYY (e.g. 01-Oct-2025).
        """
        s = (date_str or "").strip()
        if not s or len(s) < 6:
            return None

        # Access rows often begin with serial numbers and trailing narration.
        # Keep only the date-like token before parsing.
        s = re.sub(r"^\s*\d+\s+", "", s)
        for pat in [r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", r"\b\d{1,2}-[A-Za-z]{3}-\d{2,4}\b"]:
            m = re.search(pat, s)
            if m:
                s = m.group(0)
                break
        
        # If it contains slashes, treat as M/D/YYYY (Access Bank US format)
        if "/" in s:
            try:
                dt = pd.to_datetime(s, dayfirst=False, errors='coerce')
                if pd.notna(dt):
                    return dt.strftime("%d-%b-%Y")
            except:
                pass
            
        # Otherwise fallback to the standard parser
        return parse_date_smart(s)
    
    txns = []
    
    # If pdf handle is provided, use it, otherwise open
    if pdf is None:
        _pdf_handle = pdfplumber.open(pdf_path)
        _auto_close = True
    else:
        _pdf_handle = pdf
        _auto_close = False
        
    try:
        # Dynamic cuts: start with None, then update on each page if a header is found
        cuts = None
        
        # We still do a pre-scan of first 5 pages just to see if we can identify it at all
        for pg_idx in range(min(5, len(_pdf_handle.pages))):
            words = _pdf_handle.pages[pg_idx].extract_words()
            if detect_access_columns(words, pdf_path=pdf_path):
                print(f"DEBUG [Access]: Initial header signature found on page {pg_idx}")
                break
        else:
            print(f"DEBUG [Access]: No Access header signature found in first 5 pages.")
            return [], metadata
             
        print(f"DEBUG: Active Access Cuts: {cuts}")
        
        pending_description = ""
        pending_reference = ""
        
        txns = []
        target_pages = _pdf_handle.pages
        if max_pages:
            target_pages = target_pages[:max_pages]
            
        for pg_num, page in enumerate(target_pages):
            words = page.extract_words()
            
            # Update cuts for THIS page if a header is present
            new_cuts = detect_access_columns(words, pdf_path=pdf_path)
            if new_cuts:
                cuts = new_cuts
                print(f"DEBUG [Access]: Cuts updated for page {pg_num}")
            
            if not cuts:
                continue
                
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
                        # Use x0 (left edge) for all words — Access amounts are left-to-right aligned;
                        # using x1 shifts large amounts one column right (e.g. 2,687,500 credited as debit)
                        val = w['x0']
                        
                        if min_x <= val < max_x:
                            row_dict[col_name].append(w['text'])
                            break
                
                # Join bucket contents
                row_dict = {k: " ".join(v).strip() for k, v in row_dict.items()}
                
                if not any(row_dict.values()):
                    continue
                    
                date_str = row_dict.get("date", "")
                value_date_str = row_dict.get("value_date", "")
                parsed_value_date = _parse_access_date(value_date_str)
                parsed_date = _parse_access_date(date_str) or parsed_value_date
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
                    debit_str = _first_money_token(row_dict.get("debit", "")) or first_money(row_dict.get("debit", ""))
                    credit_str = _first_money_token(row_dict.get("credit", "")) or first_money(row_dict.get("credit", ""))
                    # Balance cells in this Access format may contain both "0.00 <balance>".
                    # Last token is the true running balance.
                    bal_str = _last_money_token(row_dict.get("balance", "")) or first_money(row_dict.get("balance", ""))

                    debit = _money_to_float(debit_str)
                    credit = _money_to_float(credit_str)
                    bal = _money_to_float(bal_str)
                    
                    txn = {
                        "date": parsed_date,
                        "value_date": parsed_value_date or parsed_date,
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

    finally:
        if _auto_close:
            _pdf_handle.close()

    return txns, metadata
