import sys
from pathlib import Path

# Add backend directory to path if not running from there
sys.path.append(str(Path(__file__).parent))

from pdf_extractor import extract_transactions

pdf_path = Path("temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf")
results = extract_transactions(str(pdf_path), bank_identifier='wema')

print(f"Extracted {len(results)} statements")

for s_idx, stmt in enumerate(results):
    txns = stmt.get("transactions", [])
    meta = stmt.get("metadata", {})
    
    total_debit = sum(t.get('debit', 0.0) for t in txns)
    total_credit = sum(t.get('credit', 0.0) for t in txns)
    
    print(f"\nStatement {s_idx + 1}")
    print(f"Total Debit: {total_debit:,.2f}")
    print(f"Total Credit: {total_credit:,.2f}")
    
    # Let's find unusually large debit transactions (e.g. > 1B)
    large_txns = [t for t in txns if t.get('debit', 0.0) > 1000000000.0]
    if large_txns:
        print("\nLarge Debit Transactions (> 1B):")
        for t in large_txns:
            print(f"Date: {t.get('date')} | Desc: {t.get('description')} | Debit: {t.get('debit')} | Credit: {t.get('credit')} | Balance: {t.get('balance')}")
            
    # Print the first few and last few txns to get a sense
    if len(txns) > 0:
        print("\nFirst 3 txns:")
        for t in txns[:3]:
            print(t)
        print("\nLast 3 txns:")
        for t in txns[-3:]:
            print(t)
