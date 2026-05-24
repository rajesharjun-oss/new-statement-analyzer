from pdf_extractor import extract_transactions
import sys
import pdfplumber

bank = sys.argv[1]
path = sys.argv[2]

try:
    with pdfplumber.open(path) as pdf:
         # Only 1 page for audit
         page = pdf.pages[0]
         txns, meta = extract_transactions(path, bank_identifier=bank)
         print(f"\n--- {bank.upper()} AUDIT ---")
    print(f"Total: {len(txns)}")
    for i, t in enumerate(txns[:10]):
         print(f"{i}: {t.get('date')} | DR: {t.get('debit')} | CR: {t.get('credit')} | BAL: {t.get('balance')} | DESC: {t.get('description') or t.get('remarks')}")
except Exception as e:
    print(f"ERROR {bank}: {e}")
