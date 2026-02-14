
import re
import pdfplumber
import pandas as pd
import numpy as np
from typing import List, Dict
from datetime import datetime

def parse_date(date_str):
    try:
        return datetime.strptime(str(date_str).strip(), '%d-%b-%Y').strftime('%Y-%m-%d')
    except:
        try:
            return pd.to_datetime(date_str).strftime('%Y-%m-%d')
        except:
            return date_str

def extract_ecobank_via_custom_tables(pdf_path, metadata: Dict) -> List[Dict]:
    """
    Extract Ecobank transactions using USER'S CUSTOM TABLE SETTINGS.
    """
    print("DEBUG: Using Ecobank Custom Table Strategy (User Settings + Numpy Fix)")
    
    # 1. THE FIX: Tell pdfplumber to ignore the drawn gridlines
    custom_settings = {
        "vertical_strategy": "text",   # Ignores broken vertical lines, prevents number slicing
        "horizontal_strategy": "text", # Ignores broken horizontal lines at page breaks
        "intersection_y_tolerance": 5, # Replaces snap_y_tolerance 
        "snap_tolerance": 5,
        "join_x_tolerance": 3          # Keeps wide numbers glued together
    }

    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                table = page.extract_table(custom_settings)
            except:
                # Fallback if keys are wrong
                safe_settings = {
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "intersection_y_tolerance": 5,
                    "snap_tolerance": 5
                }
                table = page.extract_table(safe_settings)
            
            if table:
                all_rows.extend(table)

    df = pd.DataFrame(all_rows)
    print(f"DEBUG: Extracted {len(df)} raw rows using custom settings.")
    
    if df.empty:
        return []

    # 2. Re-apply standard header mapping
    # 2. Re-apply standard header mapping (STRICTER SEARCH)
    def is_header_row(row):
        text = " | ".join([str(x).strip().lower() for x in row.tolist() if str(x).strip() != ""])
        needed = [
            ("date" in text or "transaction date" in text),
            ("desc" in text or "particular" in text or "narration" in text),
            ("debit" in text or "withdraw" in text),
            ("credit" in text or "deposit" in text),
            ("bal" in text),
        ]
        # Require at least 3-4 of these to avoid false positives
        return sum(needed) >= 3

    header_candidates = df[df.apply(is_header_row, axis=1)].index
    
    if not header_candidates.empty:
        # Set header
        hdr_i = header_candidates[0]
        # User requested: Do NOT .title() headers to avoid mangling
        new_header = df.iloc[hdr_i].astype(str).str.strip()
        df.columns = new_header
        df = df.iloc[hdr_i + 1:].reset_index(drop=True)
    else:
        print("DEBUG: No header found. Using index mapping.")

    # Normalize columns
    col_map = {}
    for c in df.columns:
        c_upper = str(c).upper()
        if 'DATE' in c_upper and 'VAL' not in c_upper: col_map[c] = 'Date'
        if 'DESC' in c_upper or 'PARTICULAR' in c_upper: col_map[c] = 'Description'
        if 'DEBIT' in c_upper or 'WITHDRAW' in c_upper: col_map[c] = 'Debit'
        if 'CREDIT' in c_upper or 'DEPOSIT' in c_upper: col_map[c] = 'Credit'
        if 'BAL' in c_upper: col_map[c] = 'Balance'
    
    df = df.rename(columns=col_map)
    
    # Ensure columns exist
    for req in ['Date', 'Description', 'Debit', 'Credit', 'Balance']:
        if req not in df.columns:
            df[req] = ""

    # 3. Clean the amounts (User's Numpy Version)
    def clean_money(val):
        if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and not val.strip()):
            return np.nan

        s = str(val).replace('\n', '').strip()

        # Handle parentheses negatives e.g. (1,234.00)
        neg = False
        if s.startswith('(') and s.endswith(')'):
            neg = True
            s = s[1:-1].strip()

        # Keep digits, decimal point, minus sign
        s = re.sub(r'[^\d.\-]', '', s)

        # If more than one dot, treat as NaN (broken tokenization)
        if s.count('.') > 1:
            return np.nan

        # If it's just "-" or empty
        if s in ("", "-", "."):
            return np.nan

        try:
            x = float(s)
            return -x if neg else x
        except:
            return np.nan

    for col in ['Debit', 'Credit', 'Balance']:
        if col in df.columns:
            df[col] = df[col].apply(clean_money)

    # --- DEBUG GUARD START (User Request) ---
    # Check for rows with description but No Parsed Amounts
    bad = df[(df['Debit'].isna()) & (df['Credit'].isna()) & (df['Description'].astype(str).str.strip() != "")]
    print(f"DEBUG: Rows with description but no parsed amounts: {len(bad)}")
    if len(bad) > 0:
        print(bad.head(10))
    # --- DEBUG GUARD END ---

    # 4. Filter empty rows (User's Logic: Keep NaNs until filter)
    df['Debit'] = pd.to_numeric(df['Debit'], errors='coerce')   # keep NaN
    df['Credit'] = pd.to_numeric(df['Credit'], errors='coerce') # keep NaN

    # Keep rows where at least one of Debit/Credit is a valid number and > 0
    df = df[(df['Debit'].fillna(0) > 0) | (df['Credit'].fillna(0) > 0)]

    # Normalize final output
    df['Debit'] = df['Debit'].fillna(0.0)
    df['Credit'] = df['Credit'].fillna(0.0)
    df['Balance'] = pd.to_numeric(df['Balance'], errors='coerce').fillna(0.0)

    # --- Final Output Formatting ---
    final_txns = []
    
    for i, row in df.iterrows():
        std_txn = {
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
        }
        final_txns.append(std_txn)

    print(f"DEBUG: Extracted {len(final_txns)} transactions via Ecobank Custom Table Strategy (Numpy Fixed)")
    return final_txns
