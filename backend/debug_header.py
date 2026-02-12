import pdfplumber
import sys

pdf_path = sys.argv[1]
with pdfplumber.open(pdf_path) as pdf:
    words = pdf.pages[0].extract_words()
    
    # Find header words (usually in top 100 pixels)
    header_words = [w for w in words if 30 < w['top'] < 100]
    header_words = sorted(header_words, key=lambda x: x['x0'])
    
    print("=== ECOBANK HEADER WORDS ===")
    for w in header_words:
        print(f"{w['text']:20s} | x0={w['x0']:6.1f} | x1={w['x1']:6.1f} | top={w['top']:5.1f}")
