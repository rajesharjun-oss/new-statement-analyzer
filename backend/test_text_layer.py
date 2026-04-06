import pdfplumber
import os

pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\MOSES TRANSPORT LIMITED WEMA.pdf"

if not os.path.exists(pdf_path):
    print(f"ERROR: File not found at {pdf_path}")
else:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[-1]
        text = page.extract_text()
        print(f"\n{'#'*60}")
        print(f"!!! RAW TEXT LAYER AUDIT: LAST PAGE ({len(pdf.pages)}) !!!")
        print(f"{'#'*60}\n")
        print(f"TEXT CONTENT FOUND:\n{text[-3000:] if text else 'EMPTY/NONE'}")
        print(f"\n{'#'*60}\n")
