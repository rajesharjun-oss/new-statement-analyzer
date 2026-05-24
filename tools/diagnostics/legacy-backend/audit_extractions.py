from dotenv import load_dotenv
load_dotenv()
from pdf_extractor import extract_transactions
import json

banks = {
    'uba': 'temp_uploads/UBA test.pdf',
    'zenith': 'temp_uploads/Zenith bank test.pdf',
    'access': 'temp_uploads/Access bank test.pdf',
    'providus': 'temp_uploads/Adam Providus.pdf'
}

for b, p in banks.items():
    print(f"\n--- {b.upper()} AUDIT ---")
    try:
        txns, meta = extract_transactions(p, bank_identifier=b)
        print(f"Total: {len(txns)}")
        for i, t in enumerate(txns[:20]):
            print(f"{i}: {t.get('date')} | DR: {t.get('debit')} | CR: {t.get('credit')} | BAL: {t.get('balance')} | DESC: {t.get('description') or t.get('remarks')}")
    except Exception as e:
        print(f"ERROR {b}: {e}")
