
import sys
import os
from pathlib import Path

# Allow running from backend
sys.path.insert(0, str(Path(__file__).parent))

from pdf_extractor import extract_transactions

pdf_path = 'temp_uploads/190cb33d-d970-48a5-9016-91999032a290.pdf'
if not os.path.exists(pdf_path):
    with open('debug_ecobank_final.txt', 'w', encoding='utf-8') as f:
        f.write(f"File not found: {pdf_path}\n")
    sys.exit(1)

txns, meta = extract_transactions(pdf_path, 'ecobank')

extracted_credit = sum(t.get('credit', 0) for t in txns)
extracted_debit = sum(t.get('debit', 0) for t in txns)

with open('debug_ecobank_final.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total Transactions: {len(txns)}\n")
    f.write(f"Statement Total Debit: {meta.get('statement_total_debit')}\n")
    f.write(f"Statement Total Credit: {meta.get('statement_total_credit')}\n")
    f.write(f"Extracted Total Debit: {extracted_debit:.2f}\n")
    f.write(f"Extracted Total Credit: {extracted_credit:.2f}\n")
    f.write("\nCredit Transactions:\n")
    for i, t in enumerate([t for t in txns if t.get('credit', 0) > 0]):
        f.write(f"{i+1}. Date: {t['date']} | Cr: {t['credit']:.2f} | Desc: {t['remarks'][:50]}\n")
    f.write("\nAll Transactions:\n")
    for i, t in enumerate(txns):
        f.write(f"{i+1:>3}. Date: {t['date']} | Dr: {t['debit']:>12.2f} | Cr: {t['credit']:>12.2f} | Bal: {t['balance']:>12.2f}\n")
