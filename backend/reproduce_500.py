import sys
import os

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath("."))

from pdf_extractor import extract_transactions
from categorization import categorize_transactions
from main import validate_totals

def test_mock_transactions():
    print("Testing mock transactions...")
    # This structure mirrors what repair_ref_branch_remarks returns
    mock_txns = [
        {
            "date": "01-Jun-2025",
            "value_date": "01-Jun-2025",
            "reference": "245893349GAP",
            "description": "635 AKIN ADESOLA",
            "branch": "IBADAN",
            "debit": "100.00",
            "credit": "0.00",
            "balance": "50000.00",
            "_page": 1,
            "_row": 1
        }
    ]
    
    try:
        print("Running categorize_transactions...")
        categorized = categorize_transactions(mock_txns)
        print("Categorized OK")
        
        # Test the final formatting loop from extract_transactions
        from pdf_extractor import parse_money
        final_transactions = []
        for txn in categorized:
            desc_parts = []
            ref_val = (txn.get("reference") or "").strip()
            branch_val = (txn.get("branch") or "").strip()
            narration_val = (txn.get("description") or "").strip()

            if ref_val and ref_val not in {"'", "GAP", "'GAP"}:
                desc_parts.append(ref_val)
            if branch_val:
                desc_parts.append(branch_val)
            if narration_val:
                desc_parts.append(narration_val)
            remarks = " ".join(desc_parts).strip()

            deb_val = parse_money(txn.get("debit", ""))
            cred_val = parse_money(txn.get("credit", ""))
            
            if deb_val == 0.0 and cred_val == 0.0:
                continue

            # This structure mirrors the final output in main.py
            final_transactions.append({
                "date": txn["date"],
                "value_date": txn.get("value_date", ""),
                "reference": ref_val,
                "originating_branch": branch_val,
                "remarks": remarks,
                "description": narration_val,
                "debit": deb_val,
                "credit": cred_val,
                "balance": parse_money(txn.get("balance", "")),
                "category": txn.get("category", "Unallocated"),
                "is_reversal": False,
                "_page": txn.get("_page"),
                "_row": txn.get("_row")
            })
        print(f"Final Build OK: {len(final_transactions)} txns")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_mock_transactions()
