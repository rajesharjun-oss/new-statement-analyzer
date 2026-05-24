import fitz
from pathlib import Path

pdf_path = "temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf"

print("Searching for the exact large amount...")
doc = fitz.open(pdf_path)
for page_num in range(len(doc)):
    page = doc.load_page(page_num)
    text = page.get_text("text")
    if "363" in text and "143" in text and "442" in text:
        lines = text.split('\n')
        for i, line in enumerate(lines):
             if "363" in line and "143" in line:
                 print(f"\n--- Context on Page {page_num + 1} ---")
                 start = max(0, i - 10)
                 end = min(len(lines), i + 10)
                 for j in range(start, end):
                     print(lines[j].strip())
