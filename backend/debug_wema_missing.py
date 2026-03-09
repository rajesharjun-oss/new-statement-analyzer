from pdf_extractor import extract_transactions
import pdfplumber
import re

txns, meta = extract_transactions('temp_uploads/WEMA test.pdf', 'wema')
largest_txns = sorted(txns, key=lambda x: x.get('debit', 0), reverse=True)[:10]

print('Largest Extracted Debits:')
for t in largest_txns:
    print(f"{t['date']} | {t['debit']:,.2f} | {t.get('description', '')[:30]}")

print('\nTop largest raw debits in text (heuristic):')
with pdfplumber.open('temp_uploads/WEMA test.pdf') as pdf:
    for i, p in enumerate(pdf.pages):
        text = p.extract_text()
        amounts = re.findall(r'\b\d{1,3}(?:,\d{3}){2,}\.\d{2}\b', text or '')
        b_amounts = [float(a.replace(',', '')) for a in amounts if len(a) > 13 and float(a.replace(',', '')) < 40_000_000_000]
        big_debits = [a for a in b_amounts if a > 500_000_000]
        if big_debits:
             print(f'Page {i} big amounts: {big_debits}')
