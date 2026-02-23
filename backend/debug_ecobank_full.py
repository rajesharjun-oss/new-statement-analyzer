
import sys
import os
from pathlib import Path

# Allow running from backend
sys.path.insert(0, str(Path(__file__).parent))

from pdf_extractor import extract_transactions

pdf_path = 'temp_uploads/190cb33d-d970-48a5-9016-91999032a290.pdf'
if not os.path.exists(pdf_path):
    print(f"File not found: {pdf_path}")
    sys.exit(1)

txns, meta = extract_transactions(pdf_path, 'ecobank')

print(f"Total Transactions: {len(txns)}")
print(f"Statement Total Debit: {meta.get('statement_total_debit')}")
print(f"Statement Total Credit: {meta.get('statement_total_credit')}")

extracted_credit = sum(t.get('credit', 0) for t in txns)
extracted_debit = sum(t.get('debit', 0) for t in txns)

print(f"Extracted Total Debit: {extracted_debit:.2f}")
print(f"Extracted Total Credit: {extracted_credit:.2f}")

print("\nAll Transactions:")
for i, t in enumerate(txns):
    print(f"{i+1:>3}. Date: {t['date']} | Dr: {t['debit']:>12.2f} | Cr: {t['credit']:>12.2f} | Bal: {t['balance']:>12.2f} | Desc: {t['remarks'][:50]}")
