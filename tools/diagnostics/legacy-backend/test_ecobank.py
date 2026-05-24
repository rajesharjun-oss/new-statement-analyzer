"""
Quick test for the Ecobank-specific extractor.
Usage:
    cd backend
    python test_ecobank.py [optional_path_to.pdf]

If no PDF path is given it looks for any PDF in temp_uploads/.
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Allow running from the backend directory
sys.path.insert(0, os.path.dirname(__file__))

from pdf_extractor import extract_transactions

def find_test_pdf(hint: str = None) -> str:
    if hint:
        return hint
    # Try temp_uploads
    uploads = Path(__file__).parent / "temp_uploads"
    pdfs = list(uploads.glob("*.pdf"))
    if pdfs:
        print(f"Auto-found PDF: {pdfs[0]}")
        return str(pdfs[0])
    raise FileNotFoundError("No PDF supplied and none found in temp_uploads/")


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else find_test_pdf()
    print(f"\nTesting Ecobank parser on: {pdf_path}\n")

    try:
        txns, meta = extract_transactions(pdf_path, "ecobank")
    except Exception as e:
        import traceback
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    print(f"===== RESULT =====")
    print(f"Total transactions : {len(txns)}")
    print(f"Account name       : {meta.get('account_name', 'N/A')}")
    print(f"Statement period   : {meta.get('statement_period', 'N/A')}")
    print(f"Total debit        : {meta.get('statement_total_debit', 'N/A')}")
    print(f"Total credit       : {meta.get('statement_total_credit', 'N/A')}")
    print()

    for i, t in enumerate(txns[:20], 1):
        ref = t.get("reference", "")
        date = t.get("date", "")
        # Filter non-ascii from desc for console safety
        desc_safe = str(t.get('description', '')).encode('ascii', 'ignore').decode('ascii')
        dr_raw = t.get('_raw_debit', 'N/A')
        cr_raw = t.get('_raw_credit', 'N/A')
        print(
            f"{i:>3}. Date={date} | Dr={t.get('debit', 0):>12.2f} (raw={dr_raw}) | "
            f"Cr={t.get('credit', 0):>12.2f} (raw={cr_raw}) | "
            f"Desc={desc_safe[:40]}"
        )

    if len(txns) > 10:
        print(f"     ... ({len(txns) - 10} more)")

    # Sanity checks
    print("\n===== SANITY CHECKS =====")
    bugs = 0

    # 1. reference should not equal date
    ref_eq_date = sum(1 for t in txns if t.get("reference") == t.get("date") and t.get("reference"))
    if ref_eq_date:
        print(f"❌  {ref_eq_date} transactions have reference == date (BUG)")
        bugs += 1
    else:
        print("✅  reference != date for all transactions")

    # 2. descriptions should not be identical for every row
    descs = [t.get("description", "") for t in txns]
    unique_descs = len(set(descs))
    if txns and unique_descs == 1:
        print(f"❌  All descriptions are identical: {repr(descs[0][:60])} (BUG)")
        bugs += 1
    else:
        print(f"✅  Unique descriptions: {unique_descs} / {len(txns)}")

    # 3. account name should not contain "Date" keyword
    acct = meta.get("account_name", "")
    if "Date" in acct or " date " in acct.lower():
        print(f"❌  account_name contains date garbage: {repr(acct)} (BUG)")
        bugs += 1
    else:
        print(f"✅  account_name clean: {repr(acct)}")

    print()
    if bugs == 0:
        print("ALL CHECKS PASSED ✅")
    else:
        print(f"{bugs} CHECK(S) FAILED ❌")
    return bugs


if __name__ == "__main__":
    sys.exit(main())
