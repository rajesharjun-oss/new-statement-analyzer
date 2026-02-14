
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
    print("DEBUG: Using Ecobank Text-Based Regex Strategy (New Engine v2)")
    transactions = []
    
    # EcoBank Date Format: DD-Mon-YYYY (e.g., 31-May-2025)
    # We look for lines starting with this pattern
    date_pattern = re.compile(r'^(\d{2}-[A-Za-z]{3}-\d{4})')
    
    # Regex for money tokens
    # Capture negatives, but require .2 decimals strictly to avoid "2025" years etc.
    # Exclude "2025-06-01" from being matched as money.
    money_pattern = re.compile(r'(?<!\d-)(?<!\d)(-?[\d,]+\.\d{2})(?!\d)')

    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            # 'layout=True' mimics physical layout, preserving spaces better for some PDFs
            # 'layout=False' is standard stream. Let's try standard first, but with physical x_tolerance?
            # extract_text usually defaults to layout=False.
            text = page.extract_text()
            if text:
                all_lines.extend(text.split('\n'))
            else:
                print(f"DEBUG: Page {i} had no text.")

    current_txn = None
    
    print(f"DEBUG: Scanning {len(all_lines)} text lines...")
    
    for line in all_lines:
        line = line.strip()
        if not line: continue
        
        # Skip Headers/Footers noise
        if any(x in line for x in ["Balance Brought Forward", "Page", "Account Statement", "Opening Balance", "Closing Balance"]):
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
             matches = money_pattern.findall(line)
             
             # FILTER MATCHES: Drop matches that are arguably years like "2,025.00" if rare, but 
             # usually money regex is strict enough.
             
             if len(matches) >= 1:
                 # It has money! 
                 # Decision: Is it a NEW txn (Implicit Date) or CONTINUATION?
                 
                 # Logic: Does the PREVIOUS FullLine *already* have money?
                 # If yes -> This must be a NEW transaction (implicit date).
                 # If no -> This completes the PREVIOUS transaction (wrapped).
                 
                 prev_matches = money_pattern.findall(current_txn['FullLine'])
                 prev_has_money = len(prev_matches) > 0 # Simple check
                 
                 if prev_has_money:
                     # Previous was complete. This is new.
                     transactions.append(current_txn) # Flush old
                     current_txn = {
                        'Date': current_txn['Date'], # Inherit Date
                        'FullLine': line,
                        'Debit': 0.0,
                        'Credit': 0.0,
                        'Balance': 0.0
                     }
                 else:
                     # Previous was incomplete (just desc). This appends to it.
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
        matches = money_pattern.findall(line_text)
        
        # Default
        d, c, b = 0.0, 0.0, 0.0
        clean_desc = line_text
        
        # Clean matches (remove commas)
        vals = []
        for m in matches:
             try:
                 vals.append(float(m.replace(',', '')))
             except: pass
        
        if len(vals) >= 3:
            # Assume: Debit | Credit | Balance (last 3)
            d, c, b = vals[-3], vals[-2], vals[-1]
            # Remove from desc (using original strings)
            for m in matches[-3:]:
                clean_desc = clean_desc.replace(m, '')
            clean_desc = clean_desc.strip()
            
        elif len(vals) == 2:
            # Amount | Balance
            amt, b = vals[-2], vals[-1]
            d = amt # Tentative
            for m in matches[-2:]:
                clean_desc = clean_desc.replace(m, '')
            clean_desc = clean_desc.strip()
            
        elif len(vals) == 1:
            # Balance only
            b = vals[-1]
            clean_desc = clean_desc.replace(matches[-1], '').strip()

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
    print(f"DEBUG: Parsed {len(df)} initial rows.")

    # --- NUCLEAR OPTION: RE-APPLY BALANCE DRIVEN CALCULATION ---
    if not df.empty:
    # --- NUCLEAR OPTION: RE-APPLY BALANCE DRIVEN CALCULATION ---
    if not df.empty:
        # Ensure numeric types first
        df['Balance'] = pd.to_numeric(df['Balance'], errors='coerce').fillna(0.0)
        
        # 1. Recalculate Debits and Credits based on the row-to-row Balance change
        df['Balance_Diff'] = df['Balance'].diff()

        # Init calc cols with NaN (pd.NA) to allow fillna later
        df['Calculated_Debit'] = pd.NA
        df['Calculated_Credit'] = pd.NA
        
        # If balance drops, it's a Debit. If it rises, it's a Credit.
        # Use epsilon for float safety
        diff_epsilon = 0.005
        
        df.loc[df['Balance_Diff'] < -diff_epsilon, 'Calculated_Debit'] = df['Balance_Diff'].abs()
        df.loc[df['Balance_Diff'] > diff_epsilon, 'Calculated_Credit'] = df['Balance_Diff']

        # 2. Overwrite the broken columns (leaving the first row's NaN as 0.0 or original)
        df['Debit'] = df['Calculated_Debit'].fillna(df['Debit'])
        df['Debit'] = pd.to_numeric(df['Debit'], errors='coerce').fillna(0.0).round(2)
        
        df['Credit'] = df['Calculated_Credit'].fillna(df['Credit'])
        df['Credit'] = pd.to_numeric(df['Credit'], errors='coerce').fillna(0.0).round(2)

        # 3. Clean up the stray numbers that got thrown into your Date column
        if 'Date' in df.columns:
            df['Date'] = df['Date'].astype(str).str.replace(r'\s+\d+$', '', regex=True)

        # Drop temporary columns
        df.drop(columns=['Balance_Diff', 'Calculated_Debit', 'Calculated_Credit'], inplace=True, errors='ignore')

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

    print(f"DEBUG: Extracted {len(final_txns)} transactions via Ecobank Text Engine v2")
    return final_txns
