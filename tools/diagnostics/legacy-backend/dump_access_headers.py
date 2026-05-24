import pdfplumber
from pathlib import Path

pdf_path = Path("backend/temp_uploads/Access2.0.pdf")
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    words = page.extract_words()
    # Print the first 500 words with their (x0, top) coordinates
    # to identify the header row correctly.
    for i, w in enumerate(words[:500]):
        print(f"[{i:03}] {w['text']:20} (x0={w['x0']:>6.1f}, top={w['top']:>6.1f}, x1={w['x1']:>6.1f}, bottom={w['bottom']:>6.1f})")

    # Also extract text normally to see horizontal grouping
    print("\n--- RAW TEXT PREVIEW ---")
    print(page.extract_text()[:1000])
