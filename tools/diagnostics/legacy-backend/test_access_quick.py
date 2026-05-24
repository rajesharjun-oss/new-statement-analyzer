from pathlib import Path
from access_engine import extract_access_via_coordinates

txns, meta = extract_access_via_coordinates(Path("temp_uploads/Access bank test.pdf"), {})
print(f"{len(txns)} txns extracted")
for t in txns[:10]:
    print(f"date={t['date']:15s} debit={t['debit']:>12.2f} credit={t['credit']:>12.2f} bal={t['balance']:>15.2f} desc={t['description'][:50]}")
