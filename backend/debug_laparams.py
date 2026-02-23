import pdfplumber
import traceback

pdf_path = 'test_fidelity.pdf.pdf'

try:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[1] # Page 2, which crashed
        print("Attempting extract_words with laparams=None...")
        try:
            # Note: extract_words doesn't take laparams in pdfplumber, 
            # but opening the PDF with laparams does.
            pass
        except: pass
        
    # Re-open with laparams=None
    with pdfplumber.open(pdf_path, laparams=None) as pdf:
        page = pdf.pages[1]
        print("Success opening with laparams=None. Extracting words...")
        words = page.extract_words()
        print(f"Extracted {len(words)} words successfully!")
        
except Exception:
    traceback.print_exc()
