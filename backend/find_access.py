
import os
import sys
from pathlib import Path
from pdf_extractor import extract_transactions

def find_and_test_access():
    temp_dir = Path("backend/temp_uploads")
    if not temp_dir.exists():
        print("Temp directory not found")
        return

    for f in temp_dir.glob("*.pdf"):
        print(f"Testing {f.name}...")
        try:
            txns, meta = extract_transactions(str(f), bank_identifier="auto")
            if meta.get("bank") == "accessbank":
                print(f"SUCCESS: Found Access Bank statement in {f.name}")
                print(f"Extracted {len(txns)} transactions")
                if txns:
                    for t in txns[:3]:
                        print(t)
                return
        except Exception as e:
            continue
    print("No Access Bank statement found in temp_uploads")

if __name__ == "__main__":
    find_and_test_access()
