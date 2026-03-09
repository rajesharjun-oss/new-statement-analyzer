from pdf_extractor import extract_transactions
import pdfplumber

txns, meta = extract_transactions('temp_uploads/WEMA test.pdf', 'wema')
print(f'Total Extracted Transactions: {len(txns)}')

deb_sum = sum(t.get('debit', 0) for t in txns)
cre_sum = sum(t.get('credit', 0) for t in txns)
print(f'Sum of extracted debits: {deb_sum:,.2f}')
print(f'Sum of extracted credits: {cre_sum:,.2f}')

# Output rows that might be misaligned
for i, t in enumerate(txns):
    d = t.get('debit', 0)
    c = t.get('credit', 0)
    b = t.get('balance', 0)
    
    if d > 0 and c > 0:
        print(f"[{i}] WARN: Row has BOTH debit and credit => D:{d:,.2f} C:{c:,.2f} B:{b:,.2f} | {t['description']}")
    
    # Check if a huge debit might have accidentally been placed into credit
    if c > 4_000_000_000:
        print(f"[{i}] HUGE CREDIT: {c:,.2f} | {t['description']}")
    if b > 4_000_000_000:
        print(f"[{i}] HUGE BALANCE: {b:,.2f} | {t['description']}")

