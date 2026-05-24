import pdfplumber
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from pdf_extractor import detect_fidelity_columns, clean_currency_str

pdf_path = 'backend/test_fidelity.pdf.pdf'
if not os.path.exists(pdf_path): pdf_path = 'test_fidelity.pdf.pdf'

with pdfplumber.open(pdf_path) as pdf:
    # Page 1 to find headers
    page1 = pdf.pages[0]
    words = page1.extract_words()
    cuts = detect_fidelity_columns(words, 'fidelity')
    
    if not cuts:
        print("Could not detect Fidelity columns from page 1")
        sys.exit(1)
        
    print(f"Detected cuts: {cuts}")
    
    # Convert cuts to explicit vertical lines
    # cuts is {name: (left, right)}
    v_lines = []
    sorted_cuts = sorted(cuts.items(), key=lambda x: x[1][0])
    for name, (left, right) in sorted_cuts:
        v_lines.append(left)
    # Add the last right boundary
    v_lines.append(sorted_cuts[-1][1][1])
    
    print(f"Using explicit vertical lines: {v_lines}")
    
    # Extract table with these lines
    tables = page1.extract_tables(table_settings={
        "vertical_strategy": "explicit",
        "explicit_vertical_lines": v_lines,
        "horizontal_strategy": "lines",
    })
    
    print(f"\nExtracted {len(tables)} tables with explicit lines")
    if tables:
        for row in tables[0][:10]:
            print(f"Row: {row}")
