import sys
import os
import json
from pathlib import Path

sys.path.append(os.path.join(os.getcwd(), "backend"))
import pdfplumber
from pdf_extractor import detect_fcmb_columns, group_words_to_rows, assign_row_to_cols

def test():
    pdf_path = Path(r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\FCMB Naira Q4.pdf")
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(x_tolerance=2, y_tolerance=2)
        
        cuts = detect_fcmb_columns(words)
        
        rows = group_words_to_rows(words, y_tol=3.0)
        data_rows = []
        for r in rows:
            line = " ".join([w["text"] for w in r["words"]])
            if "02-Oct-2025" in line:
                data_rows.append(r)
                
        if data_rows:
            r0 = data_rows[0]
            print(f"Cuts: {cuts}")
            for w in r0["words"]:
                print(f"Word: '{w['text']}' x0={w['x0']:.1f} x1={w['x1']:.1f}")
            
            assigned = assign_row_to_cols(r0["words"], cuts)
            print(f"Assigned: {assigned}")

if __name__ == "__main__":
    test()
