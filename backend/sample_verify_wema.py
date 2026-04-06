import sys
from pathlib import Path
import pdfplumber
from wema_engine import detect_wema_columns
from pdf_extractor import first_money

sys.path.append(str(Path(__file__).parent))

pdf_path = "temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf"
print(f"Sampling first 50 pages of {pdf_path} to verify fix...")

with pdfplumber.open(pdf_path) as pdf:
    # Use P0 to detect cuts
    words_p0 = pdf.pages[0].extract_words()
    cuts = detect_wema_columns(words_p0)
    
    total_debit = 0
    total_credit = 0
    txn_count = 0
    
    for i in range(min(50, len(pdf.pages))):
        page = pdf.pages[i]
        words = page.extract_words()
        
        # Re-detect if needed
        new_cuts = detect_wema_columns(words)
        if new_cuts: cuts = new_cuts
        
        col_list = [(name, bounds[0], bounds[1]) for name, bounds in cuts.items()]
        rows_dict = {}
        for w in words:
            y = round(w['top'] / 8) * 8
            if y not in rows_dict: rows_dict[y] = []
            rows_dict[y].append(w)
            
        for y in sorted(rows_dict.keys()):
            row_words = rows_dict[y]
            row_dict = {name: [] for name, _, _ in col_list}
            for w in sorted(row_words, key=lambda l: l['x0']):
                # Use TRUE CENTERING to match the engine fix
                mid = (w['x0'] + w['x1']) / 2
                for name, l, r in col_list:
                    if l <= mid < r:
                        row_dict[name].append(w['text'])
                        break
            
            # Joining text
            desc = " ".join(row_dict.get("description", [])).strip()
            row_text_upper = " ".join([" ".join(v) for v in row_dict.values()]).upper()
            
            # Apply our NEW filters
            summary_keywords = ["TOTAL", "CURRENT BAL", "PAYMENTS", "RECEIPTS", "BAL B/F", "BAL C/F", "BROUGHT FORWARD", "CARRIED FORWARD"]
            if any(sk in row_text_upper for sk in summary_keywords):
                continue
                
            deb_str = first_money(" ".join(row_dict.get("debit", [])))
            cred_str = first_money(" ".join(row_dict.get("credit", [])))
            
            debit = float(deb_str.replace(",", "")) if deb_str else 0.0
            credit = float(cred_str.replace(",", "")) if cred_str else 0.0
            
            if (debit > 100_000_000 or credit > 100_000_000) and not desc:
                continue
                
            if debit > 0 or credit > 0:
                total_debit += debit
                total_credit += credit
                txn_count += 1

    print(f"\nSample Result (50 Pages):")
    print(f"Total Debit: {total_debit:,.2f}")
    print(f"Total Credit: {total_credit:,.2f}")
    print(f"Transaction Count: {txn_count}")
    
    if total_debit < 10_000_000_000: # 10 Billion
        print("\nSUCCESS: No massive excess found in the first 50 pages.")
    else:
        print("\nFAILURE: Excessive amounts still present.")
