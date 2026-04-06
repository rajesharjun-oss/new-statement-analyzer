import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.abspath("backend"))

load_dotenv()

def test_config():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        print("FAIL: ANTHROPIC_API_KEY not found in .env")
        return
    print(f"SUCCESS: ANTHROPIC_API_KEY found (starts with {key[:10]}...)")

def test_categorization():
    from categorization import categorize_transactions
    
    mock_txns = [
        {"description": "GOOGLE *CLOUD PAYMENT", "debit": 5000.0, "credit": 0.0},
        {"description": "IKO EDC BILL PAYMENT", "debit": 12000.0, "credit": 0.0},
        {"description": "NIP TRF FROM OLAIDE", "debit": 0.0, "credit": 25000.0}
    ]
    
    print("\nTesting Categorization with Claude...")
    results = categorize_transactions(mock_txns)
    for t in results:
        print(f"Desc: {t.get('description')} -> Cat: {t.get('category')} (Source: {t.get('decision_source')})")

def test_audit():
    from claude_service import generate_audit_summary
    
    mock_txns = [
        {"date": "2024-01-01", "description": "Rent", "debit": 500000.0, "category": "Office Rent / Lease"},
        {"date": "2024-01-05", "description": "Salary", "debit": 100000.0, "category": "Salaries & Wages"},
        {"date": "2024-01-10", "description": "Client Payout", "credit": 1500000.0, "category": "Operating Income"}
    ]
    
    print("\nTesting Deep Audit Summary...")
    summary = generate_audit_summary(mock_txns, {"bank": "Test Bank", "account_name": "Antigravity Corp"})
    print("-" * 30)
    print(summary)
    print("-" * 30)

if __name__ == "__main__":
    test_config()
    test_categorization()
    test_audit()
