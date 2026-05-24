import fitz
import sys
from pathlib import Path

pdf_path = "temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf"

print("Searching for the large amount...")
doc = fitz.open(pdf_path)
for page_num in range(len(doc)):
    page = doc.load_page(page_num)
    text = page.get_text("text")
    if "363" in text and "143" in text:
        # Search line by line
        for line in text.split('\n'):
            if "363" in line and "143" in line:
                print(f"Page {page_num + 1}: {line.strip()}")
                
        # Also print lines around it for context
        lines = text.split('\n')
        for i, line in enumerate(lines):
             if "363" in line and "143" in line:
                 print(f"\n--- Context on Page {page_num + 1} ---")
                 start = max(0, i - 5)
                 end = min(len(lines), i + 6)
                 for j in range(start, end):
                     print(lines[j].strip())
