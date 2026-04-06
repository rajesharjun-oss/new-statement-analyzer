import sys
import os
import pdfplumber
from pathlib import Path

# Add backend to path
sys.path.append(os.path.abspath("backend"))

pdf_path = Path("backend/temp_uploads/Access2.0.pdf")

print(f"Header band inspection for {pdf_path}...")
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    words = page.extract_words()
    
    # Print all words around y=389 (the header band)
    band_words = [w for w in words if abs(w['top'] - 389) < 10]
    
    print(f"Found {len(band_words)} words in band.")
    for w in band_words:
        print(f"'{w['text']}' @ x0={w['x0']:.2f}, x1={w['x1']:.2f}, top={w['top']:.2f}")

    # Also look at some numbers on the same page
    number_words = [w for w in words if w['top'] > 400 and ('.' in w['text'] or ',' in w['text'])]
    print("\nSample numbers:")
    for w in number_words[:10]:
         print(f"'{w['text']}' @ x0={w['x0']:.2f}, x1={w['x1']:.2f}, top={w['top']:.2f}")
