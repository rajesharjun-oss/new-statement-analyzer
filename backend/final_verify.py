from dotenv import load_dotenv
load_dotenv()
import os
print(f"DEBUG: GEMINI_API_KEY present: {bool(os.getenv('GEMINI_API_KEY'))}")
from pdf_extractor import extract_transactions
from pathlib import Path
import os
import pandas as pd

banks = {
    'fcmb': 'temp_uploads/FCMB test.pdf',
    'sterling': 'temp_uploads/STERLING test.pdf',
    'uba': 'temp_uploads/UBA test.pdf',
    'wema': 'temp_uploads/WEMA test.pdf',
    'zenith': 'temp_uploads/Zenith bank test.pdf',
    'access': 'temp_uploads/Access bank test.pdf',
    'fbn': 'temp_uploads/FBN 2024.pdf',
    'providus': 'temp_uploads/Adam Providus.pdf'
}

for b, p in banks.items():
    print(f"\n--- {b.upper()} ({p}) ---")
    if not os.path.exists(p):
        print("Skipping: File not found")
        continue
    try:
        txns, meta = extract_transactions(p, bank_identifier=b)
        print(f"Extracted {len(txns)} txns.")
        if txns:
            df = pd.DataFrame(txns)
            print(f"Debit: {df['debit'].sum():,.2f}")
            print(f"Credit: {df['credit'].sum():,.2f}")
            print(f"Sample: {txns[0]['date']} | {txns[0]['description'][:30]}")
    except Exception as e:
        print(f"Error: {e}")
