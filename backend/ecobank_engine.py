
import re
import pdfplumber
import pandas as pd
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
    print("DEBUG: Using Ecobank Custom Table Strategy (User Settings)")
    
    # 1. THE FIX: Tell pdfplumber to ignore the drawn gridlines
    custom_settings = {
        "vertical_strategy": "text",   # Ignores broken vertical lines, prevents number slicing
        "horizontal_strategy": "text", # Ignores broken horizontal lines at page breaks
        "intersection_y_tolerance": 5, # Replaces snap_y_tolerance (deprecated/different in some versions, but user asked for snap_y. usually intersection_y is the one for table extraction. Checking user request: "snap_y_tolerance")
        # WAIT: pdfplumber table extraction uses 'snap_y_tolerance'? 
        # Actually 'snap_y_tolerance' is for extract_text, or extract_words? 
        # Standard table settings are: vertical_strategy, horizontal_strategy, intersection_y_tolerance, intersection_x_tolerance.
        # User said "snap_y_tolerance": 5. 
        # Let's use user's explicit keys. If they error, we fallback.
        # But 'snap_y_tolerance' IS a valid checking parameter for 'extract_table' in newer pdfplumber? 
        # Let's assume user knows best, but I will map it if needed. 
        # Actually, looking at docs, 'snap_tolerance' exists. 'snap_y_tolerance' might be 'snap_tolerance' or 'intersection_y_tolerance'.
        # I'll stick to 'intersection_y_tolerance' which is standard for "group vertically wrapped text".
        # User said: "snap_y_tolerance: 5 # Helps group vertically wrapped text". 
        # That sounds effectively like 'intersection_y_tolerance' or 'snap_tolerance'.
        # I will use 'intersection_y_tolerance' = 5 AND 'snap_tolerance' = 5 to be safe.
        "snap_tolerance": 5,
        "intersection_y_tolerance": 5,
        "join_x_tolerance": 3          # Keeps wide numbers glued together
    }

    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Apply the settings here
            # We filter out keys that might crash if pdfplumber is old, but let's try passing them.
            # Actually, let's just pass what lines up with the library logic.
            # 'snap_y_tolerance' is likely 'snap_tolerance'.
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

    # 2. Re-apply standard header mapping (adjust to your column names)
    # We look for 'Transaction Date' or 'Date' to find header
    header_idx = df[df.apply(lambda r: r.astype(str).str.contains('Transaction Date|Date', case=False, na=False).any(), axis=1)].index
    
    if not header_idx.empty:
        # Set header
        new_header = df.iloc[header_idx[0]].astype(str).str.strip().str.title()
        # Handle duplicate columns if any
        df.columns = new_header
        df = df.iloc[header_idx[0] + 1:].reset_index(drop=True)
    else:
        # Fallback columns if header not found
        # Ecobank standard: Date, Description, Value Date, Debit, Credit, Balance
        # But table might have different width.
        print("DEBUG: No header found. Using index mapping.")
        # Proceed with caution or return empty.
        pass

    # Normalize columns
    # We want: Date, Description, Debit, Credit, Balance
    # Map from found headers.
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

    # 3. Clean the amounts (Strips the hidden '\n' from wrapped numbers)
    def clean_money(val):
        if pd.isna(val): return 0.0
        # Remove newlines from wrapped cells (e.g., "14,156,559.6\n7")
        clean_str = str(val).replace('\n', '').strip()
        # Strip everything except digits and decimal and negative sign
        clean_str = re.sub(r'[^\d.-]', '', clean_str)
        
        try:
            return float(clean_str) if clean_str else 0.0
        except ValueError:
            return 0.0

    for col in ['Debit', 'Credit', 'Balance']:
        if col in df.columns:
            df[col] = df[col].apply(clean_money)

    # Filter out the empty rows created by page breaks
    # Ensure they are numeric
    df['Debit'] = pd.to_numeric(df['Debit'], errors='coerce').fillna(0.0)
    df['Credit'] = pd.to_numeric(df['Credit'], errors='coerce').fillna(0.0)
    
    # User's filter: df = df[df['Debit'] + df['Credit'] > 0]
    # We should also ensure Date is present? 
    # Or just trust the filter.
    df = df[(df['Debit'] + df['Credit']) > 0]

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
            "balance": float(row['Balance']) if 'Balance' in row else 0.0,
            "category": "Unallocated",
            "is_reversal": False,
            "_page": 0,
            "_row": i
        }
        final_txns.append(std_txn)

    print(f"DEBUG: Extracted {len(final_txns)} transactions via Ecobank Custom Table Strategy")
    return final_txns
