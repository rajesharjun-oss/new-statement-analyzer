
import os
import sys
from pathlib import Path

# Add the current directory to sys.path so we can import pdf_extractor
sys.path.append(os.path.dirname(__file__))

from pdf_extractor import extract_transactions, detect_ecobank_pdf

def full_scan():
    uploads = Path("backend/temp_uploads")
    if not uploads.exists():
        uploads = Path("temp_uploads")
        
    pdfs = list(uploads.glob("*.pdf"))
    print(f"Scanning {len(pdfs)} PDFs in {uploads.absolute()}\n")
    
    results = []
    
    for f in pdfs:
        path = str(f)
        is_eco = detect_ecobank_pdf(path)
        
        if not is_eco:
            # Maybe it's Ecobank but detector is too strict?
            # Try to force it if the name looks like a statement
            pass
            
        try:
            # We want to find the 142 count
            txns, meta = extract_transactions(path, "auto")
            count = len(txns)
            bank = meta.get("bank", "unknown")
            
            if bank == "ecobank" or count == 142:
                print(f"TARGET CANDIDATE: {f.name} | Bank: {bank} | Count: {count}")
                results.append((f.name, bank, count))
        except:
            pass

    print("\n--- Summary of Candidates ---")
    for name, bank, count in results:
        print(f"{name}: {bank} ({count} txns)")

if __name__ == "__main__":
    full_scan()
