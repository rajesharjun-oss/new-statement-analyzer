import sys
import os
import pdfplumber
from pathlib import Path

sys.path.append(os.path.join(os.getcwd(), "backend"))
from pdf_extractor import group_words_to_rows

def dump(pdf_path, label):
    print(f"\n{'='*80}")
    print(f"  {label}")
    print(f"{'='*80}")
    with pdfplumber.open(pdf_path) as pdf:
        # Page 1
        page = pdf.pages[0]
        text = page.extract_text() or ""
        print(f"\n--- RAW TEXT (first 2000 chars) ---")
        print(text[:2000])
        
        words = page.extract_words(x_tolerance=2, y_tolerance=2)
        rows = group_words_to_rows(words, y_tol=3.0)
        
        print(f"\n--- WORD ROWS (first 25) ---")
        for i, r in enumerate(rows[:25]):
            line = " ".join([w["text"] for w in r["words"]])
            print(f"Row {i:2d} (y={r['top']:.1f}): {line}")
        
        # Find header row
        print(f"\n--- HEADER CANDIDATES ---")
        for i, r in enumerate(rows):
            line_upper = " ".join([w["text"].upper() for w in r["words"]])
            if "DATE" in line_upper and ("BALANCE" in line_upper or "DEBIT" in line_upper or "CREDIT" in line_upper):
                print(f"Row {i:2d}: {line_upper}")
                for w in r["words"]:
                    print(f"  Word: '{w['text']}' x0={w['x0']:.1f} x1={w['x1']:.1f}")

def main():
    base = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads"
    dump(os.path.join(base, "NGN JAN - JUNE UBA.pdf"), "NGN JAN - JUNE UBA")
    dump(os.path.join(base, "UBA test.pdf"), "UBA test")

if __name__ == "__main__":
    main()
