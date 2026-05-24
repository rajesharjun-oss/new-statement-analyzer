from pypdf import PdfReader

def test_pypdf(pdf_path):
    print(f"--- PyPDF Test: {pdf_path} ---")
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    text = page.extract_text()
    if text.strip():
        print("PyPDF extracted text!")
        print(text[:500])
    else:
        print("PyPDF extracted NO text.")

test_pypdf("temp_uploads/UBA test.pdf")
