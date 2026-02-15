import re
import pdfplumber
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime

# --- User's Provided Logic & Regex ---
# Enhanced money token regex: 
# 1. Negative Lookbehind `(?<![\d-])`: Don't match if preceded by Digit or Dash (prevents "Jun-2025")
# 2. Match standard amounts with commas: `\d{1,3}(?:,\d{3})+`
# 3. Match integers/decimals: `\d+(?:\.\d+)?`
# 4. Negative Lookahead `(?!\d)`: Don't match if followed by digit.
# 5. Dash as zero: `(?<!\w)-(?!\w)`
money_token_re = re.compile(r'(?<![\d-])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d)|(?<!\w)-(?!\w)')

def normalize_split_decimals(tokens: List[str]) -> List[str]:
    """
    Joins patterns like:
    - ["13,046,880.", "13"] -> "13,046,880.13" (Trailing dot)
    - ["14,156,559.6", "7"] -> "14,156,559.67" (Split decimal part)
    - ["12,500,000", "00"] -> "12,500,000.00" (Implicit dot/Space separator)
    - ["12,500,000", ".", "00"] -> "12,500,000.00" (Detached dot)
    """
    out = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        
        # Look ahead
        next_t = tokens[i+1] if i + 1 < len(tokens) else None
        next_next_t = tokens[i+2] if i + 2 < len(tokens) else None

        # Case 1: Trailing dot ("123." + "45")
        if t.endswith('.') and next_t and re.fullmatch(r'\d{1,2}', next_t):
            out.append(t + next_t)
            i += 2
            
        # Case 2: Split decimal part ("123.6" + "7") -> "123.67"
        elif re.search(r'\.\d$', t) and next_t and re.fullmatch(r'\d', next_t):
            out.append(t + next_t)
            i += 2

        # Case 3: Detached dot ("123" + "." + "45")
        elif t.replace(',', '').isdigit() and next_t == '.' and next_next_t and re.fullmatch(r'\d{1,2}', next_next_t):
             out.append(t + "." + next_next_t)
             i += 3

        # Case 4: Implicit dot / Space ("123" + "45")
        elif t.replace(',', '').isdigit() and next_t and re.fullmatch(r'\d{2}', next_t):
            out.append(t + "." + next_t)
            i += 2
            
        else:
            out.append(t)
            i += 1
    return out

def parse_amounts_from_row_text(row_text: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Extracts Debit, Credit, Balance from the row text.
    Assumes order: ... Debit Credit Balance
    Returns (Debit, Credit, Balance) floats, or (None, None, None) if ambiguous.
    """
    # Replace newlines with space for cleaner regex matching
    clean_text = row_text.replace('\n', ' ')
    
    # Capture ALL potential number-like tokens (including noise integers)
    toks = money_token_re.findall(clean_text)
    
    # Merge split decimals
    toks = normalize_split_decimals(toks)
    
    # FILTER: Keep only tokens that look like Money (have dot OR are dash)
    # AND are not years or huge ref numbers
    valid_money_toks = []
    for t in toks:
        is_money_format = '.' in t or t.strip() == '-'
        if not is_money_format:
            continue
            
        # Refine: Discard if it looks like a Year (1990-2030)
        # Even if it has a dot? E.g. "2025.01" (created by bad merge? No, regex fix helps).
        # But let's be safe.
        try:
            val = float(t.replace(',', ''))
            # Filter Years
            if 1990 <= val <= 2030 and ',' not in t: 
                 continue
            # Filter huge integers that might have picked up a decimal (RefNos)
            # RefNos are usually > 100,000,000 and have NO commas.
            # Real large amounts usually have commas.
            # Exception: 12500000.00 might not have commas if extracted poorly?
            # But pdfplumber usually preserves them.
            if val > 100000000 and ',' not in t:
                 continue
                 
        except:
            pass

        valid_money_toks.append(t)
    
    if len(valid_money_toks) < 3:
        return None, None, None

    # Take last 3 valid tokens
    debit_s, credit_s, bal_s = valid_money_toks[-3], valid_money_toks[-2], valid_money_toks[-1]
    
    def f(x):
        if x.strip() == '-':
            return 0.0
        clean = x.replace(',', '')
        try:
            return float(clean)
        except:
            return 0.0

    return f(debit_s), f(credit_s), f(bal_s)

def parse_date(date_str):
    try:
        return datetime.strptime(str(date_str).strip(), '%d-%b-%Y').strftime('%Y-%m-%d')
    except:
        return date_str

# --- Engine Implementation ---

def extract_ecobank_via_row_text_strategy(pdf_path, metadata: Dict) -> List[Dict]:
    """
    Extract Ecobank transactions by grouping words into lines (y-pos), 
    stitching by Date, and parsing amounts from the tail of the text.
    Attributes:
      - Uses layout-based word grouping.
      - Handles split decimals.
      - Ignores table column boundaries (drifts).
    """
    print("DEBUG: Using Ecobank Row-Text Strategy (User's Fix)")
    
    all_words = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # extract_words gives us {"text": "...", "x0": ..., "top": ...}
            words = page.extract_words(keep_blank_chars=True)
            all_words.extend(words)

    if not all_words:
        print("DEBUG: No text found in PDF.")
        return []

    # 1. Group words into lines based on 'top' (y-position)
    # We'll use a tolerance of ~3-5 pixels.
    lines = []
    current_line = []
    current_y = -1
    tolerance = 4 

    # Sort words by top (y) first
    all_words.sort(key=lambda w: w['top'])

    for w in all_words:
        y = w['top']
        if current_y == -1:
            current_y = y
            current_line.append(w)
        elif abs(y - current_y) <= tolerance:
            current_line.append(w)
        else:
            # Finish/Store current line
            lines.append(current_line)
            current_line = [w]
            current_y = y
    
    if current_line:
        lines.append(current_line)

    # Convert word-lines to text-lines (strings)
    # Sort words in line by x0
    text_lines = []
    for line_words in lines:
        line_words.sort(key=lambda w: w['x0'])
        # Join with minimal logic (smart spacing?)
        # For now, simple join with space. pdfplumber usually handles spaces in 'text' but extract_words might split.
        # Check spacing between words?
        row_str = ""
        last_x1 = -1
        for w in line_words:
            if last_x1 != -1 and (w['x0'] - last_x1) > 2: # arbitrary space width
                 row_str += " "
            row_str += w['text']
            last_x1 = w['x1']
        text_lines.append(row_str)

    # 2. Stitch continuation lines into Transactions
    # Look for Date pattern at start of line: DD-Mon-YYYY
    # Remove anchor '^' to allow leading noise (page nums etc)
    date_pattern = re.compile(r'(\d{2}-[A-Za-z]{3}-\d{4})')
    
    transactions = []
    current_txn = None

    print(f"DEBUG: Processing {len(text_lines)} visual lines...")

    for line in text_lines:
        line = line.strip()
        if not line: continue
        
        # Filtering headers/noise
        upper_line = line.upper()
        if any(x in upper_line for x in ["BALANCE BROUGHT FORWARD", "OPENING BALANCE", "CLOSING BALANCE", "TOTAL DEBIT", "TOTAL CREDIT", "ACCOUNT SUMMARY"]):
            continue
        
        # New Transaction Detection
        date_match = date_pattern.match(line)
        if date_match:
            # Flush previous
            if current_txn: transactions.append(current_txn)
            
            txn_date = date_match.group(1)
            # Remove date from start to keep description/amounts clean(er)? 
            # Actually, amounts are at end. Description is middle.
            # Let's keep full line for context, or just remaining.
            # User's logic parses "row_text".
            
            current_txn = {
                'Date': txn_date,
                'FullText': line
            }
        else:
            # Continuation line
            if current_txn:
                current_txn['FullText'] += " " + line
            # else: skip (header junk before first txn)

    if current_txn: transactions.append(current_txn)

    # 3. Parse Data from Transactions
    final_txns = []

    for t in transactions:
        full_text = t['FullText']
        d, c, b = parse_amounts_from_row_text(full_text)
        
        if d is None:
            # Fallback or review required.
            # Maybe it uses 0.00 explicit?
            # If we fail to parse 3 numbers, assume ... what?
            # Maybe it's a line with just description? (Shouldn't happen with valid txn structure)
            # Let's log and default to 0.
            print(f"DEBUG: Failed to parse amounts for line: {full_text[:30]}...")
            d, c, b = 0.0, 0.0, 0.0

        # Description cleaning: Remove the money tokens?
        # The user didn't specify description cleaning, but we want nice output.
        # We can strip the money tokens from the end.
        desc = full_text
        # Naive approach: matching last 3 tokens and replacing them is risky if they appear in desc.
        # Better: use the specific strings found by parse_amounts_from_row_text if possible, 
        # but the helper only returns floats.
        # Let's assume description is "everything before the money".
        # We don't have the exact span.
        # For now, leave description raw or try to split?
        # Let's just strip the date.
        
        # Clean Date from Desc
        desc = desc.replace(t['Date'], "", 1).strip()
        
        final_txns.append({
            "date": parse_date(t['Date']),
            "value_date": "",
            "reference": "",
            "originating_branch": "",
            "remarks": desc,
            "description": desc,
            "debit": d,
            "credit": c,
            "balance": b,
            "category": "Unallocated",
            "is_reversal": False,
            "_page": 0,
            "_row": 0
        })

    print(f"DEBUG: Extracted {len(final_txns)} transactions via Row-Text Strategy.")
    return final_txns
