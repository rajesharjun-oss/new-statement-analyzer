import re
import pdfplumber
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime

# --- User's Provided Logic & Regex ---
# Enhanced money token regex to capture "1,234.56", "1234", "12.34"
# Added handling for possible leading/trailing checks
money_token_re = re.compile(r'(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d)')

def normalize_split_decimals(tokens: List[str]) -> List[str]:
    """
    Joins patterns like ["13,046,880.", "13"] -> ["13,046,880.13"]
    Fixes the 'floating decimal tail' issue common in PDF text extraction.
    """
    out = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        # Check if current token ends with '.' and next token is 1-2 digits
        if t.endswith('.') and i + 1 < len(tokens) and re.fullmatch(r'\d{1,2}', tokens[i+1]):
            out.append(t + tokens[i+1])
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
    
    toks = money_token_re.findall(clean_text)
    toks = normalize_split_decimals(toks)
    
    # We need at least 3 numbers for D/C/B. 
    # Sometimes there are more (if description contains numbers).
    # We take the *last* 3.
    if len(toks) < 3:
        # Check for case where 0.00 might be represented as '-' or blank?
        # If we have 1 or 2 tokens, it's ambiguous.
        return None, None, None

    debit_s, credit_s, bal_s = toks[-3], toks[-2], toks[-1]

    def f(x):
        # Remove commas, convert to float
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
    date_pattern = re.compile(r'^(\d{2}-[A-Za-z]{3}-\d{4})')
    
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
