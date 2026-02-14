import re
import pdfplumber
import pandas as pd
from typing import List, Dict
from datetime import datetime

def parse_date(date_str):
    if pd.isna(date_str) or not str(date_str).strip():
        return ""
    try:
        return datetime.strptime(str(date_str).strip()[:11], '%d-%b-%Y').strftime('%Y-%m-%d')
    except:
        return str(date_str)

def extract_ecobank_via_custom_tables(pdf_path, metadata: Dict = None) -> List[Dict]:
    # 1. Use standard 'lines' strategy to keep Date/Desc columns from merging
    custom_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "intersection_y_tolerance": 15
    }

    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table(table_settings=custom_settings)
            if table:
                all_rows.extend(table)

    df = pd.DataFrame(all_rows)
    if df.empty:
        return []

    # 2. Header Mapping
    # Find header row
    header_idx = df[df.apply(lambda r: r.astype(str).str.contains('Transaction Date', case=False, na=False).any(), axis=1)].index
    
    if not header_idx.empty:
        # Assign header
        df.columns = df.iloc[header_idx[0]].astype(str).str.strip()
        df = df.iloc[header_idx[0] + 1:].reset_index(drop=True)

    # Normalize Columns
    col_map = {}
    for c in df.columns:
        c_upper = str(c).upper()
        if 'DATE' in c_upper and 'VAL' not in c_upper: col_map[c] = 'Date'
        elif 'DESC' in c_upper or 'PARTICULAR' in c_upper: col_map[c] = 'Description'
        elif 'VAL' in c_upper: col_map[c] = 'Value Date'
        elif 'DEBIT' in c_upper or 'WITHDRAW' in c_upper: col_map[c] = 'Debit'
        elif 'CREDIT' in c_upper or 'DEPOSIT' in c_upper: col_map[c] = 'Credit'
        elif 'BAL' in c_upper: col_map[c] = 'Balance'
    
    df = df.rename(columns=col_map)
    
    for req in ['Date', 'Description', 'Value Date', 'Debit', 'Credit', 'Balance']:
        if req not in df.columns:
            df[req] = ""

    # 3. The Mega-String Healer
    def heal_row_amounts(row):
        # Grab raw text from the rightmost columns where numbers spill
        cols = ['Value Date', 'Debit', 'Credit', 'Balance']
        # Use only cols that actually exist in the dataframe to avoid errors
        actual_cols = [c for c in cols if c in row.index]
        
        raw_texts = [str(row.get(c, '')).replace('nan', '') for c in actual_cols]
        
        # Combine into one continuous string. 
        # Removing newlines entirely glues vertically wrapped numbers back together (e.g. 13,046,880.\n13)
        combined = " ".join(raw_texts).replace('\n', '')
        
        # Remove Dates so they aren't parsed as amounts (e.g. 2025-06-01)
        # Regex for DD-Mon-YYYY
        combined = re.sub(r'\d{2}-[A-Za-z]{3}-\d{4}', '', combined)
        
        # Heal horizontally sliced digits and spaces (e.g. "8 ,000" -> "8,000")
        combined = re.sub(r'\s+,', ',', combined)
        combined = re.sub(r',\s+', ',', combined)
        
        # Extract all valid money formats (allow for 1,234.56 or 1234.56)
        # Note: Added check to ignore simple integers if they look like years/days? 
        # The user regex: \b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b
        # This matches "2025" or "1". 
        # Let's stick strictly to user's regex but maybe filter results? 
        # User's regex:
        amounts = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b', combined)
        
        d_val, c_val, b_val = 0.0, 0.0, 0.0
        
        # Filter out obvious non-amounts if necessary? 
        # Ecobank amounts usually have decimals. 
        # If we have "01" (day) it might be caught.
        # But we removed dates. 
        # User logic assigns right-to-left: Balance, Credit, Debit.
        
        clean_amounts = []
        for a in amounts:
             # Cleanup
             val_str = a.replace(',', '')
             try:
                 f = float(val_str)
                 clean_amounts.append(f)
             except: pass
        
        if len(clean_amounts) >= 3:
            b_val = clean_amounts[-1]
            c_val = clean_amounts[-2]
            d_val = clean_amounts[-3]
        elif len(clean_amounts) == 2:
            # Usually Credit and Balance? Or Debit and Balance?
            # User logic: c_val = amounts[-1], d_val = amounts[-2] ?
            # Wait, user wrote:
            # if len(amounts) == 2:
            #    c_val = amounts[-1]
            #    d_val = amounts[-2] 
            # This implies Balance is missing? Or is the last one the Credit?
            # Standard banking: Amount | Balance. 
            # If 2 numbers, likely Amount (Dr or Cr) and Balance.
            # User's code assigns them to Credit and Debit. This might be a logic bug in user request?
            # "c_val = amounts[-1]" -> Credit? 
            # "d_val = amounts[-2]" -> Debit?
            # That would mean NO Balance found.
            # Given the request, I will EXECUTE AS WRITTEN.
            b_val = 0.0 # User didn't assign balance in len=2 case
            c_val = clean_amounts[-1]
            d_val = clean_amounts[-2]
            
        elif len(clean_amounts) == 1:
            # User code didn't handle len=1
            pass
            
        return pd.Series([d_val, c_val, b_val])

    # Overwrite broken amounts with healed amounts
    # Apply to the dataframe
    # Ensure columns exist first
    for c in ['Debit', 'Credit', 'Balance']:
         if c not in df.columns: df[c] = 0.0

    healed = df.apply(heal_row_amounts, axis=1)
    df['Debit'] = healed[0]
    df['Credit'] = healed[1]
    df['Balance'] = healed[2]

    # Drop rows with no activity (User logic: Debit > 0 or Credit > 0)
    # Ensure numeric
    df['Debit'] = pd.to_numeric(df['Debit'], errors='coerce').fillna(0.0)
    df['Credit'] = pd.to_numeric(df['Credit'], errors='coerce').fillna(0.0)
    df['Balance'] = pd.to_numeric(df['Balance'], errors='coerce').fillna(0.0)
    
    df = df[(df['Debit'] > 0) | (df['Credit'] > 0)]

    # 4. Final Formatting
    final_txns = []
    for i, row in df.iterrows():
        final_txns.append({
            "date": parse_date(row.get('Date', '')),
            "value_date": "", 
            "reference": "",
            "originating_branch": "",
            "remarks": str(row.get('Description', '')).strip().replace('\n', ' '),
            "description": str(row.get('Description', '')).strip().replace('\n', ' '),
            "debit": float(row['Debit']),
            "credit": float(row['Credit']),
            "balance": float(row['Balance']),
            "category": "Unallocated",
            "is_reversal": False,
            "_page": 0,
            "_row": i
        })

    return final_txns
