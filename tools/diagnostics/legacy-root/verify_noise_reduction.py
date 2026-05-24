import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

from pdf_extractor import scrub_boilerplate
from categorization import normalize_description, extract_entity_from_narration, categorize_single_transaction

def test_noise_reduction():
    samples = [
        "Please address all enquiries VATCHARGES Ikoyi.. P.O.Box 75455, Victoria Is",
        "Commission on NIP TransferCHARGES Please address all enquiries",
        "REGISTERED OFFICE: 123 Street Lagos RC 123456",
        "Member of the Nigeria Deposit Insurance Corporation NDIC www.gtbank.com",
        "638845457491835662-5 GAPS0493901874206959730S NIBSS Staff",
        "TRSF IFO SUNBETH GLOBAL LTD /LAGOS/NG",
        "TRANSPORT FOR JUNE 2025 GAPS0493901874207305400S 2073K CHRISTIAN05400 TO ACCESS - JOY ISE",
        "Please address all enquiries VATCHARGES Ikoyi.. P.O.Box 75455, Victoria Is"
    ]
    
    print("--- Testing PDF Extractor scrubbing (for Excel) ---")
    for s in samples:
        cleaned = scrub_boilerplate(s)
        print(f"Original: {s}")
        print(f"Scrubbed: {cleaned}")
        print("-" * 20)

    print("\n--- Testing Categorization (Final Category) ---")
    for s in samples:
        txn = {"description": s, "debit": "1000", "credit": "0"}
        categorize_single_transaction(txn)
        print(f"Original: {s}")
        print(f"Category: {txn.get('category')} (Source: {txn.get('decision_source')}, Rule: {txn.get('rule_id')})")
        print("-" * 20)

if __name__ == "__main__":
    test_noise_reduction()
