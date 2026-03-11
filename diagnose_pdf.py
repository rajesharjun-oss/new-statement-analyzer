import pdfplumber
import re
from pathlib import Path

def parse_acc(text):
    m = re.search(r"(?:Account No|Acc No|Account Number)[:\s]*(\d{10,12})", text, re.I)
    return m.group(1) if m else None

pdf_path = "backend/temp_uploads/OCT - DEC GTBs BANK STATEMENT PDF.pdf"
with pdfplumber.open(pdf_path) as pdf:
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        acc = parse_acc(text)
        is_header = "CUSTOMER STATEMENT" in text or "Statement Period" in text
        print(f"Page {i+1}: Acc={acc}, Header={is_header}")
