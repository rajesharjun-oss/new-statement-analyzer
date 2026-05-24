#!/usr/bin/env python3
"""Per-bank chain integrity check across all PDFs in temp_uploads."""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))
from pdf_extractor import extract_transactions
import pdfplumber

def _f(val):
    if val is None: return 0.0
    if isinstance(val, (int, float)): return float(val)
    cleaned = re.sub(r'[^\d.\-]', '', str(val))
    try: return float(cleaned) if cleaned else 0.0
    except: return 0.0

def chain_check(txns):
    errors = 0
    prev_b = None
    for t in txns:
        b, d, c = _f(t.get('balance')), _f(t.get('debit')), _f(t.get('credit'))
        if prev_b is not None and b != 0:
            expected = round(prev_b - d + c, 2)
            if abs(expected - b) > 0.015:
                errors += 1
        if b != 0:
            prev_b = b
    return errors

def detect_bank(path):
    try:
        with pdfplumber.open(path) as pdf:
            txt = (pdf.pages[0].extract_text() or '')[:500].lower()
    except:
        return 'unknown'
    for b in ['gtbank','fidelity','zenith','access bank','uba','ecobank',
              'first bank','firstbank','providus','wema','fcmb','sterling','stanbic']:
        if b in txt:
            return b.replace(' ', '')
    return 'unknown'

def main():
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'temp_uploads')
    rows = []
    for fn in sorted(os.listdir(upload_dir)):
        if not fn.endswith('.pdf'):
            continue
        path = os.path.join(upload_dir, fn)
        uid = fn[:8]
        bank = detect_bank(path)
        try:
            result = extract_transactions(path)
            txns = result[0]['transactions'] if result and isinstance(result[0], dict) else []
            if not txns:
                rows.append(('SKIP ', bank, uid, 0, 0))
                continue
            errs = chain_check(txns)
            rows.append(('OK  ' if errs == 0 else f'ERR:{errs}', bank, uid, len(txns), errs))
        except Exception as e:
            rows.append((f'CRASH', bank, uid, 0, 0))

    rows.sort(key=lambda r: (r[0] != 'OK  ', r[1], r[2]))
    for status, bank, uid, ntxns, nerrs in rows:
        if status == 'SKIP ':
            print(f"SKIP  {bank:12s} {uid}")
        elif status == 'CRASH':
            print(f"CRASH {bank:12s} {uid}")
        else:
            print(f"{status} {bank:12s} {uid} ({ntxns} txns)")

    ok = sum(1 for r in rows if r[0] == 'OK  ')
    fail = sum(1 for r in rows if r[0] not in ('OK  ', 'SKIP ', 'CRASH'))
    skip = sum(1 for r in rows if r[0] == 'SKIP ')
    crash = sum(1 for r in rows if r[0] == 'CRASH')
    print(f"\nSUMMARY: {ok} OK, {fail} FAIL, {skip} SKIP, {crash} CRASH")

if __name__ == '__main__':
    main()
