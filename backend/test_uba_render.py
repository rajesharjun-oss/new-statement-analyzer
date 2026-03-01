import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
from ocr_helper import render_page_to_bytes
import os

def test_render(pdf_path, output_path):
    print(f"Rendering {pdf_path}...")
    img_bytes = render_page_to_bytes(pdf_path, 0, zoom=2.0)
    if img_bytes:
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        print(f"Saved to {output_path}")
    else:
        print("Failed to render")

test_render("temp_uploads/UBA test.pdf", "uba_p0.png")
