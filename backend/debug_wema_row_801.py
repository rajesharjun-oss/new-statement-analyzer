import pdfplumber

with pdfplumber.open('temp_uploads/WEMA test.pdf') as pdf:
    page = pdf.pages[26]
    words = page.extract_words()
    
    y = 801
    row = [w for w in words if abs(round(w['top'] / 3) * 3 - y) < 2]
    row.sort(key=lambda x: x['x0'])
    print(f'Row words at y={y}:')
    for w in row:
        print(f" {w['text']:>20}  [x0={w['x0']:.1f}, x1={w['x1']:.1f}]")
