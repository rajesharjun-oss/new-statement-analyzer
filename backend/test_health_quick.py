import os, sys
sys.path.insert(0, '.')
from pdf_extractor import extract_transactions

files = {
    "access":    ("temp_uploads/Access bank test.pdf", "access"),
    "uba":       ("temp_uploads/UBA test.pdf", "uba"),
    "wema":      ("temp_uploads/WEMA test.pdf", "wema"),
    "fcmb":      ("temp_uploads/FCMB test.pdf", "fcmb"),
    "zenith":    ("temp_uploads/Zenith bank test.pdf", "zenith"),
    "gtbank":    ("temp_uploads/OCT - DEC GTBs BANK STATEMENT PDF.pdf", "gtbank"),
    "providus":  ("temp_uploads/Adam Providus.pdf", "providus"),
    "sterling":  ("temp_uploads/STERLING test.pdf", "sterling"),
    "firstbank": ("temp_uploads/FBN - Dec25.pdf", "firstbank"),
}

lines = []
lines.append("=" * 90)
lines.append(f"{'BANK':>10} | STATUS | TXNS |     TOTAL DEBIT     |    TOTAL CREDIT")
lines.append("-" * 90)

for label, (path, bank) in files.items():
    if not os.path.exists(path):
        lines.append(f"{label.upper():>10} | SKIP   |    - | file not found")
        continue
    try:
        results = extract_transactions(path, bank_identifier=bank)
        if isinstance(results, list) and results and isinstance(results[0], dict):
            txns = results[0].get("transactions", [])
        elif isinstance(results, tuple):
            txns = results[0]
        else:
            txns = results
        
        total_dr = sum(float(str(t.get("debit",0)).replace(",","")) for t in txns)
        total_cr = sum(float(str(t.get("credit",0)).replace(",","")) for t in txns)
        status = "OK" if len(txns) > 0 else "BLANK!"
        lines.append(f"{label.upper():>10} | {status:>6} | {len(txns):>4} | {total_dr:>19,.2f} | {total_cr:>19,.2f}")
    except Exception as e:
        lines.append(f"{label.upper():>10} | ERROR  |    - | {str(e)[:50]}")

lines.append("=" * 90)

with open("health_results_utf8.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

# Also print
for l in lines:
    print(l)
