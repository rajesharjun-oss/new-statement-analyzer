import pdfplumber
import os

pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\MOSES TRANSPORT LIMITED WEMA.pdf"

if not os.path.exists(pdf_path):
    print(f"ERROR: File not found at {pdf_path}")
else:
    with pdfplumber.open(pdf_path) as pdf:
        print(f"\n{'#'*60}")
        print(f"!!! FORENSIC AUDIT: {os.path.basename(pdf_path)} !!!")
        print(f"Total Pages: {len(pdf.pages)}")
        print(f"{'#'*60}\n")
        
        # Check Last Page for Summary
        last_page = pdf.pages[-1]
        print(f"--- AUDITING LAST PAGE ({len(pdf.pages)}) ---")
        raw_text = last_page.extract_text()
        print(f"\n[RAW-FOOTER-START]\n{raw_text[-2000:] if raw_text else 'EMPTY'}\n[RAW-FOOTER-END]\n")
        
        words = last_page.extract_words()
        
        # Print lines
        rows = {}
        for w in words:
            y = round(w['top'])
            if y not in rows: rows[y] = []
            rows[y].append(w)
            
        for y in sorted(rows.keys()):
            row_words = sorted(rows[y], key=lambda x: x['x0'])
            line_txt = " ".join([w['text'] for w in row_words])
                
                # Highlight summary keywords
                if any(kw in line_txt.upper() for kw in ["TOTAL DEBIT", "TOTAL CREDIT", "DEPOSITS", "WITHDRAWALS"]):
                    print(f"\n[SUMMARY-LINE] {line_txt}")
                    for w in row_words:
                        print(f"   - '{w['text']}' | BBox: (x0={w['x0']:.1f}, x1={w['x1']:.1f})")
        print(f"\n{'#'*60}")
