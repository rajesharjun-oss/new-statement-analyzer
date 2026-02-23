import traceback
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

from pdf_extractor import extract_transactions

log_file = "debug_traceback.txt"

with open(log_file, "w", encoding="utf-8") as f:
    sys.stdout = f
    sys.stderr = f
    
    try:
        print("Starting extraction...")
        txns, meta = extract_transactions('test_fidelity.pdf.pdf', 'fidelity')
        print(f"Success! Found {len(txns)} transactions")
    except Exception:
        print("\n=== TRACEBACK ===")
        traceback.print_exc()

print(f"Extraction finished. Check {log_file} for details.")
