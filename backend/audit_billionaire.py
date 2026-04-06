import pdfplumber
from pathlib import Path
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from wema_engine import extract_wema_summary

pdf_path = Path(r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\MOSES TRANSPORT LIMITED WEMA.pdf")

print(f"\n{'='*60}")
print(f"!!! ATOMIC BILLIONAIRE AUDIT: {pdf_path.name} !!!")
print(f"{'='*60}\n")

with pdfplumber.open(pdf_path) as pdf:
    print(f"Scanning head and tail of {len(pdf.pages)} pages...")
    summary = extract_wema_summary(pdf.pages)
    
    print(f"\n{'#'*60}")
    print(f"FINAL CAPTURED TOTALS:")
    print(f"DEBIT:  {summary.get('statement_total_debit', 0.0):,.2f}")
    print(f"CREDIT: {summary.get('statement_total_credit', 0.0):,.2f}")
    print(f"{'#'*60}\n")

    if summary.get('statement_total_debit', 0.0) > 1000000000:
        print("RESULT: SUCCESS - Billionaire total captured.")
    else:
        print("RESULT: FAILURE - Total not captured.")
