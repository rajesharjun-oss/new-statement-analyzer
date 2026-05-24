import sys
import os
import pdfplumber
from pathlib import Path

# Add backend to path
sys.path.append(os.path.abspath("backend"))

from access_engine import detect_access_columns

pdf_path = Path("backend/temp_uploads/Access2.0.pdf")

print(f"Investigating word coordinates in {pdf_path}...")
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    words = page.extract_words()
    
    # Find words that look like money (contain comma or dot)
    money_words = [w for w in words if ('.' in w['text'] or ',' in w['text']) and len(w['text']) > 5]
    
    for w in money_words[:20]:
        print(f"'{w['text']}' @ x0={w['x0']:.2f}, x1={w['x1']:.2f}, top={w['top']:.2f}")

    cuts = detect_access_columns(words)
    print(f"\nCurrent cuts: {cuts}")
