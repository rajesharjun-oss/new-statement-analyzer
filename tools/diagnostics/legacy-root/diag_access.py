import sys
import os
import re
from pathlib import Path
import pdfplumber

# Add backend to path
sys.path.append(os.path.abspath("backend"))

pdf_path = Path("backend/temp_uploads/Access2.0.pdf")

with pdfplumber.open(pdf_path) as pdf:
    p = pdf.pages[0]
    words = p.extract_words()
    
    # Target keywords
    keywords = ["DATE", "TRANSACTION", "DETAILS", "REFERENCE", "REF", "VALUE", "WITHDRAWALS", "DEBIT", "LODGEMENTS", "CREDIT", "BALANCE", "BAL"]
    header_words = [w for w in words if any(k in w["text"].upper() for k in keywords)]
    
    print(f"Total header words found: {len(header_words)}")
    
    rows = {}
    for w in header_words:
        y = round(w['top'])
        if y not in rows: rows[y] = []
        rows[y].append(w)
        
    for y, rw in rows.items():
        band = [w for w in header_words if abs(w['top'] - y) < 8.0]
        indicators = set([k for w in band for k in keywords if k in w["text"].upper()])
        print(f"Y={y}: {len(band)} words, Indicators ({len(indicators)}): {indicators}")
        print(f"  Words: {[w['text'] for w in band]}")
        
        if len(indicators) >= 4:
            print("\nTESTRUN for this band:")
            for r in [r"Date", r"Details|Transaction", r"Ref", r"Value", r"Withdrawals|Debit", r"Lodgements|Credit", r"Balance|Bal"]:
                matches = [w for w in band if re.search(r, w["text"], re.I)]
                print(f"  Regex '{r}': {[m['text'] for m in matches]}")
