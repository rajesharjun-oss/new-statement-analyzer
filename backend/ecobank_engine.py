import re
import pdfplumber
import pandas as pd
from typing import List, Dict, Any
from datetime import datetime

def extract_ecobank_final(pdf_path, metadata: Dict = None) -> List[Dict]:
    all_rows = []
    
    # 1. Use strict text-based table extraction with tighter tolerances.
    table_settings = {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "snap_tolerance": 3,
        "snap_x_tolerance": 3,
        "snap_y_tolerance": 3,
        "join_tolerance": 3,
        "join_x_tolerance": 3,
        "join_y_tolerance": 3,
        "intersection_x_tolerance": 5,
        "intersection_y_tolerance": 5,
        "min_words_vertical": 1,
        "min_words_horizontal": 1,
    }

    def crop_table_area(page):
        w, h = page.width, page.height
        # Crop header (top 80) and footer (bottom 60)
        # Ensure we don't crop if page is too small
        if h < 150: return page
        return page.crop((0, 80, w, h - 60))

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                p = crop_table_area(page)
                tables = p.extract_tables(table_settings)
                for t in (tables or []):
                    all_rows.extend(t)
            except Exception as e:
                print(f"DEBUG: Error cropping/extracting page: {e}")
                # Fallback to full page if crop fails
                tables = page.extract_tables(table_settings)
                for t in (tables or []):
                    all_rows.extend(t)

    df = pd.DataFrame(all_rows)
    if df.empty: return []

    # 2. Map Headers
    # Find header row by looking for 'Transaction Date'
    header_idx = df[df.apply(lambda r: r.astype(str).str.contains('Transaction Date', case=False, na=False).any(), axis=1)].index
    
    if not header_idx.empty:
        df.columns = df.iloc[header_idx[0]].astype(str).str.strip()
        df = df.iloc[header_idx[0] + 1:].reset_index(drop=True)

    # Normalize column names
    col_map = {}
    for c in df.columns:
        c_upper = str(c).upper()
        if 'DATE' in c_upper and 'VAL' not in c_upper: col_map[c] = 'Date'
        elif 'DESC' in c_upper or 'PARTICULAR' in c_upper: col_map[c] = 'Description'
        elif 'DEBIT' in c_upper or 'WITHDRAW' in c_upper: col_map[c] = 'Debit'
        elif 'CREDIT' in c_upper or 'DEPOSIT' in c_upper: col_map[c] = 'Credit'
        elif 'BAL' in c_upper: col_map[c] = 'Balance'
    
    df = df.rename(columns=col_map)

    # 3. Clean wrapped numbers
    def clean_amount(val):
        if pd.isna(val) or str(val).strip() == '': return 0.0
        clean_str = str(val).replace('\n', '').replace(' ', '').replace(',', '')
        clean_str = re.sub(r'[^\d.-]', '', clean_str)
        try:
            return float(clean_str) if clean_str else 0.0
        except ValueError:
            return 0.0

    for col in ['Debit', 'Credit', 'Balance']:
        if col in df.columns:
            df[col] = df[col].apply(clean_amount)

    # Drop rows without financial movement
    if 'Debit' in df.columns and 'Credit' in df.columns:
        df = df[(df['Debit'] > 0) | (df['Credit'] > 0)]
    
    # 4. Final Formatting
    final_txns = []
    for i, row in df.iterrows():
        date_val = str(row.get('Date', '')).split('\n')[0].strip()
        dt = date_val
        try:
            if len(date_val) >= 11:
                dt_obj = datetime.strptime(date_val[:11], '%d-%b-%Y')
                dt = dt_obj.strftime('%Y-%m-%d')
        except:
            pass

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
            "_page": 0,
            "_row": i
        })

    return final_txns
