import sys
import os
from pathlib import Path

sys.path.append(os.path.join(os.getcwd(), "backend"))
from pdf_extractor import extract_transactions

def verify():
    pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\UBA test.pdf"
    print("Testing UBA test.pdf (scanned/image PDF)...")
    results = extract_transactions(pdf_path, bank_identifier="uba")
    
    if not results:
        print("No statements extracted.")
        return
        
    for i, res in enumerate(results):
        meta = res.get("metadata", {})
        txns = res.get("transactions", [])
        print(f"\nStatement {i+1}:")
        print(f"  Method: {meta.get('method', 'word-bucketing')}")
        print(f"  Transactions: {len(txns)}")
        if meta.get("error"):
            print(f"  Error: {meta.get('error')}")

if __name__ == "__main__":
    verify()
