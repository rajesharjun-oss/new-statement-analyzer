import sys
import os
from pathlib import Path
import json

sys.path.append(os.path.join(os.getcwd(), "backend"))
from pdf_extractor import extract_transactions

def verify():
    pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\FBN - Dec25.pdf"
    results = extract_transactions(pdf_path, bank_identifier="firstbank")
    
    if not results:
        print("No statements found.")
        return
        
    for i, res in enumerate(results):
        meta = res.get("metadata", {})
        txns = res.get("transactions", [])
        
        print(f"\nStatement {i+1}:")
        print(f"  Account No: {meta.get('account_no')}")
        print(f"  Account Name: {meta.get('account_name')}")
        print(f"  Transactions: {len(txns)}")
        print(f"  Validation: {meta.get('status')} (Match: {meta.get('validation_match', False)})")
        
        if txns:
            cred_txns = [t for t in txns if t.get('credit', 0) > 0]
            print(f"  Credit Transactions Found: {len(cred_txns)}")
            
            # Print sample to verify
            if cred_txns:
                print(f"  Sample Credit: Date={cred_txns[0]['date']}, amount={cred_txns[0]['credit']}, balance={cred_txns[0]['balance']}")

if __name__ == "__main__":
    verify()
