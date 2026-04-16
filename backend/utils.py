"""
Shared utilities for bank statement extraction.
"""
import re
import pandas as pd
from datetime import datetime
from typing import Optional

# Flexible date patterns
DATE_DMY_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$")       # 01-Jan-2023 OR 1-JAN-2026
DATE_MDY_SL_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")      # 10/1/2025 (Access)
DATE_DMY_YY_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$")    # 15-Jan-21 (Fidelity)
ECO_DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}$")      # 05-Jun-2025 (Ecobank)

# Bare month name (GTBank 4-row format: tdate column contains just "Jan", "Feb", etc.)
BARE_MONTH_RE = re.compile(
    r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?$",
    re.IGNORECASE
)

# Year token: matches "2024", "2025", "2026" etc. — also matches "2026 18:27" (year + timestamp)
YEAR_TOKEN_RE = re.compile(r"^(20\d{2})(?:\s|$)")

# Truncated year: "21-Jan-1", "21-Jan-26" style (1-2 digit year that looks wrong for 20xx context)
DATE_DMY_TRUNCYEAR_RE = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{1,2})$")

# Day + Month (no year): "21 Jan", "21-Jan"
DATE_DM_RE = re.compile(r"^(\d{1,2})[\s\-]([A-Za-z]{3,9})$")


def _current_year() -> int:
    return datetime.now().year


def parse_date_smart(date_str: str, year_hint: Optional[str] = None) -> Optional[str]:
    """
    Parse various date formats robustly.
    Normalization: DD-MMM-YYYY (e.g., 15-Jan-2023)

    year_hint: optional string from an adjacent cell (e.g. value_date) that may
               contain a year token like "2026 18:27". Used to complete partial dates.
    """
    # Remove soft hyphens \xad often found in GTCO PDFs
    s = (date_str or "").replace("\xad", "").strip()
    if not s or len(s) < 4:
        return None

    # Standard: 01-Jan-2023
    if DATE_DMY_RE.match(s):
        return s

    # Extract year from hint if provided (matches "2026" or "2026 18:27" etc.)
    hint_year: Optional[int] = None
    if year_hint:
        ym = YEAR_TOKEN_RE.match(year_hint.strip())
        if ym:
            hint_year = int(ym.group(1))

    # Truncated year: "21-Jan-1" or "21-Jan-26" or "03-JAN-25" with short digit year
    m_trunc = DATE_DMY_TRUNCYEAR_RE.match(s)
    if m_trunc:
        day, mon, short_yr = m_trunc.group(1), m_trunc.group(2), m_trunc.group(3)
        yr_int = int(short_yr)
        if len(short_yr) == 2:
            # Two-digit year like "25" → always 2025, "99" → 2099
            # Nigerian bank statements are all post-2000, so 20XX is always correct
            full_year = 2000 + yr_int
        elif yr_int < 10:
            # Single-digit year (ambiguous): prefer hint year, else current year
            full_year = hint_year if hint_year else _current_year()
        else:
            full_year = 2000 + yr_int
        return f"{day.zfill(2)}-{mon.capitalize()}-{full_year}"

    # Day + Month only: "21 Jan" or "21-Jan" (no year)
    m_dm = DATE_DM_RE.match(s)
    if m_dm:
        day, mon = m_dm.group(1), m_dm.group(2)
        full_year = hint_year if hint_year else _current_year()
        candidate = f"{day.zfill(2)}-{mon[:3].capitalize()}-{full_year}"
        try:
            pd.to_datetime(candidate, dayfirst=True, errors='raise')
            return candidate
        except Exception:
            pass

    # Reject bare 4-digit year tokens (e.g. "2024", "2025") — Sterling Bank continuation rows
    # have just the year in the date column; pd.to_datetime would resolve them to Jan 1 of that year
    if re.match(r'^20\d{2}$', s.strip()):
        return None

    # Reject HH:MM and HH:MM:SS time strings — pd.to_datetime would resolve them to today's date,
    # creating phantom transactions (e.g. "21:44" → "11-Apr-2026")
    if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', s):
        return None

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
    except Exception:
        return None
