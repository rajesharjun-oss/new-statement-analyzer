from pdf_extractor import extract_transactions
from pprint import pprint

pdf_path = "temp_uploads/ccef6abc-7f39-423f-aec6-352f84734ab5.pdf"
try:
    txns, meta = extract_transactions(pdf_path, bank_identifier="providus")
    print(f"Extracted {len(txns)} transactions")
    for i, t in enumerate(txns[:5]):
        print(f"Txn {i}: {t['date']} | {t['debit']} | {t['credit']} | {t['balance']} | {t['description'][:50]}")
    
    # Calculate sum of debits and credits
    total_debit = sum(t['debit'] for t in txns)
    total_credit = sum(t['credit'] for t in txns)
    print(f"\nTotal Debit: {total_debit}")
    print(f"Total Credit: {total_credit}")
    print("\nMetadata:", meta)

except Exception as e:
    import traceback
    traceback.print_exc()
