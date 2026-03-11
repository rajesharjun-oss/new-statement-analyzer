import requests
import os

def test_stanc_ocr():
    url = "http://localhost:8000/analyze"
    pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\Standard chartered test.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return

    print(f"Testing Standard Chartered with new 2-phase OCR pipeline...")
    with open(pdf_path, "rb") as f:
        resp = requests.post(url, files={"file": (os.path.basename(pdf_path), f, "application/pdf")})
    
    if resp.status_code != 200:
        print(f"Error: {resp.status_code}")
        print(resp.text)
        return
        
    data = resp.json()
    summary = data.get("summary", {})
    print(f"Status: {resp.status_code}")
    print(f"Records: {summary.get('transactionCount')}")
    print(f"Debit: {summary.get('totalDebit'):,.2f}")
    print(f"Credit: {summary.get('totalCredit'):,.2f}")
    print(f"Expected Debit: 1,699,167.22")
    print(f"Difference: {1699167.22 - summary.get('totalDebit'):,.2f}")

if __name__ == "__main__":
    test_stanc_ocr()
