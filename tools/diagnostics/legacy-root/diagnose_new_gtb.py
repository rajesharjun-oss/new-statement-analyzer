import sys
import os
from pathlib import Path

# Add backend to path
backend_path = os.path.join(os.getcwd(), "backend")
sys.path.insert(0, backend_path)

from pdf_extractor import extract_transactions

def diagnose_new_gtb():
    pdf_path = "backend/temp_uploads/OCT - DEC GTBs BANK STATEMENT PDF.pdf"
    print(f"Diagnosing: {pdf_path}")
    
    try:
        # Step 1: Detect template and extract
        txns, meta = extract_transactions(pdf_path, bank_identifier="auto")
        
        print(f"Detected Bank: {meta.get('bank')}")
        print(f"Total Transactions: {len(txns)}")
        
        # Step 2: Validate totals
        from validation import validate_totals
        val_result = validate_totals(txns, meta)
        print(f"\nValidation Result: {val_result['status']}")
        print(f"  Extracted Debit: {val_result['extracted_total_debit']}")
        print(f"  Extracted Credit: {val_result['extracted_total_credit']}")
        if val_result['status'] != 'Match':
             print(f"  WARNING: {val_result.get('message', 'No detail provided')}")
        
        if txns:
            print("\nFirst 3 Transactions:")
            for t in txns[:3]:
                print(f"  Date: {t['date']}, Desc: {t['description'][:30]}, Debit: {t['debit']}, Credit: {t['credit']}, Balance: {t['balance']}")
        
        # Check for zero amounts or missing fields
        valid_txns = [t for t in txns if (t.get('debit') or 0.0) > 0 or (t.get('credit') or 0.0) > 0]
        print(f"\nNon-zero movement transactions: {len(valid_txns)} / {len(txns)}")
        
        if len(txns) > 0 and len(valid_txns) == 0:
            print("WARNING: All transactions have zero amounts. Check column alignment!")

    except Exception as e:
        print(f"ERROR during extraction: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    diagnose_new_gtb()
