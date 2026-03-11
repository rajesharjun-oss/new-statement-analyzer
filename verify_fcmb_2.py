import sys
import os
import json
from pathlib import Path

sys.path.append(os.path.join(os.getcwd(), "backend"))
from pdf_extractor import extract_transactions

def verify():
    pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\FCMB Naira Q4.pdf"
    results = extract_transactions(pdf_path, bank_identifier="fcmb")
    
    if results:
        txns = results[0]["transactions"]
        for i, t in enumerate(txns[:5]):
            print(f"Row {i}: {t}")

if __name__ == "__main__":
    verify()
