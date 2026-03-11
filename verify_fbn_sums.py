import sys
import os
from pathlib import Path

sys.path.append(os.path.join(os.getcwd(), "backend"))
from pdf_extractor import extract_transactions

def verify():
    pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\FBN - Dec25.pdf"
    results = extract_transactions(pdf_path, bank_identifier="firstbank")
    
    if results:
        txns = results[0]["transactions"]
        total_deb = sum(t.get("debit", 0) for t in txns)
        total_cred = sum(t.get("credit", 0) for t in txns)
        print(f"Calculated Total Debit: {total_deb:,.2f}")
        print(f"Calculated Total Credit: {total_cred:,.2f}")
        
if __name__ == "__main__":
    verify()
