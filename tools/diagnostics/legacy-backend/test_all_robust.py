
import pdfplumber
from pdf_extractor import extract_transactions
from pathlib import Path

def test_all():
    uploads = Path("backend/temp_uploads")
    for f in uploads.glob("*.pdf"):
        try:
            with pdfplumber.open(f) as pdf:
                text = (pdf.pages[0].extract_text() or "").upper()
                bank = None
                if "ACCESS" in text: bank = "accessbank"
                elif "ECOBANK" in text: bank = "ecobank"
                
                if bank:
                    print(f"\n--- Testing {bank.upper()}: {f.name} ---")
                    txns, meta = extract_transactions(str(f), bank)
                    print(f"  Transactions: {len(txns)}")
                    print(f"  Account Name: {meta.get('account_name')}")
                    if txns:
                        print(f"  First TXN: {txns[0]['date']} | {txns[0]['description'][:30]}")
        except Exception as e:
            print(f"  Error testing {f.name}: {e}")

if __name__ == "__main__":
    test_all()
