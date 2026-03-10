import os
import sys

# Add backend to path
backend_path = os.path.join(os.getcwd(), "backend")
sys.path.insert(0, backend_path)

from pdf_extractor import extract_transactions

pdf_path = os.path.join(backend_path, "temp_uploads", "GTCO test 2.pdf")
if not os.path.exists(pdf_path):
    print(f"ERROR: {pdf_path} not found.")
    sys.exit(1)

print(f"Extracting transactions from {pdf_path}...")
transactions, metadata = extract_transactions(pdf_path, bank_identifier='gtco')

print(f"Total Transactions: {len(transactions)}")

# Check for huge debits (> 10 billion)
large_debits = [t for t in transactions if t.get("debit", 0) > 10_000_000_000]

print(f"Found {len(large_debits)} huge debits.")
for t in large_debits:
    print(f"PAGE {t.get('_page')} | DEBIT: {t.get('debit')} | REMARKS: {t.get('remarks')[:100]}")

# Check for 42127 record count
if len(transactions) == 42127:
    print("Record count 42,127 CONFIRMED.")
elif len(transactions) == 4212:
    print("Record count 4,212 found.")
else:
    print(f"Record count is {len(transactions)}")
