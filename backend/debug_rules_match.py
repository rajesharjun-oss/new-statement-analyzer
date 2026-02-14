import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from categorization import RULES, normalize_description

desc = "000013250628071514000251089068 638863826380583366-8 GAPS0493901874207935166S NIBSS Instant Payment Outward SECURITY 1 EXPENSE JUNE 2025D ALIYU 207935166 TO FBN - AHME ."
norm_desc = normalize_description(desc)

r008 = next((r for r in RULES if r.id == "R008_SECURITY_EXPENSES"), None)

if r008:
    match = r008.pattern.search(norm_desc)
    print(f"R008_MATCHED: {bool(match)}")
    if match:
        print(f"MATCH_TEXT: '{match.group(0)}'")
else:
    print("R008_NOT_FOUND")
