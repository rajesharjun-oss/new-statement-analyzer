import pdfplumber
with pdfplumber.open('temp_uploads/WEMA test.pdf') as pdf:
    for i, p in enumerate(pdf.pages):
        words = p.extract_words()
        for w in words:
            try:
                val = float(w['text'].replace(',', ''))
                if val in [1000000000.0, 2221502732.20, 1663226399.40, 1666352459.00]:
                    print(f"FOUND {w['text']} on page {i} at x0={w['x0']:.2f}, top={w['top']:.2f}, x1={w['x1']:.2f}")
            except:
                pass
