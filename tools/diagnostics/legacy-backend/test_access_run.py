from pathlib import Path
import sys

pdf_path = Path("temp_uploads/Access bank test.pdf")
print(f"Testing Access Bank extraction on: {pdf_path}")

# 1. Try the dedicated access_engine
try:
    from access_engine import extract_access_via_coordinates
    txns, meta = extract_access_via_coordinates(pdf_path, {})
    print(f"access_engine returned {len(txns)} transactions")
    if txns:
        for t in txns[:5]:
            print(t)
except Exception as e:
    print(f"access_engine CRASHED: {e}")
    import traceback
    traceback.print_exc()

# 2. Try detect_access_columns on page 1 words
print("\n--- Testing detect_access_columns ---")
try:
    import pdfplumber
    from pdf_extractor import detect_access_columns
    with pdfplumber.open(pdf_path) as pdf:
        words = pdf.pages[0].extract_words()
        cuts = detect_access_columns(words, "accessbank")
        print(f"detect_access_columns returned: {cuts}")
except Exception as e:
    print(f"detect_access_columns CRASHED: {e}")
    import traceback
    traceback.print_exc()

# 3. Try extract_access_via_tables
print("\n--- Testing extract_access_via_tables ---")
try:
    from pdf_extractor import extract_access_via_tables
    txns2, meta2 = extract_access_via_tables(pdf_path, {})
    print(f"extract_access_via_tables returned {len(txns2)} transactions")
    if txns2:
        for t in txns2[:5]:
            print(t)
except Exception as e:
    print(f"extract_access_via_tables CRASHED: {e}")
    import traceback
    traceback.print_exc()

# 4. Try extract_access_consensus
print("\n--- Testing extract_access_consensus ---")
try:
    from pdf_extractor import extract_access_consensus
    txns3, meta3 = extract_access_consensus(pdf_path, {})
    print(f"extract_access_consensus returned {len(txns3)} transactions")
    if txns3:
        for t in txns3[:5]:
            print(t)
except Exception as e:
    print(f"extract_access_consensus CRASHED: {e}")
    import traceback
    traceback.print_exc()
