
import pdfplumber
from pdf_extractor import extract_transactions, parse_statement_metadata
from pathlib import Path
import re

def diagnostic():
    uploads = Path("backend/temp_uploads")
    if not uploads.exists():
         print(f"ERROR: Directory {uploads} does not exist.")
         return
         
    files = list(uploads.glob("*.pdf"))
    print(f"Scanning {uploads} ({len(files)} files)...\n")
    
    for f in files:
        try:
            with pdfplumber.open(f) as pdf:
                text = (pdf.pages[0].extract_text() or "")
                upper_text = text.upper()
                
                bank = "Unknown"
                if "PROVIDUS" in upper_text: bank = "providus"
                elif "ECOBANK" in upper_text: bank = "ecobank"
                elif "ACCESS" in upper_text: bank = "accessbank"
                elif "ZENITH" in upper_text: bank = "zenith"
                
                print(f"--- FILE: {f.name} | DETECTED: {bank} ---")
                
                # Check Auto-detection in extractor
                txns, meta = extract_transactions(str(f), "auto")
                print(f"  Final Bank (Auto): {meta.get('bank')}")
                print(f"  Transactions Found: {len(txns)}")
                
                if len(txns) == 0:
                    peek = text[:200].replace('\n', ' ')
                    print(f"  CRITICAL: 0 transactions found for {bank}")
                    print(f"  Text Peek: {peek}")
                    
                    # Specific check for Providus Regex pattern
                    if bank == "providus":
                        date_pattern = re.compile(r'^(\d{1,2}-[A-Z]{3}-\d{4})')
                        matches = [line for line in text.split('\n') if date_pattern.match(line)]
                        print(f"  Providus Regex matches found in raw text: {len(matches)}")
                        if matches: print(f"  Example match: {matches[0]}")
                
                print("-" * 50)
        except Exception as e:
            print(f"  Error processing {f.name}: {e}")

if __name__ == "__main__":
    diagnostic()
