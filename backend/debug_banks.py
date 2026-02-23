
import pdfplumber
from pathlib import Path
from pdf_extractor import extract_transactions
import re

def check_all():
    uploads = Path("backend/temp_uploads")
    print(f"Checking files in {uploads}")
    
    banks_to_debug = ["accessbank", "ecobank", "providus"]
    
    for f in uploads.glob("*.pdf"):
        try:
            with pdfplumber.open(f) as pdf:
                raw_text = pdf.pages[0].extract_text() or ""
                text = raw_text.upper()
                
                detected = None
                if "PROVIDUS" in text: detected = "providus"
                elif "ECOBANK" in text: detected = "ecobank"
                elif "ACCESS" in text: detected = "accessbank"
                
                if detected in banks_to_debug:
                    print(f"\n--- FILE: {f.name} | BANK: {detected.upper()} ---")
                    txns, meta = extract_transactions(str(f), detected)
                    print(f"  Final Detected Bank: {meta.get('bank')}")
                    print(f"  Transactions Found: {len(txns)}")
                    if txns:
                        print(f"  First TXN: {txns[0]['date']} | {txns[0]['description'][:40]}")
                    else:
                        print(f"  STILL BLANK!")
                        peek = raw_text[:200].replace('\n', ' ')
                        print(f"  Text Peek: {peek}")
        except Exception as e:
            print(f"  Error processing {f.name}: {e}")

if __name__ == "__main__":
    check_all()
