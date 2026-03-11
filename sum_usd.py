
raw_psv = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\dff33eb4-a75b-480b-b678-1259c3b643fe.phase2.raw.psv"

total_debit = 0.0
total_credit = 0.0

with open(raw_psv, 'r') as f:
    for line in f:
        parts = line.strip().split('|')
        if len(parts) >= 5:
            try:
                total_debit += float(parts[2])
                total_credit += float(parts[3])
            except:
                pass

print(f"Computed Total Debit: {total_debit:,.2f}")
print(f"Computed Total Credit: {total_credit:,.2f}")
