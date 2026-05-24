from dotenv import load_dotenv
load_dotenv()
from pdf_extractor import extract_transactions
from pathlib import Path
import os

banks = {
    'fcmb': 'temp_uploads/FCMB test.pdf',
    'sterling': 'temp_uploads/STERLING test.pdf',
    'fbn': 'temp_uploads/FBN 2024.pdf'
}

for b, p in banks.items():
    print(f"--- {b.upper()} ({p}) ---")
    if not os.path.exists(p):
        print("Skipping: File not found")
        continue
    try:
        txns, meta = extract_transactions(p, bank_identifier=b)
        print(f"Extracted {len(txns)} txns.")
        print(f"Debit: {sum(t.get('debit', 0) for t in txns):,.2f}")
        print(f"Credit: {sum(t.get('credit', 0) for t in txns):,.2f}")
    except Exception as e:
        print(f"Error: {e}")
