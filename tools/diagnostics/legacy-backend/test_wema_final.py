
import sys
from pathlib import Path
import pdfplumber

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from wema_engine import extract_wema_via_coordinates
from pdf_extractor import normalize_remarks
import json

pdf_path = Path("backend/temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf")
print(f"--- Fast Test Wema (First 20 Pages) ---")

with pdfplumber.open(pdf_path) as full_pdf:
    # Create a dummy object that mimics pdfplumber.PDF but only has 20 pages
    class DummyPDF:
        def __init__(self, pages):
            self.pages = pages
            self.metadata = full_pdf.metadata
    
    limited_pdf = DummyPDF(full_pdf.pages[:20])
    
    # Run the Wema engine directly
    wm_txns, wm_meta = extract_wema_via_coordinates(pdf_path, {}, pdf=limited_pdf)
    
    if wm_txns:
        txns = normalize_remarks(wm_txns)
        print(f"Status: SUCCESS")
        print(f"Total Transactions Extracted (P1-20): {len(txns)}")
        
        if len(txns) > 0:
            print("\nSample Transactions:")
            print(f"{'Date':<15} | {'Debit':>15} | {'Credit':>15} | {'Description'}")
            print("-" * 80)
            for t in txns[:10]:
                print(f"{t['date']:<15} | {t.get('debit',0):>15,.2f} | {t.get('credit',0):>15,.2f} | {t['remarks'][:45]}...")
                
            # Check for massive outliers (> 10 million)
            outliers = [t for t in txns if (t.get('debit',0) or 0) > 10_000_000 or (t.get('credit',0) or 0) > 10_000_000]
            if outliers:
                print(f"\n⚠️ WARNING: {len(outliers)} massive values found (P1-20)")
                for o in outliers:
                     print(f"  - Page {o.get('page','?')}: {o['date']} | D: {o.get('debit'):,.2f} | C: {o.get('credit'):,.2f}")
            else:
                print("\n✅ Clean Run: No massive hallucinated summary values found in first 20 pages.")
        else:
            print("\n❌ No transactions extracted from first 20 pages.")
    else:
        print("\n❌ Extraction failed to return results.")
