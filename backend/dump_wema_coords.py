import pdfplumber
from pathlib import Path

pdf_path = "temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf"
print(f"Dumping words from {pdf_path}...")

with pdfplumber.open(pdf_path) as pdf:
    # Look at page 319 (where we found 363)
    page = pdf.pages[318]
    words = page.extract_words()
    
    # Group into rows roughly
    rows = {}
    for w in words:
        y = round(w['top'] / 2) * 2 # Tighter Y grouping
        if y not in rows: rows[y] = []
        rows[y].append(w)
        
    for y in sorted(rows.keys()):
        row = sorted(rows[y], key=lambda w: w['x0'])
        row_text = "   ".join([f"[{w['text']} ({w['x0']:.1f}-{w['x1']:.1f})]" for w in row])
        # Only print rows that look like transactions
        if any(w['text'].count('/') >= 2 for w in row if '-' not in w['text']): # Date-like
            print(f"Y={y}: {row_text}")
