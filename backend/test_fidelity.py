from pdf_extractor import extract_transactions
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
import traceback
import sys

try:
    txns, meta = extract_transactions('test_fidelity.pdf.pdf', 'fidelity')
    print(f"\n===== SUCCESS =====")
    print(f"Transactions: {len(txns)}")
    if txns:
        print(f"\nFirst transaction:")
        print(f"  Date: {txns[0].get('date')}")
        print(f"  Description: {txns[0].get('description', '')[:100]}")
        print(f"  Debit: {txns[0].get('debit')}")
        print(f"  Credit: {txns[0].get('credit')}")
except Exception as e:
    print(f"\n===== ERROR =====")
    print(f"Error: {e}")
    print(f"\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)
