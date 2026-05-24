import pdfplumber
from pathlib import Path

pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\FBN - Dec25.pdf"
output_path = "fbn_words_dump.txt"

with pdfplumber.open(pdf_path) as pdf:
    with open(output_path, "w", encoding="utf-8") as f:
        for i, page in enumerate(pdf.pages):
            f.write(f"--- Page {i+1} ---\n")
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            for w in words:
                f.write(f"[{w['x0']:.1f}, {w['x1']:.1f}, {w['top']:.1f}] {w['text']}\n")
            if i >= 1: break # Just first 2 pages

print(f"Dumped words to {output_path}")
