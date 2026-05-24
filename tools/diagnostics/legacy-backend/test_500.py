import os
import sys
from pathlib import Path
from pdf_extractor import extract_transactions
from main import analyze_statement
import requests

def test_all_pdfs():
    uploads_dir = Path("temp_uploads")
    for pdf_path in uploads_dir.glob("*.pdf"):
        print(f"\n--- Testing {pdf_path.name} ---")
        try:
            with open(pdf_path, "rb") as f:
                response = requests.post(
                    "http://localhost:8000/analyze",
                    data={"bank": "auto"},
                    files={"file": (pdf_path.name, f, "application/pdf")}
                )
            
            if response.status_code == 500:
                print(f"!!! FOUND HTTP 500 CRASH ON: {pdf_path.name} !!!")
                print("Error Details:")
                print(response.text)
                return pdf_path
            elif response.status_code != 200:
                print(f"Other Error {response.status_code}: {response.text}")
            else:
                print("Success")
                
        except Exception as e:
            print(f"Test script error: {e}")

if __name__ == "__main__":
    test_all_pdfs()
