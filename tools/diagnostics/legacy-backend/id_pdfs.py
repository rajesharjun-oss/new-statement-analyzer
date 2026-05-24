
import pdfplumber
from pathlib import Path

def identify_pdfs():
    uploads = Path("backend/temp_uploads")
    for f in uploads.glob("*.pdf"):
        try:
            with pdfplumber.open(f) as pdf:
                text = (pdf.pages[0].extract_text() or "").upper()
                if "ACCESS" in text:
                    print(f"ACCESS: {f.name}")
                if "ECOBANK" in text:
                    print(f"ECOBANK: {f.name}")
        except:
            continue

if __name__ == "__main__": identify_pdfs()
