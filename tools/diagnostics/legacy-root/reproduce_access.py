import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(os.path.abspath("backend"))

from pdf_extractor import extract_transactions
from validation import validate_totals

pdf_path = Path("backend/temp_uploads/Access2.0.pdf")

print(f"Testing extraction for {pdf_path}...")
results = extract_transactions(pdf_path, bank_identifier="access")

if not results:
    print("No transactions found!")
    sys.exit(1)

for i, stmt in enumerate(results):
    txns = stmt["transactions"]
    meta = stmt["metadata"]
    val = validate_totals(txns, meta)
    
    print(f"\nStatement {i+1}:")
    print(f"Bank: {meta.get('bank')}")
    print(f"Account: {meta.get('account_name')}")
    print(f"Transactions: {len(txns)}")
    print(f"Metadata Total Debit: {meta.get('total_debit')}")
    print(f"Metadata Total Credit: {meta.get('total_credit')}")
    print(f"Extracted Total Debit: {sum(t['debit'] for t in txns):,.2f}")
    print(f"Extracted Total Credit: {sum(t['credit'] for t in txns):,.2f}")
    print(f"Validation Status: {val['status']}")
    if val['status'] == 'Failed':
        print(f"Warnings: {val['warnings']}")

    # Print first 5 txns for debugging
    print("\nFirst 5 transactions:")
    for t in txns[:5]:
        print(f"{t['date']} | {t['debit']} | {t['credit']} | {t['description'][:50]}...")
