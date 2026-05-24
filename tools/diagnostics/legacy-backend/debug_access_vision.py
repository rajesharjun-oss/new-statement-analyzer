import os
import google.generativeai as genai
from pdfplumber import open as pdf_open
from PIL import Image
import io
from pathlib import Path

# Load API Key
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Error: No GEMINI_API_KEY found.")
    exit(1)

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash')

pdf_path = "backend/temp_uploads/Access2.0.pdf"
print(f"Analyzing {pdf_path} with Gemini Vision...")

try:
    import fitz
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    
    prompt = """
    Look at this bank statement page.
    1. Identify the bank name.
    2. Identify the column headers for the transactions table.
    3. For each header, give me its rough horizontal position (left to right) in the image.
    Return as JSON: {"bank": "...", "headers": [{"text": "...", "x": ...}]}
    """
    
    response = model.generate_content([prompt, img])
    print("\nGemini Response:")
    print(response.text)
    
except Exception as e:
    print(f"Vision analysis failed: {e}")
