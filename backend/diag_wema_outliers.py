import sys
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).parent))

from wema_engine import extract_wema_via_coordinates
import pdfplumber

pdf_path = "temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf"

# We run the extraction
print("Analyzing outliers...")
txns, meta = extract_wema_via_coordinates(Path(pdf_path), {"bank": "wema"})

# Sort by debit descending
txns_sorted = sorted(txns, key=lambda x: x.get('debit', 0.0), reverse=True)

print("\n--- TOP 50 DEBIT SUSPECTS ---")
for i, t in enumerate(txns_sorted[:50]):
    print(f"{i+1}. Page {t.get('page','?')}: {t.get('debit', 0.0):,.2f} | Desc: {t.get('description', '')[:50]} | Ref: {t.get('reference', '')}")

# Sort by credit descending
txns_credit_sorted = sorted(txns, key=lambda x: x.get('credit', 0.0), reverse=True)

print("\n--- TOP 50 CREDIT SUSPECTS ---")
for i, t in enumerate(txns_credit_sorted[:50]):
    print(f"{i+1}. Page {t.get('page','?')}: {t.get('credit', 0.0):,.2f} | Desc: {t.get('description', '')[:50]} | Ref: {t.get('reference', '')}")
