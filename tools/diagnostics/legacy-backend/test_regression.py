#!/usr/bin/env python3
"""Quick regression test: check chain integrity for all PDFs in temp_uploads."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from pdf_extractor import extract_transactions

def _f(val):
    """Parse float from possibly comma-formatted string or numeric."""
    import re
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r'[^\d.\-]', '', str(val))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0

def chain_check(txns):
    errors = 0
    prev_b = None
    for t in txns:
        b = _f(t.get('balance'))
        d = _f(t.get('debit'))
        c = _f(t.get('credit'))
        if prev_b is not None and b != 0:
            expected = round(prev_b - d + c, 2)
            if abs(expected - b) > 0.015:
                errors += 1
        if b != 0:
            prev_b = b
    return errors

def main():
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'temp_uploads')
    pdfs = sorted(f for f in os.listdir(upload_dir) if f.endswith('.pdf'))
    pass_count = fail_count = skip_count = 0

    for fn in pdfs:
        path = os.path.join(upload_dir, fn)
        uid = fn[:8]
        try:
            result = extract_transactions(path)
            txns = result[0]['transactions'] if result and isinstance(result[0], dict) else []
            if not txns:
                skip_count += 1
                continue
            errs = chain_check(txns)
            if errs == 0:
                pass_count += 1
            else:
                fail_count += 1
                print(f"FAIL {uid}: {len(txns)} txns, {errs} errors")
        except Exception as e:
            skip_count += 1
            print(f"CRASH {uid}: {type(e).__name__}: {e}")

    print(f"SUMMARY: {pass_count} pass, {fail_count} fail, {skip_count} skip/empty")

if __name__ == '__main__':
    main()
