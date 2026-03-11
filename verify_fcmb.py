import sys
import os
from pathlib import Path
import json

sys.path.append(os.path.join(os.getcwd(), "backend"))
from pdf_extractor import extract_transactions

def verify():
    pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\FCMB Naira Q4.pdf"
    results = extract_transactions(pdf_path, bank_identifier="fcmb")
    
    if not results:
        print("No statements extracted.")
        return
        
    for i, res in enumerate(results):
        meta = res.get("metadata", {})
        txns = res.get("transactions", [])
        
        print(f"\nStatement {i+1}:")
        print(f"  Account Name: {meta.get('account_name')}")
        print(f"  Transactions: {len(txns)}")
        print(f"  Validation: {meta.get('status')} (Match: {meta.get('validation_match', False)})")
        
        if txns:
            cred_txns = [t for t in txns if t.get('credit', 0) > 0]
            print(f"  Credit Transactions Found: {len(cred_txns)}")
            
            total_deb = sum(t.get("debit", 0) for t in txns)
            total_cred = sum(t.get("credit", 0) for t in txns)
            print(f"  Extracted Total Debit: {total_deb:,.2f}")
            print(f"  Extracted Total Credit: {total_cred:,.2f}")

if __name__ == "__main__":
    verify()
