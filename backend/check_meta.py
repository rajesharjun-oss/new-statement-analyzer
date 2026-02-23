
import pdfplumber
from pdf_extractor import parse_statement_metadata
from pathlib import Path

def check_meta():
    uploads = Path("backend/temp_uploads")
    for f in uploads.glob("*.pdf"):
        try:
            with pdfplumber.open(f) as pdf:
                text = pdf.pages[0].extract_text() or ""
                meta = parse_statement_metadata(text)
                print(f"FILE: {f.name} | BANK: {'ACCESS' if 'ACCESS' in text.upper() else '?'}")
                print(f"  NAME: {meta.get('account_name')}")
                print(f"  DEBIT: {meta.get('statement_total_debit')}")
        except:
            continue

if __name__ == "__main__": check_meta()
