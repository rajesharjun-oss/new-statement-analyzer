
import re
import pdfplumber
from datetime import datetime
from typing import List, Dict, Tuple, Optional

# --- Robust Regex & Helpers (Restored from "Final Fix") ---

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
        try:
            val = float(t.replace(',', ''))
            # Filter Years
            if 1990 <= val <= 2030 and ',' not in t: 
                 continue
            # Filter huge integers that might have picked up a decimal (RefNos)
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

# --- Main Engine Function (Renamed to match Dispatcher) ---

def extract_ecobank_final(pdf_path, metadata: Dict = None) -> List[Dict]:
    """
    Robust "Row-Text" Strategy. 
    Groups words by Y-position, stitches lines by Date, and extracts amounts 
    from the tail of the text using strict regex filters.
    """
    print("DEBUG: Using Ecobank Row-Text Strategy (Restored Final Fix)")
    
    all_words = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # extract_words gives us {"text": "...", "x0": ..., "top": ...}
            words = page.extract_words(keep_blank_chars=True)
            all_words.extend(words)

    if not all_words:
        return []

    # 1. Group words into lines based on 'top' (y-position)
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
            lines.append(current_line)
            current_line = [w]
            current_y = y
    
    if current_line:
        lines.append(current_line)

    # Convert word-lines to text-lines (strings)
    text_lines = []
    for line_words in lines:
        line_words.sort(key=lambda w: w['x0'])
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
    # Remove anchor '^' to allow leading noise
    date_pattern = re.compile(r'(\d{2}-[A-Za-z]{3}-\d{4})')
    
    transactions = []
    current_txn = None

    for i, line in enumerate(text_lines):
        # Check if line *starts* with date (or close to start)
        match = date_pattern.search(line)
        
        # New Transaction Start
        if match:
            # Finish previous
            if current_txn:
                # Parse amounts from accumulated text
                full_text = " ".join(current_txn['lines'])
                d, c, b = parse_amounts_from_row_text(full_text)
                
                # Check if we successfully parsed amounts
                if d is not None:
                    current_txn['debit'] = d
                    current_txn['credit'] = c
                    current_txn['balance'] = b
                    
                    # Description is everything before the amounts?
                    # Or just use the lines?
                    # We'll just clean the amounts from the text for description?
                    # Simplification: Use full text as description for now
                    current_txn['description'] = full_text
                    current_txn['remarks'] = full_text
                    
                    transactions.append(current_txn)
                else:
                    # Failed to parse amounts? Maybe header or junk line?
                    # Or maybe amounts are on next line? 
                    # Row-text strategy assumes amounts are in the block.
                    # We'll drop if no amounts found (strict financial extraction)
                    pass

            date_str = match.group(1)
            current_txn = {
                "date": parse_date(date_str),
                "lines": [line],
                "debit": 0.0,
                "credit": 0.0,
                "balance": 0.0
            }
        else:
            # Continuation line
            if current_txn:
                current_txn['lines'].append(line)

    # Finish last txn
    if current_txn:
        full_text = " ".join(current_txn['lines'])
        d, c, b = parse_amounts_from_row_text(full_text)
        if d is not None:
            current_txn['debit'] = d
            current_txn['credit'] = c
            current_txn['balance'] = b
            current_txn['description'] = full_text
            current_txn['remarks'] = full_text
            transactions.append(current_txn)

    return transactions
