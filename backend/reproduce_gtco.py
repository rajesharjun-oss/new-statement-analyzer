
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))

import pdf_extractor
import pdfplumber

def test_gtco_extraction():
    pdf_path = "temp_uploads/GTCO test.pdf"
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found")
        # Try finding it
        for root, dirs, files in os.walk("."):
            for f in files:
                if "GTCO test.pdf" in f:
                    pdf_path = os.path.join(root, f)
                    break
    
    print(f"Testing extraction for: {pdf_path}")
    
    # Manually check first page text to see what detect_template sees
    with pdfplumber.open(pdf_path) as pdf:
        combined_text = ""
        for p_idx in range(min(3, len(pdf.pages))):
            pg_text = pdf.pages[p_idx].extract_text() or ""
            if pg_text.strip():
                combined_text += "\n" + pg_text
                if len(combined_text) > 2000:
                    break
        
        print("--- COMBINED TEXT PREVIEW (used for detection) ---")
        print(combined_text[:2000])
        print("--- END PREVIEW ---")
        
        bank = pdf_extractor.detect_template(combined_text)
        print(f"Detected Bank: {bank}")
        
        # cuts = pdf_extractor.detect_column_cuts_from_header(words, bank)
        # print(f"Column Cuts: {cuts}")
        
    # Full extraction
    try:
        transactions, metadata = pdf_extractor.extract_transactions(pdf_path, bank_identifier="auto")
        print(f"Total Transactions: {len(transactions)}")
        if transactions:
            print(f"First transaction: {transactions[0]}")
            print(f"Last transaction: {transactions[-1]}")
            
            # Check for any None values in important fields
            none_dates = [t for t in transactions if t.get('date') is None]
            none_desc = [t for t in transactions if not t.get('description')]
            print(f"Transactions with None date: {len(none_dates)}")
            print(f"Transactions with empty description: {len(none_desc)}")
            
            # Summarize totals
            total_debit = sum(float(str(t.get('debit') or 0).replace(',', '')) for t in transactions)
            total_credit = sum(float(str(t.get('credit') or 0).replace(',', '')) for t in transactions)
            print(f"Calculated Total Debit: {total_debit:,.2f}")
            print(f"Calculated Total Credit: {total_credit:,.2f}")
            
    except Exception as e:
        print(f"Extraction failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_gtco_extraction()
