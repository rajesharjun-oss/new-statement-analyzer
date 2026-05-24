import pdfplumber
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from wema_engine import detect_wema_columns

pdf_path = "temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf"
print(f"Investigating header detection across pages...")

with pdfplumber.open(pdf_path) as pdf:
    # Check pages at intervals to see if headers change or if they are found at all
    for p_idx in [0, 10, 50, 100, 300, 500, 800]:
        if p_idx >= len(pdf.pages): break
        page = pdf.pages[p_idx]
        words = page.extract_words()
        
        # Check for keywords manually first
        text = page.extract_text().upper()
        has_withdrawals = "WITHDRAWALS" in text
        has_deposits = "DEPOSITS" in text
        has_debit = "DEBIT" in text
        has_credit = "CREDIT" in text
        
        print(f"\n--- Page {p_idx + 1} ---")
        print(f"Keywords: WID={has_withdrawals}, DEP={has_deposits}, DEB={has_debit}, CRE={has_credit}")
        
        cuts = detect_wema_columns(words)
        if cuts:
            print(f"Cuts Detected: {list(cuts.keys())}")
            print(f"Debit Bounds: {cuts.get('debit')}")
            print(f"Credit Bounds: {cuts.get('credit')}")
        else:
            print("No Wema cuts detected on this page.")

        # Find the actual words for headers to see their x-coordinates
        headers = [w for w in words if w['text'].upper() in ["WITHDRAWALS", "DEPOSITS", "DEBIT", "CREDIT"]]
        for h in headers:
            print(f"  Header Word: '{h['text']}' at x0={h['x0']:.1f}, x1={h['x1']:.1f}")
