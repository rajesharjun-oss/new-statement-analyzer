import pdfplumber
import math
from pathlib import Path

def debug_zenith_coords(pdf_path):
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        # Group by Y
        from collections import defaultdict
        rows = defaultdict(list)
        for w in words:
            rows[round(w['top'])] .append(w)
        
        print("Raw Coordinates Sample:")
        for y in sorted(rows.keys())[:100]:
            row = sorted(rows[y], key=lambda w: w['x0'])
            txt = " ".join([f"[{w['x0']:.1f}-{w['x1']:.1f}]'{w['text']}'" for w in row])
            print(f"Y={y}: {txt}")

debug_zenith_coords("temp_uploads/Zenith bank test.pdf")
