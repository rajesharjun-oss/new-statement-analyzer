from pdf_extractor import extract_transactions

txns, meta = extract_transactions('temp_uploads/WEMA test.pdf', 'wema')
print(f'Total Extracted: {len(txns)}')

prev_bal = meta.get('opening_balance') or 841829.64
gap_found = False

for i, t in enumerate(txns):
    b = t.get('balance', 0)
    d = t.get('debit', 0)
    c = t.get('credit', 0)
    
    # Check if this row is validly continuing the balance
    expected_bal = round(prev_bal - d + c, 2)
    if abs(expected_bal - b) > 1.0 and b != 0:
        print(f'GAP BEFORE index {i} (pg {t.get("_page", "?")}):')
        print(f'  Prev Balance: {prev_bal:,.2f}')
        print(f'  Current Row: D={d:,.2f}, C={c:,.2f}')
        print(f'  Expected Bal: {expected_bal:,.2f}')
        print(f'  Actual Bal:   {b:,.2f}')
        print(f'  Diff (Actual-Expected): {b - expected_bal:,.2f}')
        print(f'  Desc: {t.get("description", "")[:100]}...')
        print('-' * 40)
        gap_found = True
        
        # When a gap occurs, we resync prev_bal to the new actual balance
        prev_bal = b
    else:
        # Update prev_bal only if b seems valid
        if b != 0:
            prev_bal = b

if not gap_found:
    print('No math gaps found! The extracted transactions form a perfect running balance.')
