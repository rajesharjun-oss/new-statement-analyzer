from pdf_extractor import extract_transactions
import pdfplumber

txns, meta = extract_transactions('temp_uploads/WEMA test.pdf', 'wema')
print("Extracted transactions:", len(txns))

print("\n--- ALL DEBITS > 100M ---")
for i, t in enumerate(txns):
    d = t.get('debit', 0)
    if d > 100_000_000:
        print(f"[{i}] D: {d:,.2f} | DESC: {t.get('description', '')[:50]}")

print("\n--- Rows 706 to 715 ---")
for i, t in enumerate(txns[706:716]):
    print(f"ROW {706+i}: D={t.get('debit',0)}, C={t.get('credit',0)}, B={t.get('balance',0)} | {t.get('description', '')}")
