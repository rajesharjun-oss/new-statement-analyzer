import google.generativeai as genai
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from typing import Optional

# Global index for rotation
_current_key_index = 0

def extract_text_with_gemini_vision(image_bytes: bytes) -> str:
    """
    Perform OCR on bank statement image bytes using Google Gemini API.
    Supports rotation of multiple API keys provided as comma-separated list.
    """
    global _current_key_index
    
    raw_keys = os.getenv("GEMINI_API_KEY", "")
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    
    if not keys:
        print("DEBUG: No Gemini API keys found in environment.")
        return ""

    # Pick the current key
    api_key = keys[_current_key_index % len(keys)]
    _current_key_index += 1
    
    print(f"DEBUG: Using Gemini API Key (Index {_current_key_index % len(keys)})")

    try:
        genai.configure(api_key=api_key)
        
        # Use gemini-2.0-flash for state-of-the-art OCR
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Construct the prompt
        prompt = (
            "Perform high-quality OCR on this bank statement page. "
            "Extract all text while preserving the spatial relationship of the columns as much as possible. "
            "Group related fields (Date, Description, Debit, Credit, Balance) together in a clean row-based text format."
        )
        
        # PREVENT WINDOWS CRASH: Use PIL.Image instead of raw bytes dict
        from PIL import Image
        import io
        image_parts = [
            Image.open(io.BytesIO(image_bytes))
        ]
        
        response = model.generate_content([prompt, image_parts[0]])
        
        if not response.text:
             print("DEBUG: Gemini OCR returned empty text.")
             return ""
             
        return response.text
        
    except Exception as e:
        print(f"DEBUG: Gemini OCR failed with current key: {e}")
        # Could potentially retry with next key here, but keeping it simple for now
        return ""

def _clean_ai_json(text: str) -> str:
    """
    Robust JSON cleaning: strips Markdown code blocks and leading/trailing whitespace.
    """
    # Remove markdown code blocks if present
    text = re.sub(r'```json\s*', '', text, flags=re.I)
    text = re.sub(r'```\s*', '', text, flags=re.I)
    return text.strip()

def extract_transactions_via_ai(pdf_path: str, max_pages: int = 10, bank_identifier: str = "") -> list:
    """
    Multimodal High-Precision Extraction: Renders PDF pages to images and uses 
    Gemini 1.5 Flash to extract a strict CSV table.
    """
    from ocr_helper import render_page_to_bytes
    import pandas as pd
    import io
    import re
    
    global _current_key_index
    
    raw_keys = os.getenv("GEMINI_API_KEY", "")
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not keys:
         print("DEBUG: Gemini AI Extraction Failed - No Keys")
         return []

    api_key = keys[_current_key_index % len(keys)]
    _current_key_index += 1
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # User's strict workflow prompt
        prompt = (
            "Extract the transaction table from this bank statement into a structured CSV format. \n"
            "Output headers: DATE, DESCRIPTION, DEBIT, CREDIT, BALANCE. \n"
            "Rules:\n"
            "1. Format amount values strictly as numbers (e.g. 1000.50, not 1,000.50).\n"
            "2. If a value is missing or zero, use 0.00.\n"
            "3. Ensure the description is complete and captures all relevant narration details.\n"
            "4. Return ONLY the raw CSV text without any markdown markers or extra text."
        )
        
        # Render pages to images
        image_parts = []
        for i in range(max_pages):
            img_bytes = render_page_to_bytes(pdf_path, i, zoom=3.0) # Higher zoom for better OCR
            if not img_bytes:
                break
            # FIX FOR WINDOWS: Avoid passing raw dicts with large bytes, use PIL.Image directly
            # to prevent STATUS_STACK_OVERFLOW in protobuf C extensions
            from PIL import Image
            import io
            image_parts.append(Image.open(io.BytesIO(img_bytes)))
            
        print(f"DEBUG: Gemini Vision - Rendered {len(image_parts)} pages for {bank_identifier}")
        if not image_parts:
            return []

        # Combine prompt and images
        payload = [prompt] + image_parts
        response = model.generate_content(payload)
        
        if not response.text:
            print("DEBUG: Gemini Vision - Received empty response")
            return []
            
        # Step 2: Save raw CSV output (cleaning markdown if present)
        raw_csv = response.text.strip()
        raw_csv = re.sub(r'^```(csv|json)\s*', '', raw_csv, flags=re.I)
        raw_csv = re.sub(r'```$', '', raw_csv, flags=re.I)
        
        # Log raw result for debugging
        debug_csv_path = Path(pdf_path).with_suffix('.raw.csv')
        with open(debug_csv_path, 'w', encoding='utf-8') as f:
            f.write(raw_csv)
            
        # Step 3: Use pandas to read the CSV and convert to standard format
        try:
            # error_bad_lines=False / on_bad_lines='skip' is used to drop rows with too many/few columns
            df = pd.read_csv(io.StringIO(raw_csv), on_bad_lines='skip')
            # Normalize column names to lowercase
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            def safe_float(val):
                if pd.isnull(val): return 0.0
                try:
                    # Remove all non-numeric characters except . and -
                    s = str(val).replace(',', '').strip()
                    s = re.sub(r'[^\d\.\-]', '', s)
                    if not s or s == '-' or s == '.': return 0.0
                    return float(s)
                except ValueError:
                    return 0.0

            # Map columns to our standard schema
            standard_txns = []
            for _, row in df.iterrows():
                try:
                    standard_txns.append({
                        'date': str(row.get('date', '')).strip(),
                        'description': str(row.get('description', '')).strip(),
                        'debit': safe_float(row.get('debit', 0)),
                        'credit': safe_float(row.get('credit', 0)),
                        'balance': safe_float(row.get('balance', 0)),
                        'reference': '',
                        'remarks': str(row.get('description', '')).strip(),
                        'category': 'Uncategorized'
                    })
                except Exception as row_e:
                    print(f"DEBUG: Skipping malformed AI row: {row_e}")
                    continue
            return standard_txns
            
        except Exception as pe:
            print(f"DEBUG: CSV Parse failed: {pe}")
            return []

    except Exception as e:
        print(f"DEBUG: Gemini Vision Extraction failed: {e}")
        return []
