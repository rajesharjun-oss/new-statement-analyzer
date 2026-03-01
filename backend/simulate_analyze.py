import sys
import os
import uuid
from pathlib import Path

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath("."))

from pdf_extractor import extract_transactions
from categorization import categorize_transactions
from excel_generator import generate_excel
from validation import validate_totals

def num(x):
    try:
        return float(str(x).replace(",", ""))
    except:
        return 0.0

def simulate_analyze():
    print("Simulating analyze_statement...")
    # Find a PDF to test with
    import glob
    pdfs = glob.glob("temp_uploads/*.pdf")
    if not pdfs:
        print("No PDFs found in temp_uploads")
        return
    
    stored_path = Path(pdfs[0])
    bank = "gtbank"
    print(f"Testing with {stored_path} and bank={bank}")
    
    try:
        # Step 1: Extract
        print("Step 1: Extract transactions...")
        transactions, metadata = extract_transactions(stored_path, bank_identifier=bank.lower())
        print(f"Extracted {len(transactions)} txns")
        
        # Step 2: Validate totals
        print("Step 2: Validate totals...")
        validation_result = validate_totals(transactions, metadata)
        print("Validation OK")
        
        # Step 3: Categorize
        print("Step 3: Categorize...")
        categorized_transactions = categorize_transactions(transactions)
        print("Categorization OK")
        
        # Step 4: Generate Excel
        print("Step 4: Generate Excel...")
        excel_path = Path("test_output.xlsx")
        generate_excel(categorized_transactions, validation_result, excel_path)
        print("Excel Generation OK")
        
        # Step 5: Build summary
        print("Step 5: Build summary...")
        total_debit = sum(num(t.get("debit")) for t in categorized_transactions)
        total_credit = sum(num(t.get("credit")) for t in categorized_transactions)
        dates = [t.get("date") for t in categorized_transactions if t.get("date")]
        period = metadata.get("statement_period") or (f"{dates[0]} to {dates[-1]}" if dates else "N/A")
        print(f"Summary OK: Period={period}, Total={total_debit}")
        
        print("ALL STEPS COMPLETED SUCCESSFULLY")
        
    except Exception as e:
        import traceback
        print("\nFATAL ERROR DETECTED:")
        traceback.print_exc()
        print(f"FAILED: {e}")

if __name__ == "__main__":
    simulate_analyze()
