"""Quick end-to-end test: simulate what main.py does when bank=auto"""
from pathlib import Path
from pdf_extractor import extract_transactions

pdf = Path("temp_uploads/Access bank test.pdf")
txns, meta = extract_transactions(pdf, bank_identifier="auto")
print(f"Bank detected: {meta.get('bank', 'unknown')}")
print(f"Transactions: {len(txns)}")
if txns:
    for t in txns[:3]:
        print(f"  date={t.get('date')} debit={t.get('debit')} credit={t.get('credit')} desc={t.get('description','')[:50]}")
