import pdfplumber
import os

pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\MOSES TRANSPORT LIMITED WEMA.pdf"

if not os.path.exists(pdf_path):
    print(f"ERROR: File not found at {pdf_path}")
else:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        
        print(f"\n{'#'*60}")
        print(f"!!! DEEP FORENSIC AUDIT: PAGE 1 !!!")
        print(f"{'#'*60}\n")
        
        # Print every word starting with 'Total' or containing digits
        for w in words:
            txt = w['text']
            if "TOTAL" in txt.upper() or any(c.isdigit() for c in txt):
                print(f"[{txt}] | BBox: (y_top={w['top']:.2f}, y_bottom={w['bottom']:.2f}, x0={w['x0']:.1f}, x1={w['x1']:.1f})")
        
        print(f"\n{'#'*60}\n")
