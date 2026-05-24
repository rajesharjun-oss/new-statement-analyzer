import sys
import os
import re
from pathlib import Path

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from pdf_extractor import extract_transactions
from validation import validate_totals

pdf_path = os.path.join(os.getcwd(), "backend", "temp_uploads", "GTCO test 2.pdf")
if not os.path.exists(pdf_path):
    print(f"File not found: {pdf_path}")
    sys.exit(1)

print(f"Analyzing {pdf_path}...")
transactions, metadata = extract_transactions(pdf_path, bank_identifier='gtco')
validation = validate_totals(transactions, metadata)

print("\n--- METADATA ---")
for k, v in metadata.items():
    print(f"{k}: {v}")

print("\n--- VALIDATION ---")
for k, v in validation.items():
    print(f"{k}: {v}")

print("\n--- FIRST 5 TRANSACTIONS ---")
for i, t in enumerate(transactions[:5]):
    print(f"{i+1}: {t}")

# Check for huge values
huge_debits = [t for t in transactions if t.get('debit') and len(str(t['debit']).replace(',', '').split('.')[0]) > 12]
if huge_debits:
    print(f"\n--- FOUND {len(huge_debits)} HUGE DEBITS ---")
    for t in huge_debits[:5]:
        print(t)
else:
    print("\nNo huge debit values found in individual transactions.")

# Check for string concatenation sum in Python logic (simulated)
total_debit_str = "0"
for t in transactions:
    total_debit_str += str(t.get('debit', 0) or 0)

print(f"\nConcatenated string length: {len(total_debit_str)}")
print(f"Concatenated string start: {total_debit_str[:50]}")
