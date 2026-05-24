import fitz
import re

pdf_path = "temp_uploads/MOSES TRANSPORT LIMITED WEMA.pdf"
target = "36314344226334"
print(f"Searching for exactly {target}...")

doc = fitz.open(pdf_path)
found = False
for page_num in range(len(doc)):
    page = doc.load_page(page_num)
    text = page.get_text("text")
    # Remove all formatting to see if it exists as a sequence
    clean_text = re.sub(r'[^0-9]', '', text)
    if target in clean_text:
        print(f"FOUND sequence on Page {page_num + 1}!")
        print(text)
        found = True

if not found:
    print("Not found as a single sequence. Checking fragments...")
    f1 = "363143"
    f2 = "442263"
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        if f1 in text or f2 in text:
             print(f"Fragment found on Page {page_num+1}")
             # Print lines containing fragments
             for line in text.split('\n'):
                 if f1 in line or f2 in line:
                     print(f"  {line.strip()}")
