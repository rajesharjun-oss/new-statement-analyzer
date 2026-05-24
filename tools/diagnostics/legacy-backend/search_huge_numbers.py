import fitz
import re

pdf_path = "temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf"

print("Searching for huge numbers in the PDF...")
doc = fitz.open(pdf_path)

# Regex to find numbers that look like thousands/billions
# e.g., 363,143,442,263.34 or 363143442263.34
# We'll look for strings of at least 10 digits
huge_num_re = re.compile(r'\d[\d,.]*\d')

for page_num in range(len(doc)):
    page = doc.load_page(page_num)
    text = page.get_text("text")
    matches = huge_num_re.findall(text)
    for m in matches:
        # Clean for float parsing
        clean_m = m.replace(',', '')
        try:
            val = float(clean_m)
            if val > 100000000.0: # Over 100 Million
                print(f"Page {page_num+1}: Potential huge number found: {m} (Parsed: {val:,.2f})")
                # Print context
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    if m in line:
                        print(f"  Context: {line.strip()}")
        except ValueError:
            continue

print("Search complete.")
