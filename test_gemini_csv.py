import pandas as pd
import io
import re

def safe_float(val):
    if pd.isnull(val): return 0.0
    try:
        s = str(val).replace(',', '').strip()
        s = re.sub(r'[^\d\.\-]', '', s)
        if not s or s == '-' or s == '.': return 0.0
        return float(s)
    except ValueError:
        return 0.0

raw_csv = """DATE,DESCRIPTION,DEBIT,CREDIT,BALANCE
01-Oct-2025,Opening Balance,0.00,0.00,912801.19
17-Oct-2025,SMS/SMS CHARGES SEP 27TH 2025 - OCT 3RD 2025: 01102801534600009896184: TNF-AKINDUKO,6.00,0.00,912795.19
17-Oct-2025,OLUBUNMI/App To United Bank,0.00,1000000.00,1912795.19"""

try:
    df = pd.read_csv(io.StringIO(raw_csv), on_bad_lines='skip')
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    standard_txns = []
    for _, row in df.iterrows():
        try:
            standard_txns.append({
                'date': str(row.get('date', '')).strip(),
                'description': str(row.get('description', '')).strip(),
                'debit': safe_float(row.get('debit', 0)),
                'credit': safe_float(row.get('credit', 0)),
                'balance': safe_float(row.get('balance', 0)),
                'reference': '',
                'remarks': str(row.get('description', '')).strip(),
                'category': 'Uncategorized'
            })
        except Exception as row_e:
            print(f"DEBUG: Skipping malformed AI row: {row_e}")
            continue
    print(f"Extracted {len(standard_txns)} txns")
    for t in standard_txns:
        print(t)
        
except Exception as pe:
    print(f"DEBUG: CSV Parse failed: {pe}")
