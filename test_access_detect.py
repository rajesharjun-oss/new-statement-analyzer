import sys
import os
import pdfplumber
from pathlib import Path

# Add backend to path
sys.path.append(os.path.abspath("backend"))

from access_engine import detect_access_columns

pdf_path = Path("backend/temp_uploads/Access2.0.pdf")

print(f"Testing detect_access_columns for {pdf_path}...")
with pdfplumber.open(pdf_path) as pdf:
    for i in range(min(5, len(pdf.pages))):
        print(f"\n--- Page {i} ---")
        words = pdf.pages[i].extract_words()
        print(f"Extraction yielded {len(words)} words.")
        cuts = detect_access_columns(words)
        if cuts:
            print(f"SUCCESS: Found cuts: {cuts}")
            break
        else:
            print(f"FAILED: No cuts found for page {i}")
