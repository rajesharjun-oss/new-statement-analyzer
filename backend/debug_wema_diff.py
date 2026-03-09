import pdfplumber
import re
from pdf_extractor import extract_transactions

txns, meta = extract_transactions('temp_uploads/WEMA test.pdf', 'wema')
extracted_debits = [t.get('debit', 0) for t in txns if t.get('debit', 0) > 0]

print(f"Extracted Sum: {sum(extracted_debits):,.2f}")

raw_debits = []
with pdfplumber.open('temp_uploads/WEMA test.pdf') as pdf:
    for page in pdf.pages:
        # We need to find numbers that are in the "Withdrawals" column!
        words = page.extract_words()
        
        # Approximate debit column x-range: 526 to 646
        debit_words = [w for w in words if 526 < w['x0'] < 646 and w['x1'] < 680]
        
        for w in debit_words:
            t = w['text'].replace(',', '')
            try:
                val = float(t)
                if val > 0:
                    raw_debits.append(val)
            except:
                pass

print(f"Raw Debit Column Sum: {sum(raw_debits):,.2f}")

# Cross check
extracted_copy = extracted_debits[:]
missing = []
for rd in sorted(raw_debits, reverse=True):
    if rd in extracted_copy:
        extracted_copy.remove(rd)
    else:
        missing.append(rd)

print(f"Missing debits (sum={sum(missing):,.2f}):")
for m in missing[:20]:
    print(f" - {m:,.2f}")
    
