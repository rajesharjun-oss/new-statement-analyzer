import sys
import os
import pdfplumber
from pathlib import Path

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))
from pdf_extractor import detect_fcmb_columns, group_words_to_rows

def test():
    pdf_path = Path(r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\FCMB Naira Q4.pdf")
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(x_tolerance=2, y_tolerance=2)
        
        rows = group_words_to_rows(words, y_tol=3.0)
        for r in rows:
            line = " ".join([w["text"] for w in r["words"]])
            if "Date" in line and "Balance" in line:
                print(f"Header Row: {line}")
            
        cuts = detect_fcmb_columns(words)
        print(f"Original cuts output: {cuts}")

if __name__ == "__main__":
    test()
