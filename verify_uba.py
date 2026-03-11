import sys
import os
from pathlib import Path

sys.path.append(os.path.join(os.getcwd(), "backend"))
from pdf_extractor import extract_transactions

def verify(pdf_path, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    results = extract_transactions(pdf_path, bank_identifier="uba")
    
    if not results:
        print("No statements extracted.")
        return
        
    for i, res in enumerate(results):
        meta = res.get("metadata", {})
        txns = res.get("transactions", [])
        
        print(f"\nStatement {i+1}:")
        print(f"  Account Name: {meta.get('account_name')}")
        print(f"  Account No: {meta.get('account_no')}")
        print(f"  Method: {meta.get('method', 'word-bucketing')}")
        print(f"  Transactions: {len(txns)}")
        
        if txns:
            cred_txns = [t for t in txns if t.get('credit', 0) > 0]
            deb_txns = [t for t in txns if t.get('debit', 0) > 0]
            print(f"  Debit Transactions: {len(deb_txns)}")
            print(f"  Credit Transactions: {len(cred_txns)}")
            
            total_deb = sum(t.get("debit", 0) for t in txns)
            total_cred = sum(t.get("credit", 0) for t in txns)
            print(f"  Extracted Total Debit: {total_deb:,.2f}")
            print(f"  Extracted Total Credit: {total_cred:,.2f}")
            
            # Show first 3 transactions
            print(f"\n  First 3 transactions:")
            for j, t in enumerate(txns[:3]):
                print(f"    [{j}] date={t.get('date')} debit={t.get('debit')} credit={t.get('credit')} balance={t.get('balance')} desc={t.get('description','')[:50]}")

def main():
    base = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads"
    verify(os.path.join(base, "NGN JAN - JUNE UBA.pdf"), "NGN JAN - JUNE UBA (Template 1 - Searchable)")

if __name__ == "__main__":
    main()
