from pdf_extractor import extract_transactions
import pdfplumber

txns, meta = extract_transactions('temp_uploads/WEMA test.pdf', 'wema')
print("Extracted transactions:", len(txns))

# Dump row 709
for i, t in enumerate(txns):
    if t.get('debit') == 0 and t.get('credit') == 0:
        desc = t.get('description', '')
        if 'S15448040' in desc or 'S14848075' in desc:
            print(f"FOUND SUSPECT ROW {i}:")
            print(t)
