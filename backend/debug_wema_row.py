import pdfplumber

with pdfplumber.open('temp_uploads/WEMA test.pdf') as pdf:
    # Page 32
    page = pdf.pages[32]
    words = page.extract_words()
    
    y = 808
    row = [w for w in words if abs(w['top'] - y) < 5]
    row.sort(key=lambda x: x['x0'])
    print(f'Row words at y={y}:')
    for w in row:
        print(f" {w['text']:>20}  [x0={w['x0']:.1f}, x1={w['x1']:.1f}]")
