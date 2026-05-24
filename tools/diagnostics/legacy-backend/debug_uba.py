import pdfplumber
from pathlib import Path

def debug_uba(pdf_path):
    print(f"\n--- DEBUG UBA: {pdf_path} ---")
    if not Path(pdf_path).exists():
        print("File not found")
        return
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        
        from collections import defaultdict
        rows = defaultdict(list)
        for w in words:
            rows[round(w['top'])].append(w)
            
        print("First 100 lines:")
        count = 0
        for y in sorted(rows.keys()):
            row = sorted(rows[y], key=lambda w: w['x0'])
            txt = " ".join([f"[{w['x0']:.1f}-{w['x1']:.1f}]'{w['text']}'" for w in row])
            print(f"Y={y}: {txt}")
            count += 1
            if count > 100: break

debug_uba("temp_uploads/UBA test.pdf")
