import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

print(f"DEBUG: GEMINI_API_KEY present: {bool(os.getenv('GEMINI_API_KEY'))}")

sys.path.append(str(Path(__file__).parent))

from access_engine import extract_access_via_coordinates
import pdfplumber

pdf_path = Path("temp_uploads/Access2.0.pdf")
if not pdf_path.exists():
    pdf_path = Path("backend/temp_uploads/Access2.0.pdf")

print(f"Diagnosing: {pdf_path}")
metadata = {"bank": "access"}

import access_engine
print(f"DEBUG: Using access_engine from {access_engine.__file__}")

try:
    with pdfplumber.open(pdf_path) as pdf:
        txns, final_meta = extract_access_via_coordinates(pdf_path, metadata, pdf=pdf)
        
    print(f"\nExtracted {len(txns)} transactions")
    
    if txns:
        print("\nFirst 5 transactions:")
        for t in txns[:5]:
            print(f"Date: {t['date']} | Desc: {t['description'][:50]} | D={t['debit']} C={t['credit']} B={t['balance']}")
            
        print("\nLast 5 transactions:")
        for t in txns[-5:]:
            print(f"Date: {t['date']} | Desc: {t['description'][:50]} | D={t['debit']} C={t['credit']} B={t['balance']}")
            
        # Check for discrepancies (e.g. balance doesn't match txns)
        # (This is manual for now)
        
except Exception as e:
    print(f"Error during diagnosis: {e}")
    import traceback
    traceback.print_exc()
