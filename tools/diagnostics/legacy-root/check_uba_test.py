import sys
import os
import pdfplumber
from pathlib import Path

def check():
    pdf_path = Path(r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\UBA test.pdf")
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Total pages: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages[:3]):
            text = page.extract_text() or ""
            words = page.extract_words(x_tolerance=2, y_tolerance=2) if hasattr(page, 'extract_words') else []
            images = page.images if hasattr(page, 'images') else []
            print(f"\nPage {i+1}:")
            print(f"  Text length: {len(text)}")
            print(f"  Words: {len(words)}")
            print(f"  Images: {len(images)}")
            if text:
                print(f"  Text preview: {text[:300]}")
            if words:
                print(f"  First 5 words: {[w['text'] for w in words[:5]]}")

if __name__ == "__main__":
    check()
