
import re
import pdfplumber
import pandas as pd
from typing import List, Dict
from datetime import datetime

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, '%d-%b-%Y').strftime('%Y-%m-%d')
    except:
        return date_str

def extract_ecobank_via_text_strategy(pdf_path, metadata: Dict) -> List[Dict]:
    """
    Extract Ecobank transactions using a Text-Based Regex Strategy.
    Bypasses table extraction issues (merging rows/newlines) by parsing line-by-line.
    """
    print("DEBUG: Using Ecobank Text-Based Regex Strategy (New Engine)")
    transactions = []
    
    # EcoBank Date Format: DD-Mon-YYYY (e.g., 31-May-2025)
    # We look for lines starting with this pattern
    date_pattern = re.compile(r'^(\d{2}-[A-Za-z]{3}-\d{4})')
    
    # Regex for money at end of line 
    # Matches strings that look like money columns at the end of the text
    money_pattern = re.compile(r'([\d,]+\.\d{2})')

    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend(text.split('\n'))

    current_txn = None
    
    for line in all_lines:
        line = line.strip()
        if not line: continue
        
        # Skip Headers/Footers noise
        if any(x in line for x in ["Balance Brought Forward", "Page", "Account Statement", "Opening Balance"]):
            continue

        # 1. New Transaction Detection
        date_match = date_pattern.match(line)
        if date_match:
            # Save previous
            if current_txn: transactions.append(current_txn)
            
            txn_date = date_match.group(1)
            remaining_text = line[len(txn_date):].strip()
            
            current_txn = {
                'Date': txn_date,
                'FullLine': remaining_text, 
                'Debit': 0.0,
                'Credit': 0.0,
                'Balance': 0.0
            }

        # 2. Implicit Date Transaction (Same Day)
        # Check if line *starts* with a Description but ends with clear Money columns
        # AND we have a current transaction to inherit date from.
        elif current_txn and not date_match:
             # Heuristic: verify if line has at least 2 numbers looking like money (Amount + Balance)
             # or just one number (Balance? or Amount?)
             # Ecobank rows often wrap description, then have text.
             # Strict check: Does it end with a number?
             
             matches = money_pattern.findall(line)
             if len(matches) >= 1:
                 # It has money! check if it's not a phone number (usually 11 digits, no decimal)
                 # Our regex requires .2 decimals, so it's likely money.
                 
                 # Logic: Is this a wrapped description line WITH money?
                 # Or a new implicit transaction?
                 
                 # If the previous transaction ALREADY has money parsed (conceptually), then this is a NEW implicit one.
                 # But we haven't parsed money yet.
                 
                 # Let's assume ANY line with money that isn't a date-line is a NEW implicit transaction 
                 # OR the tail end of a wrapped line that had the money.
                 
                 # Case A:
                 # 01-Jan  Desc Part 1
                 #         Desc Part 2   10,000.00   50,000.00
                 # In this case, Row 1 has NO money. Row 2 has money. They are ONE transaction.
                 
                 # Case B:
                 # 01-Jan  Desc Txn 1    10,000.00   50,000.00
                 #         Desc Txn 2     5,000.00   45,000.00  <-- Implicit Date
                 
                 # Differentation: Did the previous line have money?
                 # We can check FullLine of current_txn for money pattern.
                 prev_has_money = bool(money_pattern.search(current_txn['FullLine']))
                 
                 if prev_has_money:
                     # Previous already has money. This must be a NEW implicit transaction.
                     if current_txn: transactions.append(current_txn)
                     current_txn = {
                        'Date': current_txn['Date'], # Inherit Date
                        'FullLine': line,
                        'Debit': 0.0,
                        'Credit': 0.0,
                        'Balance': 0.0
                     }
                 else:
                     # Previous had no money. This is the tail of the previous transaction.
                     current_txn['FullLine'] += " " + line
             
             else:
                 # No money. Just wrapped description text.
                 current_txn['FullLine'] += " " + line

    # Last one
    if current_txn: transactions.append(current_txn)

    # --- Processing Phase: Parse 'FullLine' into Amounts ---
    final_txns = []
    
    def parse_money_from_line(line_text):
        # Extract all numbers resembling amounts
        # Regex: digits, commas, dot, two digits
        matches = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', line_text)
        
        # Default
        d, c, b = 0.0, 0.0, 0.0
        clean_desc = line_text
        
        if len(matches) >= 3:
            # Assume: Debit | Credit | Balance
            d_str, c_str, b_str = matches[-3], matches[-2], matches[-1]
            try:
                d = float(d_str.replace(',', ''))
                c = float(c_str.replace(',', ''))
                b = float(b_str.replace(',', ''))
            except: pass
            # Remove them from description
            clean_desc = line_text.replace(d_str, '').replace(c_str, '').replace(b_str, '').strip()
            
        elif len(matches) == 2:
            # Assume one is Amount (Dr or Cr), last is Balance
            # We don't know which is Dr/Cr yet. We'll use Balance Diff later to decide!
            # For now, put in Debit column as placeholder.
            amt_str, b_str = matches[-2], matches[-1]
            try:
                amt = float(amt_str.replace(',', ''))
                b = float(b_str.replace(',', ''))
                d = amt 
            except: pass
            
            clean_desc = line_text.replace(amt_str, '').replace(b_str, '').strip()
            
        elif len(matches) == 1:
            # Just Balance?
            b_str = matches[-1]
            try:
                b = float(b_str.replace(',', ''))
            except: pass
            clean_desc = line_text.replace(b_str, '').strip()

        return clean_desc, d, c, b

    df_data = []
    for i, t in enumerate(transactions):
        desc, d, c, b = parse_money_from_line(t['FullLine'])
        df_data.append({
            'Date': t['Date'],
            'Description': desc,
            'Debit': d,
            'Credit': c,
            'Balance': b
        })
        
    df = pd.DataFrame(df_data)
    
    # --- NUCLEAR OPTION: RE-APPLY BALANCE DRIVEN CALCULATION ---
    if not df.empty:
        df['Balance'] = pd.to_numeric(df['Balance'], errors='coerce').fillna(0.0)
        df['Balance_Diff'] = df['Balance'].diff()
        
        df['Calculated_Debit'] = 0.0
        df['Calculated_Credit'] = 0.0
        diff_epsilon = 0.005 

        # Balance Drops -> Debit
        # If diff is negative (balance went down), it's a debit.
        # But wait, diff = current - prev. 
        # If curr < prev, diff is negative. Money left account. Debit. Correct.
        mask_debit = df['Balance_Diff'] < -diff_epsilon
        df.loc[mask_debit, 'Calculated_Debit'] = df.loc[mask_debit, 'Balance_Diff'].abs()

        # Balance Rises -> Credit
        mask_credit = df['Balance_Diff'] > diff_epsilon
        df.loc[mask_credit, 'Calculated_Credit'] = df.loc[mask_credit, 'Balance_Diff']

        # Overwrite extraction
        # Row 0 exception: Keep extracted (cannot calc diff)
        df.loc[1:, 'Debit'] = df.loc[1:, 'Calculated_Debit']
        df.loc[1:, 'Credit'] = df.loc[1:, 'Calculated_Credit']

    for i, row in df.iterrows():
        std_txn = {
            "date": parse_date(row.get('Date', '')),
            "value_date": "", 
            "reference": "",
            "originating_branch": "",
            "remarks": row.get('Description', ''),
            "description": row.get('Description', ''),
            "debit": float(row['Debit'] or 0.0),
            "credit": float(row['Credit'] or 0.0),
            "balance": float(row['Balance'] or 0.0),
            "category": "Unallocated",
            "is_reversal": False,
            "_page": 0,
            "_row": i
        }
        final_txns.append(std_txn)

    print(f"DEBUG: Extracted {len(final_txns)} transactions via Ecobank Text Engine")
    return final_txns
