import os
import sys
from pathlib import Path
import pdfplumber

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from pdf_extractor import detect_column_cuts_from_header, group_words_to_rows, assign_row_to_cols

def debug_fbn():
    pdf_path = Path(r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\FBN - Dec25.pdf")
    if not pdf_path.exists():
        print(f"Error: {pdf_path} not found")
        return

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"\n--- Page {i+1} ---")
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            if not words:
                print("No words found on page.")
                continue
            
            cuts = detect_column_cuts_from_header(words, "firstbank")
            print(f"Detected Cuts: {cuts}")
            
            if cuts:
                # Test extract a few rows
                rows = group_words_to_rows(words, y_tol=3.0)
                found_samples = 0
                for r in rows:
                    row_data = assign_row_to_cols(r["words"], cuts)
                    # Check if it looks like a transaction row (has date and either debit or credit)
                    if row_data.get("date") and (row_data.get("debit") or row_data.get("credit")):
                        print(f"Sample Row: {row_data}")
                        found_samples += 1
                        if found_samples > 10: break
                
                if found_samples == 0:
                    print("No transaction rows found with these cuts.")

if __name__ == "__main__":
    debug_fbn()
