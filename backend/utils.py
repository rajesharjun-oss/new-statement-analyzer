"""
Shared utilities for bank statement extraction.
"""
import re
import pandas as pd
from typing import Optional

# Flexible date patterns
DATE_DMY_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$")       # 01-Jan-2023 OR 1-JAN-2026
DATE_MDY_SL_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")      # 10/1/2025 (Access)
DATE_DMY_YY_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$")    # 15-Jan-21 (Fidelity)
ECO_DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}$")      # 05-Jun-2025 (Ecobank)

def parse_date_smart(date_str: str) -> Optional[str]:
    """
    Parse various date formats robustly.
    Normalization: DD-MMM-YYYY (e.g., 15-Jan-2023)
    """
    # Remove soft hyphens \xad often found in GTCO PDFs
    s = (date_str or "").replace("\xad", "").strip()
    if not s or len(s) < 4: 
        return None
    
    # Standard: 01-Jan-2023
    if DATE_DMY_RE.match(s):
        return s
        
    try:
        # Use pandas for robust parsing. dayfirst=True is critical for Nigerian banks.
        dt = pd.to_datetime(s, dayfirst=True, errors='coerce')
        if pd.isna(dt):
            # Check for DD-MMM-YY (Fidelity 15-Jan-21)
            if DATE_DMY_YY_RE.match(s):
                parts = s.split('-')
                return f"{parts[0]}-{parts[1]}-20{parts[2]}"
            return None
        return dt.strftime("%d-%b-%Y")
    except:
        return None
