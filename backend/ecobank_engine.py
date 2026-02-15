import re
import pdfplumber
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime

# --- Regex & Logic ---

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
            # Filter Years (strict range for statement dates)
            if 1990 <= val <= 2030 and ',' not in t: 
                 continue
            # Filter huge integers that might have picked up a decimal (RefNos)
            # RefNos are usually > 100,000,000 and have NO commas.
            # Real large amounts usually have commas.
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

def extract_ecobank_final(pdf_path, metadata: Dict = None) -> List[Dict]:
    """
    Robust Row-Text Strategy implementation.
    Ignores gridlines, stitches text by Y-position, and parses amounts from the tail.
    """
    print("DEBUG: Using Ecobank Row-Text Strategy (Restored & Refined)")
    
    all_words = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=True)
            all_words.extend(words)

    if not all_words:
        return []

    # 1. Group words into lines based on 'top' (y-position)
    lines = []
    current_line = []
    current_y = -1
    tolerance = 4 

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
    text_lines_objs = [] # store the text and the extracted amounts?
    
    for line_words in lines:
        line_words.sort(key=lambda w: w['x0'])
        row_str = ""
        last_x1 = -1
        for w in line_words:
             # Intelligent spacing
             if last_x1 != -1 and (w['x0'] - last_x1) > 2:
                 row_str += " "
             row_str += w['text']
             last_x1 = w['x1']
        
        text_lines_objs.append(row_str)

    # 2. Iterate and Parse
    final_txns = []
    current_date = None
    
    # Date Regex: DD-Mon-YYYY
    # We remove anchors to match dates even if noise precedes them
    date_regex = re.compile(r'(\d{2}-[A-Za-z]{3}-\d{4})')
    
    for row_text in text_lines_objs:
        # Check for date
        date_match = date_regex.search(row_text)
        if date_match:
            # New Transaction Start?
            # Try parsing amounts first
            debit, credit, halance = parse_amounts_from_row_text(row_text)
            
            if debit is not None:
                # Valid txn line
                raw_date = date_match.group(1)
                try:
                    dt = datetime.strptime(raw_date, '%d-%b-%Y').strftime('%Y-%m-%d')
                except:
                    dt = raw_date
                
                # Description: Everything before the amounts?
                # This is heuristic. We can just take the whole row text for now.
                # Or try to strip the amounts from the end.
                
                final_txns.append({
                    "date": dt,
                    "value_date": "",
                    "reference": "",
                    "originating_branch": "",
                    "description": row_text, # Full text is safer for now
                    "remarks": row_text,
                    "debit": debit,
                    "credit": credit,
                    "balance": halance,
                    "category": "Unallocated",
                    "is_reversal": False
                })
        else:
            # Continuation line? 
            # If we had a previous txn, append text to description?
            # For this specific task (totals mismatch), strict Amount capture is the priority.
            # We can skip complex looking-back stitching for now unless needed.
            # Ecobank often has 1-line txns or amounts on the date line.
            pass

    return final_txns
