import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from wema_engine import extract_wema_via_coordinates

pdf_path = Path(r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\MOSES TRANSPORT LIMITED WEMA.pdf")

if not pdf_path.exists():
    print(f"ERROR: PDF not found at {pdf_path}")
    sys.exit(1)

print(f"\n{'='*60}")
print(f"!!! STANDALONE FORENSIC AUDIT: {pdf_path.name} !!!")
print(f"{'='*60}\n")

metadata = {}
txns, meta = extract_wema_via_coordinates(pdf_path, metadata)

print(f"\n{'#'*60}")
print(f"RESULTS FOR: {pdf_path.name}")
print(f"Total Transactions: {len(txns)}")
print(f"Metadata Total Debit: {meta.get('statement_total_debit', 0.0):,.2f}")
print(f"Metadata Total Credit: {meta.get('statement_total_credit', 0.0):,.2f}")
print(f"{'#'*60}\n")

if len(txns) == 552:
    print("SUCCESS: Transaction count matches expectation (552).")
else:
    print(f"CAUTION: Transaction count mismatch ({len(txns)} vs 552).")

if meta.get('statement_total_debit', 0.0) > 45000000000:
    print("SUCCESS: Billion-naira total identified (> 45B).")
else:
    print(f"FAILURE: Total debit is only {meta.get('statement_total_debit', 0.0):,.2f} (Expected 45.5B).")
