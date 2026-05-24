import re

desc = "000013250628071514000251089068 638863826380583366-8 GAPS0493901874207935166S NIBSS Instant Payment Outward SECURITY 1 EXPENSE JUNE 2025D ALIYU 207935166 TO FBN - AHME ."
pattern = r"SECURITY\s*EXPENSE|SECURITY\b|POLICE|VIGILANTE|GUARD|ESCORT|SAFETY"

match = re.search(pattern, desc, re.IGNORECASE)

print(f"Desc: {desc}")
print(f"Pattern: {pattern}")
print(f"Match: {match}")

if match:
    print(f"Matched text: {match.group(0)}")
else:
    print("NO MATCH")
