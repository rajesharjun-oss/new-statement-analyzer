import re
import pdfplumber
import pandas as pd
from typing import List, Dict
from datetime import datetime

def parse_date(date_str):
    if pd.isna(date_str) or not str(date_str).strip():
        return ""
    try:
        # Grabs just the DD-Mon-YYYY part in case of trailing characters
        return datetime.strptime(str(date_str).strip()[:11], '%d-%b-%Y').strftime('%Y-%m-%d')
    except:
        return str(date_str)

def extract_ecobank_via_custom_tables(pdf_path, metadata: Dict = None) -> List[Dict]:
    # 1. Settings to ignore drawn gridlines and prevent number slicing
    custom_settings = {
        "vertical_strategy": "text",   
        "horizontal_strategy": "text", 
        "intersection_y_tolerance": 5, 
        "join_x_tolerance": 3          
    }

    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # FIX: Must explicitly pass as table_settings
            table = page.extract_table(table_settings=custom_settings)
            if table:
                all_rows.extend(table)

    df = pd.DataFrame(all_rows)
    if df.empty:
        return []

    # 2. Header Mapping
    # Find row with 'Transaction Date'
    header_idx = df[df.apply(lambda r: r.astype(str).str.contains('Transaction Date', case=False, na=False).any(), axis=1)].index
    
    if not header_idx.empty:
        df.columns = df.iloc[header_idx[0]].astype(str).str.strip()
        df = df.iloc[header_idx[0] + 1:].reset_index(drop=True)

    col_map = {}
    for c in df.columns:
        c_upper = str(c).upper()
        if 'DATE' in c_upper and 'VAL' not in c_upper: col_map[c] = 'Date'
        elif 'DESC' in c_upper or 'PARTICULAR' in c_upper: col_map[c] = 'Description'
        elif 'DEBIT' in c_upper or 'WITHDRAW' in c_upper: col_map[c] = 'Debit'
        elif 'CREDIT' in c_upper or 'DEPOSIT' in c_upper: col_map[c] = 'Credit'
        elif 'BAL' in c_upper: col_map[c] = 'Balance'
    
    df = df.rename(columns=col_map)
    
    for req in ['Date', 'Description', 'Debit', 'Credit', 'Balance']:
        if req not in df.columns:
            df[req] = ""

    # 3. Amount Cleaning
    def clean_money(val):
        if pd.isna(val) or str(val).strip() == '': 
            return 0.0
        
        # FIX: Handle horizontally merged cells (e.g. "8000000.00 0.00")
        first_val = str(val).replace('\n', '').strip().split()[0]
        
        # Strip invalid chars
        clean_str = re.sub(r'[^\d.-]', '', first_val)
        try:
            return float(clean_str) if clean_str else 0.0
        except ValueError:
            return 0.0

    for col in ['Debit', 'Credit', 'Balance']:
        df[col] = df[col].apply(clean_money)

    # Filter out empty rows from page breaks
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
            "balance": float(row['Balance']) if 'Balance' in df.columns else 0.0,
            "category": "Unallocated",
            "is_reversal": False,
            "_page": 0,
            "_row": i
        })

    return final_txns
