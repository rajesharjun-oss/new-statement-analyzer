import sys
from pathlib import Path

# Add backend to path so we can import modules
sys.path.append(str(Path(__file__).parent))

from access_engine import extract_access_via_coordinates

pdf_path = Path("temp_uploads/Access bank test.pdf")
print(f"Testing {pdf_path}")

txns, meta = extract_access_via_coordinates(pdf_path, {})
print(f"Extracted {len(txns)} transactions")
if txns:
    for t in txns[:3]:
        print(t)
