from pathlib import Path
import pdfplumber

def search():
    for f in Path('c:/Users/ionawoga/Desktop/Statement-analyzer-3.0-1/backend/temp_uploads').glob('*.pdf'):
        try:
            with pdfplumber.open(f) as pdf:
                page1 = pdf.pages[0].extract_text()
                if not page1: continue
                if "CORECOST" in page1.upper() or "PROVIDUS" in page1.upper() or "ADAM" in page1.upper():
                    print(f"MATCH: {f.name}")
        except Exception as e:
            pass

if __name__ == '__main__':
    search()
