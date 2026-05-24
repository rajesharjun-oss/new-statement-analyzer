import requests

def test_api(pdf_path, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    
    url = "http://localhost:8000/analyze"
    with open(pdf_path, "rb") as f:
        resp = requests.post(url, files={"file": (pdf_path.split("\\")[-1], f, "application/pdf")}, data={"bank": "uba"})
    
    if resp.status_code != 200:
        print(f"ERROR: HTTP {resp.status_code}")
        print(resp.text[:500])
        return
    
    data = resp.json()
    summary = data.get("summary", {})
    txns = data.get("transactions", [])
    
    print(f"Status: {resp.status_code}")
    print(f"Account: {summary.get('accountName')}")
    print(f"Bank: {summary.get('bank')}")
    print(f"Transaction Count: {summary.get('transactionCount')}")
    print(f"Total Debit: {summary.get('totalDebit'):,.2f}")
    print(f"Total Credit: {summary.get('totalCredit'):,.2f}")
    print(f"Validation: {summary.get('validationStatus')}")
    
    if txns:
        print(f"\nFirst 3 transactions:")
        for i, t in enumerate(txns[:3]):
            print(f"  [{i}] date={t.get('date')} debit={t.get('debit')} credit={t.get('credit')} bal={t.get('balance')} desc={str(t.get('description',''))[:50]}")

if __name__ == "__main__":
    test_api(r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\UBA test.pdf", 
             "UBA test.pdf OCR (API End-to-End Test)")
