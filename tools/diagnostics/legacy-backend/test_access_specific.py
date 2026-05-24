
from pathlib import Path
from pdf_extractor import extract_transactions
import json

def test_access():
    pdf_path = "backend/temp_uploads/3c570c8c-b9c1-46da-98b6-15eb94a1d182.pdf"
    print(f"Testing Access Bank parser on: {pdf_path}")
    try:
        txns, meta = extract_transactions(pdf_path, "accessbank")
        print(f"Total transactions: {len(txns)}")
        print(f"Bank: {meta.get('bank')}")
        if txns:
            for t in txns[:10]:
                print(t)
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__": test_access()
