import pdfplumber
with pdfplumber.open('temp_uploads/WEMA test.pdf') as pdf:
    for i, p in enumerate(pdf.pages):
        words = p.extract_words()
        for w in words:
            if w['text'] in ['1,000,000,000.00', '2,221,502,732.20', '1,663,226,399.40', '1,666,352,459.00']:
                print(f"FOUND {w['text']} on page {i} at x0={w['x0']:.2f}, x1={w['x1']:.2f}, top={w['top']:.2f}")
