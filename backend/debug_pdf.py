import sys
import pdf_extractor
import json

# Redirect stdout to a file with explicit UTF-8 encoding
log_file = open("pdf_debug_log.txt", "w", encoding="utf-8")
sys.stdout = log_file
sys.stderr = log_file

# Path to the problematic PDF
pdf_path = r"C:\Users\ionawoga\Downloads\MY PROJECT\TESTING\0797242269Abc health.pdf"

try:
    print(f"Testing extraction on: {pdf_path}")
    # Force 'accessbank'
    transactions, metadata = pdf_extractor.extract_transactions(pdf_path, bank_identifier="accessbank")
    
    print("\nSUCCESS: Extracted transactions:")
    print(json.dumps(transactions[:2], indent=2, default=str)) 
    print(f"Total transactions: {len(transactions)}")
    
except Exception as e:
    print(f"\nERROR: Extraction failed: {e}")
    import traceback
    traceback.print_exc()
    
log_file.close()
