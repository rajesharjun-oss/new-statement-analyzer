import sys
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).parent))

import pdfplumber
from wema_engine import detect_wema_columns
from pdf_extractor import parse_date_smart, first_money, is_noise_row

pdf_path = "temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf"

print(f"Deep Debug of Wema Extraction...")

with pdfplumber.open(pdf_path) as pdf:
    total_debit = 0
    
    # Let's check pages where we found fragments
    target_pages = [319, 1066, 1227, 1228, 1229, 1230, 1231, 1232, 1233, 1234, 1235, 1236, 1237, 1238]
    
    # Initialize cuts from P0
    words_p0 = pdf.pages[0].extract_words()
    cuts = detect_wema_columns(words_p0)
    
    for p_num in range(len(pdf.pages)):
        page = pdf.pages[p_num]
        words = page.extract_words()
        
        # Update cuts if headers found
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
            for w in sorted(row_words, key=lambda w: w['x0']):
                word_mid = w['x1'] - 5
                for name, min_x, max_x in col_list:
                    if min_x <= word_mid < max_x:
                        row_dict[name].append(w['text'])
                        break
            
            for name in row_dict:
                row_dict[name] = " ".join(row_dict[name]).strip()
            
            deb_raw = row_dict.get("debit", "")
            deb_str = first_money(deb_raw)
            if deb_str:
                d = float(deb_str.replace(",", ""))
                if d > 1000000: # We are looking for the big guys
                    print(f"Page {p_num+1} Row Y={y}: DEBIT={d:,.2f} | RAW_DEBIT='{deb_raw}' | DESC='{row_dict.get('description')}' | ID='{row_dict.get('tran_id')}'")
                total_debit += d

    print(f"\nFinal Calculated Total Debit: {total_debit:,.2f}")
