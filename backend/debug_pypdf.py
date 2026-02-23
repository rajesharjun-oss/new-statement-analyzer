from pypdf import PdfReader
import traceback

pdf_path = 'test_fidelity.pdf.pdf'

try:
    reader = PdfReader(pdf_path)
    page = reader.pages[1] # Page 2
    print("Attempting pypdf extraction...")
    text = page.extract_text()
    print(f"Extracted {len(text)} characters successfully!")
    print("\nFirst 200 chars:")
    print(text[:200])
except Exception:
    traceback.print_exc()
