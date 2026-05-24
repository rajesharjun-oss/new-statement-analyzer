import pdfplumber

pdf = pdfplumber.open("temp_uploads/Access bank test.pdf")
words = pdf.pages[0].extract_words()
# Print ALL words with top > 200 (where the table starts)
for w in words:
    if w['top'] > 200:
        print(f"'{w['text']:30s}' x0={w['x0']:7.2f} x1={w['x1']:7.2f} top={w['top']:7.2f}")
        if w['top'] > 350:
            break
pdf.close()
