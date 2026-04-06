import pdfplumber
import os

pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\MOSES TRANSPORT LIMITED WEMA.pdf"

print(f"\n{'#'*60}")
print(f"!!! ATOMIC TAIL AUDIT: {os.path.basename(pdf_path)} !!!")

with pdfplumber.open(pdf_path) as pdf:
    last_pages = pdf.pages[-2:]
    for i, page in enumerate(last_pages):
        page_num = len(pdf.pages) - 1 + i
        text = page.extract_text()
        print(f"\n--- [PAGE {page_num+1}] RAW TEXT ---")
        if text:
            print(text)
        else:
            print("[EMPTY TEXT LAYER]")
print(f"\n{'#'*60}\n")
