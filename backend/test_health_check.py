import os
from pathlib import Path
from pdf_extractor import extract_transactions

files_to_test = {
    "providus": "temp_uploads/Adam Providus.pdf",
    "wema": "temp_uploads/WEMA test.pdf",
    "gtco": "temp_uploads/GTCO test 2.pdf",
    "gtbank": "temp_uploads/GTCO test.pdf"
}

print("=== SYSTEM HEALTH CHECK ===")
for bank, path in files_to_test.items():
    if not os.path.exists(path):
        print(f"[{bank.upper()}] SKIPPED: File {path} not found.")
        continue
    
    try:
        txns, meta = extract_transactions(path, bank_identifier="auto")  # Use auto to test routing too
        
        detected_bank = meta.get("bank", "Unknown")
        txn_count = len(txns)
        total_dr = sum(t.get("debit", 0.0) for t in txns)
        total_cr = sum(t.get("credit", 0.0) for t in txns)
        
        print(f"[{bank.upper()}] File: {os.path.basename(path)}")
        print(f"  Detected Bank: {detected_bank}")
        print(f"  Transactions: {txn_count}")
        print(f"  Total Debit: {total_dr:,.2f}")
        print(f"  Total Credit: {total_cr:,.2f}")
    except Exception as e:
        print(f"[{bank.upper()}] FAILED: {str(e)}")
print("===========================")
