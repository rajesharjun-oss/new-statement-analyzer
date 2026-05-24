
import pdfplumber
from pathlib import Path

pdf_path = 'temp_uploads/190cb33d-d970-48a5-9016-91999032a290.pdf'

with pdfplumber.open(pdf_path) as pdf:
    with open('debug_coords_paged.txt', 'w', encoding='utf-8') as f:
        for i in range(len(pdf.pages)):
            page = pdf.pages[i]
            f.write(f"\n--- PAGE {i+1} ---\n")
            words = page.extract_words(x_tolerance=1.5, y_tolerance=2.0)
            words.sort(key=lambda w: (round(w['top'], 1), w['x0']))
            
            for w in words:
                f.write(f"Top: {w['top']:>7.2f} | x0: {w['x0']:>7.2f} | x1: {w['x1']:>7.2f} | Text: {w['text']}\n")
