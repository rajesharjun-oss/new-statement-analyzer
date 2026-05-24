import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from categorization import categorize_single_transaction

# The transaction description from the user's screenshot
desc = "000013250628071514000251089068 638863826380583366-8 GAPS0493901874207935166S NIBSS Instant Payment Outward SECURITY 1 EXPENSE JUNE 2025D ALIYU 207935166 TO FBN - AHME ."
amount = 100000.00

txn = {
    "date": "2025-06-01",
    "description": desc,
    "debit": amount,
    "credit": 0.0,
    "balance": 0.0
}

print(f"--- Testing Transaction ---")
print(f"Desc: {txn['description']}")
print(f"Debit: {txn['debit']}")

result = categorize_single_transaction(txn)

print(f"--- Result ---")
print(f"Full Result: {result}", flush=True)
print(f"Category: {result.get('category')}", flush=True)
print(f"Rule ID: {result.get('ruleId')}", flush=True)
print(f"Confidence: {result.get('confidence')}", flush=True)
