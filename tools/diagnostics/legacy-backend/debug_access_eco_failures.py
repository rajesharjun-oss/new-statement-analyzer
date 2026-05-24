
from pdf_extractor import extract_transactions
from pathlib import Path

def debug_failures():
    # Identified samples from previous research
    access_pdf = "backend/temp_uploads/86de914e-ba62-4f83-95ae-94ec143ffb55.pdf"
    ecobank_pdf = "backend/temp_uploads/190cb33d-d970-4ccb-9016-91999032a292.pdf"
    
    print("--- DEBUGGING ACCESS BANK ---")
    if Path(access_pdf).exists():
        txns, meta = extract_transactions(access_pdf, "accessbank")
        print(f"Sample: {access_pdf}")
        print(f"Transactions: {len(txns)}")
        print(f"Account Name: {meta.get('account_name')}")
    else:
        print(f"Access sample {access_pdf} not found.")

    print("\n--- DEBUGGING ECOBANK ---")
    if Path(ecobank_pdf).exists():
        txns, meta = extract_transactions(ecobank_pdf, "ecobank")
        print(f"Sample: {ecobank_pdf}")
        print(f"Transactions: {len(txns)}")
        print(f"Account Name: {meta.get('account_name')}")
    else:
        print(f"Ecobank sample {ecobank_pdf} not found.")

if __name__ == "__main__":
    debug_failures()
