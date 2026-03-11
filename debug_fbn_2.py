import sys
import os
import pdfplumber
from pathlib import Path

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))
from pdf_extractor import detect_firstbank_columns, assign_row_to_cols, group_words_to_rows

def test():
    pdf_path = Path(r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\FBN - Dec25.pdf")
    with pdfplumber.open(pdf_path) as pdf:
        # FirstBank statement seems to start on page 1 (index 0)
        page = pdf.pages[0]
        words = page.extract_words(x_tolerance=2, y_tolerance=2)
        
        cuts = detect_firstbank_columns(words)
        print(f"Cuts: {cuts}")
        
        if cuts:
            rows = group_words_to_rows(words, y_tol=3.0)
            for r in rows:
                line = " ".join([w["text"] for w in r["words"]])
                if "10-Dec-2025" in line:
                    assigned = assign_row_to_cols(r["words"], cuts)
                    print(f"Row: {line}")
                    print(f"Assigned: {assigned}")

if __name__ == "__main__":
    test()
