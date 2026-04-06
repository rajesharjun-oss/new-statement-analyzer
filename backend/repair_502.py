import sys

file_path = r'c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\pdf_extractor.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update UBA call
old_uba = "txns = extract_transactions_via_ai(str(pdf_path), bank_identifier='uba')"
new_uba = "txns = extract_transactions_via_ai(str(pdf_path), bank_identifier='uba', max_pages=15)"
content = content.replace(old_uba, new_uba)

# 2. Update Access call
old_acc = "ai_txns = extract_transactions_via_ai(str(pdf_path), bank_identifier='access')"
new_acc = "ai_txns = extract_transactions_via_ai(str(pdf_path), bank_identifier='access', max_pages=15)"
content = content.replace(old_acc, new_acc)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Repair completed successfully: UBA and Access AI calls now include max_pages=15.")
