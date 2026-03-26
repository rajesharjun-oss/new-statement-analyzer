import sys
import os
import time
from pathlib import Path

# Add backend to path
sys.path.append(os.path.abspath("backend"))

from pdf_extractor import extract_transactions

def test_uba_extraction():
    pdf_path = "backend/temp_uploads/NGN JAN - JUNE UBA.pdf"
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found")
        return

    print(f"--- Testing {pdf_path} ---")
    start_time = time.time()
    
    # Run with auto-detection
    results = extract_transactions(pdf_path, bank_identifier='auto')
    
    end_time = time.time()
    duration = end_time - start_time
    
    if not results:
        print("FAILED: No results returned")
        return

    first_stmt = results[0]
    txns = first_stmt.get("transactions", [])
    meta = first_stmt.get("metadata", {})
    
    print(f"Detected Bank: {meta.get('bank')}")
    print(f"Transaction Count: {len(txns)}")
    print(f"Time Taken: {duration:.2f} seconds")
    
    if len(txns) == 86:
        print("SUCCESS: Transaction count matches expectation (86)")
    else:
        print(f"WARNING: Transaction count mismatch. Expected 86, got {len(txns)}")

if __name__ == "__main__":
    test_uba_extraction()
