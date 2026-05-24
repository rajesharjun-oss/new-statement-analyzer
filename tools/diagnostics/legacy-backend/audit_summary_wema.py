import pdfplumber
import os

pdf_path = r"c:\Users\ionawoga\Desktop\Statement-analyzer-3.0-1\backend\temp_uploads\MOSES TRANSPORT LIMITED WEMA.pdf"

print(f"\n{'#'*60}")
print(f"!!! ATOMIC BILLIONAIRE AUDIT: {os.path.basename(pdf_path)} !!!")

with pdfplumber.open(pdf_path) as pdf:
    print(f"Found {len(pdf.pages)} pages.")
    
    # Check First 10 and Last 10 pages for Billion-Naira keywords
    target_pages = list(range(0, 10)) + list(range(len(pdf.pages)-10, len(pdf.pages)))
    
    for i in target_pages:
        if i < 0 or i >= len(pdf.pages): continue
        text = pdf.pages[i].extract_text()
        if not text: continue
        
        lines = text.split('\n')
        for line in lines:
            # Look for 45,5... or keywords TOTAL DEBIT/CREDIT
            if "TOTAL" in line.upper() or "DEBIT" in line.upper() or "CREDIT" in line.upper() or "45," in line:
                # Print any line that looks like a billionaire total (contains at least 8-10 digits)
                digit_count = sum(c.isdigit() for c in line)
                if digit_count > 8:
                    print(f"\n[PAGE {i+1}] {line.strip()}")
print(f"\n{'#'*60}\n")
