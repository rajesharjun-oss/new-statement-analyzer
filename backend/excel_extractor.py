import pandas as pd
import re
from pathlib import Path
from typing import List, Dict, Tuple, Any
from datetime import datetime

def parse_money(text: Any) -> float:
    if text is None or pd.isna(text): 
        return 0.0
    text = str(text).strip()
    if not text:
        return 0.0
    # Remove currency symbols, commas, and spaces
    cleaned = re.sub(r'[^\d\.-]', '', text)
    try:
        return float(cleaned)
    except:
        return 0.0

def parse_date_smart(text: Any) -> str:
    if text is None or pd.isna(text): 
        return ""
    if isinstance(text, (datetime, pd.Timestamp)):
        return text.strftime("%Y-%m-%d")
    
    text = str(text).strip()
    if not text:
        return ""
    try:
        # Generic pandas date parser
        return pd.to_datetime(text, dayfirst=True).strftime("%Y-%m-%d")
    except:
        return text

def extract_excel_transactions(file_path: Path) -> Tuple[List[Dict], Dict]:
    """
    Extract transactions from Excel (.xlsx, .xls) or CSV (.csv) files.
    Identifies header rows and maps columns automatically.
    """
    file_ext = file_path.suffix.lower()
    
    try:
        if file_ext == '.csv':
            # Try different encodings for CSV
            encodings = ['utf-8', 'latin1', 'cp1252']
            df = None
            for enc in encodings:
                try:
                    df = pd.read_csv(file_path, encoding=enc)
                    break
                except:
                    continue
            if df is None:
                raise ValueError(f"Could not read CSV {file_path}")
        else:
            df = pd.read_excel(file_path)
    except Exception as e:
        print(f"ERROR: Failed to read file {file_path}: {e}")
        return [], {"error": str(e)}

    # Check for empty dataframe
    if df.empty:
        return [], {"error": "File is empty"}

    # 1. Identify header row and mapping
    # We scan the first 20 rows (columns headers usually appear early)
    mapping = {"date": None, "desc": None, "debit": None, "credit": None, "balance": None, "vdate": None}
    header_row_idx = -1
    
    # Check if current columns are headers
    def check_headers(cols):
        m = {"date": None, "desc": None, "debit": None, "credit": None, "balance": None, "vdate": None}
        found = 0
        for i, col in enumerate(cols):
            val = str(col).upper()
            if "DATE" in val and "VALUE" not in val: m["date"] = i; found += 1
            elif "VALUE" in val and "DATE" in val: m["vdate"] = i
            elif any(k in val for k in ["DESC", "REMARKS", "PARTICULAR", "NARRATION"]): m["desc"] = i; found += 1
            elif "DEBIT" in val or "WITHDRAWAL" in val: m["debit"] = i; found += 1
            elif "CREDIT" in val or "DEPOSIT" in val or "LODGEMENT" in val: m["credit"] = i; found += 1
            elif "BALANCE" in val: m["balance"] = i; found += 1
        return m, found

    # Try existing columns
    m, count = check_headers(df.columns)
    if count >= 3:
        mapping = m
        header_row_idx = -2 # Use -2 to indicate df columns are headers
    else:
        # Search first 20 rows
        for i in range(min(20, len(df))):
            row = df.iloc[i].values
            m, count = check_headers(row)
            if count >= 3:
                mapping = m
                header_row_idx = i
                break

    if header_row_idx == -1:
        # Final fallback: guess based on index positions if we have enough columns
        if len(df.columns) >= 5:
             mapping = {"date": 0, "desc": 1, "debit": 3, "credit": 4, "balance": 5}
             header_row_idx = 0
        else:
             return [], {"error": "Could not identify table headers in file"}

    # 2. Extract data
    start_idx = 0 if header_row_idx == -2 else header_row_idx + 1
    processed_txns = []
    
    # If we found headers in a row, we might need to reset columns
    if header_row_idx >= 0:
        new_cols = df.iloc[header_row_idx].values
        df.columns = [str(c) for c in new_cols]
        # Re-verify mapping with new column names
        m, _ = check_headers(df.columns)
        mapping = m

    for i in range(start_idx, len(df)):
        row = df.iloc[i]
        
        raw_date = row[mapping["date"]] if mapping["date"] is not None else ""
        raw_desc = row[mapping["desc"]] if mapping["desc"] is not None else ""
        raw_vdate = row[mapping["vdate"]] if mapping["vdate"] is not None else ""
        raw_debit = row[mapping["debit"]] if mapping["debit"] is not None else 0
        raw_credit = row[mapping["credit"]] if mapping["credit"] is not None else 0
        raw_bal = row[mapping["balance"]] if mapping["balance"] is not None else 0

        # Basic validity check: must have a date-like or a number-like value
        date_s = parse_date_smart(raw_date)
        if not date_s and not raw_desc:
            continue
            
        deb = parse_money(raw_debit)
        cred = parse_money(raw_credit)
        bal = parse_money(raw_bal)
        
        # Skip rows where movements are zero unless it's a balance row?
        if deb == 0.0 and cred == 0.0:
            continue

        processed_txns.append({
            "date": date_s,
            "value_date": parse_date_smart(raw_vdate),
            "reference": "",
            "originating_branch": "",
            "description": str(raw_desc).strip(),
            "remarks": str(raw_desc).strip(),
            "debit": deb,
            "credit": cred,
            "balance": bal,
            "category": "Unallocated",
            "is_reversal": False,
            "_row": i + 1
        })

    metadata = {
        "account_name": None,
        "bank": "excel",
        "statement_period": None,
        "extracted_total_debit": sum(t["debit"] for t in processed_txns),
        "extracted_total_credit": sum(t["credit"] for t in processed_txns),
    }

    return processed_txns, metadata
