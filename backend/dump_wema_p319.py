import pdfplumber

pdf_path = "temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf"
print(f"Dumping words from {pdf_path} Page 319...")

with pdfplumber.open(pdf_path) as pdf:
    # Look at page 319 (index 318)
    page = pdf.pages[318]
    words = page.extract_words()
    
    # Sort and dump
    rows = {}
    for w in words:
        y = round(w['top'] / 1) * 1 # Very tight Y
        if y not in rows: rows[y] = []
        rows[y].append(w)
        
    for y in sorted(rows.keys()):
        row = sorted(rows[y], key=lambda w: w['x0'])
        row_text = "   ".join([f"[{w['text']} ({w['x0']:.1f}-{w['x1']:.1f})]" for w in row])
        if "363" in row_text:
             print(f"Y={y}: {row_text}")
