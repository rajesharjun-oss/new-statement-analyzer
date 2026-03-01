import traceback
import sys
from pathlib import Path
from pdf_extractor import extract_transactions
import pdfplumber

def check_bank(pdf_path):
    """Try to detect which bank a PDF is, returns bank_identifier string."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""
            text_upper = text.upper()
            if "PROVIDUS" in text_upper:
                return "providus"
    except:
        pass
    return None

def run_all():
    uploads_dir = Path("temp_uploads")
    pdfs = sorted(uploads_dir.glob("*.pdf"))
    print(f"Testing {len(pdfs)} PDFs...\n")
    
    for pdf_path in pdfs:
        bank = check_bank(pdf_path)
        if bank != "providus":
            continue
        print(f"=== PROVIDUS PDF: {pdf_path.name} ===")
        try:
            txns, meta = extract_transactions(str(pdf_path), bank_identifier="providus")
            total_debit = sum(float(t.get("debit") or 0) for t in txns)
            total_credit = sum(float(t.get("credit") or 0) for t in txns)
            print(f"  OK: {len(txns)} txns | Debit={total_debit:.2f} | Credit={total_credit:.2f}")
        except Exception as e:
            print(f"  !!! CRASH: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    run_all()
