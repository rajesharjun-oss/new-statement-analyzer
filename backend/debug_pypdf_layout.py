from pypdf import PdfReader
import traceback

pdf_path = 'test_fidelity.pdf.pdf'

try:
    reader = PdfReader(pdf_path)
    page = reader.pages[1] # Page 2
    print("Attempting pypdf layout=True extraction...")
    text = page.extract_text(layout=True)
    print(f"Extracted {len(text)} characters successfully!")
    print("\nSample (lines 10-20):")
    lines = text.splitlines()
    for l in lines[10:20]:
        print(f"|{l}|")
except Exception:
    traceback.print_exc()
