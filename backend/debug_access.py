import pdfplumber
from pathlib import Path

def debug_access(pdf_path):
    print(f"\n--- DEBUG ACCESS: {pdf_path} ---")
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        
        from collections import defaultdict
        rows = defaultdict(list)
        for w in words:
            rows[round(w['top'])].append(w)
            
        print("First 50 lines:")
        count = 0
        for y in sorted(rows.keys()):
            row = sorted(rows[y], key=lambda w: w['x0'])
            txt = " ".join([f"[{w['x0']:.1f}-{w['x1']:.1f}]'{w['text']}'" for w in row])
            print(f"Y={y}: {txt}")
            count += 1
            if count > 50: break

debug_access("temp_uploads/Access bank test.pdf")
