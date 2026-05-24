import pdfplumber
from pathlib import Path

def dump_headers(pdf_path):
    print(f"\n--- DUMPING: {pdf_path} ---")
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(min(2, len(pdf.pages))):
            print(f"PAGE {i}:")
            words = pdf.pages[i].extract_words()
            from collections import defaultdict
            rows = defaultdict(list)
            for w in words:
                rows[round(w['top'])].append(w['text'])
            for y in sorted(rows.keys())[:20]: # First 20 rows
                print(f"Y={y}: {' '.join(rows[y])}")

dump_headers("temp_uploads/FCMB test.pdf")
dump_headers("temp_uploads/STERLING test.pdf")
