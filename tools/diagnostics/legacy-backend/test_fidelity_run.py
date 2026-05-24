from pdf_extractor import extract_fidelity_via_tables
import glob
import os
from pathlib import Path

if __name__ == "__main__":
    pdf_path = Path("FIDELITY 1 2024.pdf")
    print("Testing Fidelity extraction on", pdf_path)
    txns = extract_fidelity_via_tables(pdf_path, {})
    with open("test_out_utf8.txt", "w", encoding="utf-8") as f:
        f.write(f"Extracted {len(txns)} transactions.\n")
        
        # Only dump first 50 transactions to find SMS Alert Charges
        for t in txns[:50]:
            f.write(str(t) + "\n")
