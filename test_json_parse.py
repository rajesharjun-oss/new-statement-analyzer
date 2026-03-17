import json
import math

raw_json_text = """[
  {
    "date": "17-Oct-2025",
    "description": "SMS/SMS CHARGES SEP 27TH 2025 - OCT 3RD 2025: 01102901534600009896184: TNF-AKINDUKO",
    "debit": 6.00,
    "credit": 0.00,
    "balance": 912795.19
  }
]"""

try:
    data_arr = json.loads(raw_json_text)
    standard_txns = []
    
    def safe_float(val):
        if val is None: return 0.0
        try:
            v = float(val)
            if math.isnan(v): return 0.0
            return v
        except (ValueError, TypeError):
            return 0.0
            
    for row in data_arr:
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
            
    print(f"Success! {len(standard_txns)} extracted")
except Exception as pe:
    print(f"DEBUG: JSON Parse failed: {pe}")
