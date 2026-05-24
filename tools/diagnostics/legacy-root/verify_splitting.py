import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from pdf_extractor import extract_transactions
from validation import validate_totals

def verify():
    pdf_path = Path("backend/temp_uploads/OCT - DEC GTBs BANK STATEMENT PDF.pdf")
    if not pdf_path.exists():
        print(f"Error: {pdf_path} not found")
        return

    print(f"Testing split on: {pdf_path}")
    results = extract_transactions(pdf_path, bank_identifier="gtbank")
    
    print(f"Detected {len(results)} separate statements.")
    
    for i, res in enumerate(results):
        txns = res["transactions"]
        meta = res["metadata"]
        val = validate_totals(txns, meta)
        
        print(f"\nStatement {i+1}:")
        print(f"  Account No: {meta.get('account_no')}")
        print(f"  Account Name: {meta.get('account_name')}")
        print(f"  Transactions: {len(txns)}")
        print(f"  Validation: {val['status']} (Match: {val['totals_match']})")
        
        if txns:
            print(f"  First Txn Date: {txns[0]['date']}")
            print(f"  Last Txn Date: {txns[-1]['date']}")

if __name__ == "__main__":
    verify()
