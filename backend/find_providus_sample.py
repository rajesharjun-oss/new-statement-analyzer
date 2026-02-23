
import pdfplumber
from pathlib import Path

def find_pdf():
    uploads = Path("backend/temp_uploads")
    for f in uploads.glob("*.pdf"):
        try:
            with pdfplumber.open(f) as pdf:
                text = pdf.pages[0].extract_text() or ""
                if "1305414806" in text or "PROVIDUS" in text.upper():
                    print(f"FOUND: {f.name}")
                    return f
        except:
            continue
    print("NOT FOUND")
    return None

if __name__ == "__main__":
    find_pdf()
