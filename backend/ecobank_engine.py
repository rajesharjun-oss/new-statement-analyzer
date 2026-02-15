import re
import pdfplumber
import pandas as pd
from typing import List, Dict, Any
from datetime import datetime

def extract_ecobank_final(pdf_path, metadata: Dict = None) -> List[Dict]:
    all_rows = []
    
    # 1. Use strict default table extraction. This forces wrapped numbers 
    # to stay inside their column cells based on drawn gridlines.
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table() 
            if table:
                all_rows.extend(table)

    df = pd.DataFrame(all_rows)
    if df.empty: return []

    # 2. Map Headers
    # Find header row by looking for 'Transaction Date'
    # We convert to string and check case-insensitive
    header_idx = df[df.apply(lambda r: r.astype(str).str.contains('Transaction Date', case=False, na=False).any(), axis=1)].index
    
    if not header_idx.empty:
        # Set header
        df.columns = df.iloc[header_idx[0]].astype(str).str.strip()
        # Slice data after header
        df = df.iloc[header_idx[0] + 1:].reset_index(drop=True)

    # Normalize column names for mapping
    col_map = {}
    for c in df.columns:
        c_upper = str(c).upper()
        if 'DATE' in c_upper and 'VAL' not in c_upper: col_map[c] = 'Date'
        elif 'DESC' in c_upper or 'PARTICULAR' in c_upper: col_map[c] = 'Description'
        elif 'DEBIT' in c_upper or 'WITHDRAW' in c_upper: col_map[c] = 'Debit'
        elif 'CREDIT' in c_upper or 'DEPOSIT' in c_upper: col_map[c] = 'Credit'
        elif 'BAL' in c_upper: col_map[c] = 'Balance'
    
    df = df.rename(columns=col_map)

    # 3. Clean wrapped numbers (e.g., "13,046,880.\n13" -> 13046880.13)
    def clean_amount(val):
        if pd.isna(val) or str(val).strip() == '': return 0.0
        
        # Remove newlines, spaces, and commas
        clean_str = str(val).replace('\n', '').replace(' ', '').replace(',', '')
        # Keep only digits and dots (and minus sign if any, though usually debits are positive in column)
        clean_str = re.sub(r'[^\d.-]', '', clean_str)
        
        try:
            return float(clean_str) if clean_str else 0.0
        except ValueError:
            return 0.0

    for col in ['Debit', 'Credit', 'Balance']:
        if col in df.columns:
            df[col] = df[col].apply(clean_amount)

    # Drop rows without financial movement (and ensure columns exist)
    if 'Debit' in df.columns and 'Credit' in df.columns:
        df = df[(df['Debit'] > 0) | (df['Credit'] > 0)]
    
    # 4. Final Formatting
    final_txns = []
    for i, row in df.iterrows():
        # Handle dates that might have wrapped newlines
        date_val = str(row.get('Date', '')).split('\n')[0].strip()
        # Parse Date
        dt = date_val
        try:
            # Try parsing DD-Mon-YYYY
            if len(date_val) >= 11:
                dt_obj = datetime.strptime(date_val[:11], '%d-%b-%Y')
                dt = dt_obj.strftime('%Y-%m-%d')
        except:
            pass # Keep original string if parse fails

        final_txns.append({
            "date": dt,
            "value_date": "", 
            "reference": "",
            "originating_branch": "",
            "remarks": str(row.get('Description', '')).strip().replace('\n', ' '),
            "description": str(row.get('Description', '')).strip().replace('\n', ' '),
            "debit": float(row.get('Debit', 0)) if 'Debit' in row else 0.0,
            "credit": float(row.get('Credit', 0)) if 'Credit' in row else 0.0,
            "balance": float(row.get('Balance', 0)) if 'Balance' in row else 0.0,
            "category": "Unallocated",
            "is_reversal": False,
            "_page": 0, # simplified
            "_row": i
        })

    return final_txns
