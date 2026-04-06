import sys
import os
import time
from pathlib import Path
from dotenv import load_dotenv

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.append(str(backend_path))

from pdf_extractor import extract_transactions

# Load .env
load_dotenv()

test_files = [
    "backend/temp_uploads/Access2.0.pdf",
    "temp_uploads/323248f7-a2d1-437e-b0e5-a4025867f13c.pdf"
]

def run_timer_test():
    print(f"{'File':<45} | {'Txns':<6} | {'Time (s)':<10} | {'Status':<15}")
    print("-" * 85)
    
    for file_path in test_files:
        if not os.path.exists(file_path):
            print(f"Skipping {file_path} (File not found)")
            continue
            
        start_time = time.time()
        try:
            # extract_transactions returns a list of results (one per statement in PDF)
            results = extract_transactions(file_path)
            end_time = time.time()
            
            elapsed = round(end_time - start_time, 2)
            total_txns = sum(len(r.get("transactions", [])) for r in results)
            
            # Use the first result's validation status for the summary
            status = "N/A"
            if results:
                meta = results[0].get("metadata", {})
                status = meta.get("validation_status", "Generic")
            
            print(f"{os.path.basename(file_path):<45} | {total_txns:<6} | {elapsed:<10} | {status:<15}")
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    run_timer_test()
