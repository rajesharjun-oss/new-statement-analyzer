
from pdf_extractor import extract_transactions
from pathlib import Path

def test_failure():
    pdf_path = "backend/temp_uploads/86de914e-ba62-4f83-95ae-94ec143ffb55.pdf"
    print(f"Testing Access Bank failure sample: {pdf_path}")
    txns, meta = extract_transactions(pdf_path, "accessbank")
    print(f"Total transactions: {len(txns)}")
    print(f"Account Name: {meta.get('account_name')}")
    if txns:
        for t in txns[:5]:
            print(t)
    else:
        print("STILL BLANK!")

if __name__ == "__main__": test_failure()
