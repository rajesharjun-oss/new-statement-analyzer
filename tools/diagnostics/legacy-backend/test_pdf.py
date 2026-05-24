import pdfplumber
import sys

if len(sys.argv) < 2:
    print("Usage: python test_pdf.py <pdf_file>")
    sys.exit(1)

pdf_path = sys.argv[1]

with pdfplumber.open(pdf_path) as pdf:
    print(f"Total pages: {len(pdf.pages)}")
    
    for i, page in enumerate(pdf.pages[:3]):
        print(f"\n=== PAGE {i+1} ===")
        
        # Try text extraction
        text = page.extract_text()
        print(f"Text length: {len(text) if text else 0}")
        if text:
            print(f"First 500 chars:\n{text[:500]}")
        else:
            print("NO TEXT EXTRACTED")
        
        # Try word extraction
        words = page.extract_words()
        print(f"\nWord count: {len(words)}")
        if words:
            print(f"First 10 words: {[w['text'] for w in words[:10]]}")
        else:
            print("NO WORDS EXTRACTED - PDF IS LIKELY IMAGE-BASED/SCANNED")
