import pdfplumber
import sys

path = "temp_uploads/Zenith bank test.pdf"
try:
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"Extracting page {i}...")
            words = page.extract_words()
            print(f"Page {i}: {len(words)} words.")
except Exception as e:
    print(f"CRASH: {e}")
