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
        
        # Find the header row index
        idx_header = -1
        for i, r in enumerate(rows):
            line = " ".join([w["text"] for w in r["words"]]).upper()
            if "DATE" in line and "DEPOSIT" in line and "WITHDRAWAL" in line:
                idx_header = i
                break
                
        if idx_header != -1:
            for i, r in enumerate(rows[idx_header+1:idx_header+15]):
                line = " ".join([w["text"] for w in r["words"]])
                if "02-Oct-2025" in line or "NIP" in line or "8530043328394" in line:
                    print(f"\n--- Row {i} ---")
                    print(line)
                    for w in r["words"]:
                        print(f"Word: '{w['text']}' x0={w['x0']:.1f} x1={w['x1']:.1f}")
                    assigned = assign_row_to_cols(r["words"], cuts)
                    print(f"Assigned: {assigned}")

if __name__ == "__main__":
    test()
