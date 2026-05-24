"""Standalone Wema engine test"""
import sys, time
sys.path.insert(0, 'backend')
from wema_engine import extract_wema_via_coordinates
from pathlib import Path

start = time.time()
path = Path('backend/temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf')
print(f"Testing: {path.name}")
txns, meta = extract_wema_via_coordinates(path, {})
elapsed = time.time() - start

d = sum(t['debit'] for t in txns)
c = sum(t['credit'] for t in txns)
print(f"\n=== RESULTS ===")
print(f"Transactions: {len(txns)}")
print(f"Total Debit:  {d:,.2f}")
print(f"Total Credit: {c:,.2f}")
print(f"Time: {elapsed:.1f}s")
print(f"Meta: {meta}")

print(f"\nFirst 3 transactions:")
for t in txns[:3]:
    print(f"  {t['date']} | {t['description'][:50]} | D={t['debit']:,.2f} C={t['credit']:,.2f} B={t['balance']:,.2f}")

print(f"\nLast 3 transactions:")
for t in txns[-3:]:
    print(f"  {t['date']} | {t['description'][:50]} | D={t['debit']:,.2f} C={t['credit']:,.2f} B={t['balance']:,.2f}")
