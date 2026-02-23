from pypdf import PdfWriter, PdfReader
import pdfplumber
import traceback

pdf_path = 'test_fidelity.pdf.pdf'
repaired_path = 'repaired_fidelity.pdf'

try:
    print("Normalizing PDF with pypdf...")
    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    
    with open(repaired_path, "wb") as f:
        writer.write(f)
    print("Repair finished. Attempting pdfplumber on Page 1 of repaired PDF...")
    
    with pdfplumber.open(repaired_path) as pdf:
        page = pdf.pages[1]
        words = page.extract_words()
        print(f"Worked! Extracted {len(words)} words from Page 1 of repaired PDF.")
        
except Exception:
    traceback.print_exc()
