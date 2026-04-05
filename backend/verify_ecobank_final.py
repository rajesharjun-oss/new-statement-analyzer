
import os
import sys
from pathlib import Path

# Add the current directory to sys.path so we can import pdf_extractor
sys.path.append(os.path.dirname(__file__))

from pdf_extractor import extract_transactions

def full_scan():
    # Try both possible upload locations
    search_dirs = [Path("backend/temp_uploads"), Path("temp_uploads")]
    
    results = []
    for uploads in search_dirs:
        if not uploads.exists():
            continue
            
        pdfs = list(uploads.glob("*.pdf"))
        print(f"Scanning {len(pdfs)} PDFs in {uploads.absolute()}\n")
        
        for f in pdfs:
            path = str(f)
            try:
                # We want to find the 142 count or Ecobank specifically
                data_list = extract_transactions(path, "auto")
                if not data_list: continue
                
                # extract_transactions returns a list of results (usually one)
                res = data_list[0]
                txns = res.get("transactions", [])
                meta = res.get("metadata", {})
                
                count = len(txns)
                bank = meta.get("bank", "unknown")
                
                if bank == "ecobank" or count == 142:
                    print(f"TARGET CANDIDATE: {f.name} | Bank: {bank} | Count: {count}")
                    results.append((f.name, bank, count))
            except Exception as e:
                # print(f"DEBUG: Failed {f.name}: {e}")
                pass

    print("\n--- Summary of Candidates ---")
    if not results:
        print("No Ecobank or 142-count candidates found.")
    else:
        for name, bank, count in results:
            print(f"{name}: {bank} ({count} txns)")

if __name__ == "__main__":
    full_scan()
