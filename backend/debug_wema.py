import pdfplumber
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
from wema_engine import extract_wema_via_coordinates

pdf_path = Path('temp_uploads/WEMA test.pdf')

# 1. Get raw float strings from PDF
text = ' '.join(p.extract_text() for p in pdfplumber.open(pdf_path).pages)
raw_set = set(re.findall(r'\b\d{1,3}(?:,\d{3})+\.\d{2}\b', text))

# 2. Get extracted float strings
txns, _ = extract_wema_via_coordinates(pdf_path, {})
e_debs = [f"{t['debit']:,.2f}" for t in txns if t['debit'] > 0]
e_creds = [f"{t['credit']:,.2f}" for t in txns if t['credit'] > 0]
ext_set = set(e_debs + e_creds)

# 3. Diff
missed = raw_set - ext_set

# Clean out strings that we know are just balances to keep output clean
# We can filter balances by ignoring balances if they are huge and don't match.
print("Missed strings in parser:")
for m in sorted([float(x.replace(',','')) for x in missed if float(x.replace(',','')) > 10000000.0]):
    print(f"{m:,.2f}")
