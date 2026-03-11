import google.generativeai as genai
import os
import re
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict

# Load .env from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Global index for rotation
_current_key_index = 0

def pdf_to_images(pdf_path: str, dpi: int = 300) -> List:
    """Convert PDF pages to PIL Images using PyMuPDF (fitz)"""
    import fitz
    from PIL import Image
    import io
    
    images = []
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            zoom = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            images.append(img)
        doc.close()
    except Exception as e:
        print(f"DEBUG: pdf_to_images failed: {e}")
    return images

def extract_text_with_gemini_vision(image_bytes: bytes) -> str:
    """Legacy single-page OCR (kept for compatibility)"""
    global _current_key_index
    raw_keys = os.getenv("GEMINI_API_KEY", "")
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not keys: return ""
    api_key = keys[_current_key_index % len(keys)]
    _current_key_index += 1
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        response = model.generate_content(["Perform OCR on this bank statement page.", img])
        return response.text if response else ""
    except:
        return ""

def extract_scanned_statement(pdf_path: str, bank_identifier: str = "generic") -> List[Dict]:
    """
    Overhauled 2-Phase OCR Pipeline:
    Phase 1: High-DPI Rendering -> Vision Transcriber (Literal Grid Extraction)
    Phase 2: Text Engineer -> PSV Formatter (Cleaning & Validation)
    """
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
        
        # Phase 1: Convert PDF to high-quality images (300 DPI for watermark-heavy PDFs)
        images = pdf_to_images(pdf_path, dpi=300)
        if not images:
            return []
            
        # Limit to 15 pages for speed/token safety
        if len(images) > 15:
            print(f"DEBUG: PDF has {len(images)} pages. Processing first 15.")
            images = images[:15]
            
        prompt_extractor = (
            "Role: You are a high-precision Financial OCR Engine.\n"
            "Task: Literal transcription of the bank statement grid into raw CSV format.\n"
            "Directives:\n"
            "1. NO ANALYSIS: Extract exactly what is printed. Do not calculate totals.\n"
            "2. WATERMARK AWARE: Ignore semi-transparent background logos (e.g. 'SAMSUNG' or bank logos).\n"
            "3. NUMERIC PRECISION: Transcribe all digits and separators exactly. Watch for 1000s commas vs decimals.\n"
            "4. ALIGNMENT: Keep DEBITS, CREDITS, and BALANCE strictly separate. Reconstruct the grid row by row.\n"
            "5. Headers: Use exactly: DATE, DESCRIPTION, DEBIT, CREDIT, BALANCE.\n"
            "Output Format: Return ONLY raw CSV code in a single markdown block."
        )

        print(f"DEBUG: Gemini Vision - Executing Phase 1 (Extractor) on {len(images)} pages...")
        payload_phase1 = [prompt_extractor] + images
        response_phase1 = model.generate_content(
            payload_phase1,
            generation_config=genai.types.GenerationConfig(max_output_tokens=8192)
        )
        
        if not response_phase1 or not response_phase1.text:
            print("DEBUG: Gemini Vision - Phase 1 Received empty response")
            return []

        raw_csv_phase1 = response_phase1.text.strip()
        raw_csv_phase1 = re.sub(r'^```(csv|text)?\s*', '', raw_csv_phase1, flags=re.I)
        raw_csv_phase1 = re.sub(r'```$', '', raw_csv_phase1, flags=re.I)
        
        # Log Phase 1 for debugging
        debug_csv_path = Path(pdf_path).with_suffix('.phase1.raw.csv')
        with open(debug_csv_path, 'w', encoding='utf-8') as f:
            f.write(raw_csv_phase1)

        # PHASE 2: The Data Engineer (Text -> Cleaned PSV)
        prompt_engineer = (
            "Role: You are a financial data engineer processing messy OCR output.\n"
            "Task: Clean, validate, and structure the raw CSV data into a pristine Pipe-Separated Values (PSV) format.\n"
            "Directives:\n"
            "1. Numeric Cleaning: Remove currency symbols and formatting. Convert to raw floats (e.g. 100.50). Handle empty values as 0.00.\n"
            "2. Validation (CRITICAL): Cross-reference the BALANCE column. For each row: (Previous Balance - Debit + Credit) should match (Current Balance). If the OCR misread a number but the balance progression is clear, use the balance math to correct the amount.\n"
            "3. Multiline Descriptions: Merge multi-line descriptions into a single string.\n"
            "4. Account Splits: If you see a 'BALANCE BROUGHT FORWARD' or a currency change mid-stream, keep it as a separator row.\n"
            "Format: Return ONLY raw PSV text (no headers, no markdown): DATE|DESCRIPTION|DEBIT|CREDIT|BALANCE"
        )
        
        print("DEBUG: Gemini Vision - Executing Phase 2 (Data Engineer)...")
        payload_phase2 = f"{prompt_engineer}\n\nRAW OCR DATA:\n{raw_csv_phase1}"
        response_phase2 = model.generate_content(
            payload_phase2,
            generation_config=genai.types.GenerationConfig(max_output_tokens=8192)
        )
        
        if not response_phase2 or not response_phase2.text:
            return []

        raw_psv_text = response_phase2.text.strip()
        raw_psv_text = re.sub(r'^```(csv|psv|text)?\s*', '', raw_psv_text, flags=re.I)
        raw_psv_text = re.sub(r'```$', '', raw_psv_text, flags=re.I)
        
        # Log Phase 2 for debugging
        debug_psv_path = Path(pdf_path).with_suffix('.phase2.raw.psv')
        with open(debug_psv_path, 'w', encoding='utf-8') as f:
            f.write(raw_psv_text)

        # Step 3: Parse PSV
        standard_txns = []
        def safe_float(val):
            if not val or str(val).isspace(): return 0.0
            try:
                s = str(val).replace(',', '').strip()
                s = re.sub(r'[^\d\.\-]', '', s)
                if not s or s == '-' or s == '.': return 0.0
                return float(s)
            except:
                return 0.0
                
        for line in raw_psv_text.split('\n'):
            if not line.strip(): continue
            parts = line.split('|')
            if len(parts) >= 5:
                # Skip headers
                if 'DATE' in parts[0].upper() or 'DESCRIPTION' in parts[1].upper(): continue
                standard_txns.append({
                    'date': str(parts[0]).strip(),
                    'description': str(parts[1]).strip(),
                    'debit': safe_float(parts[2]),
                    'credit': safe_float(parts[3]),
                    'balance': safe_float(parts[4]),
                    'reference': '',
                    'remarks': str(parts[1]).strip(),
                    'category': 'Uncategorized'
                })
        
        print(f"DEBUG: Successfully parsed {len(standard_txns)} transactions.")
        return standard_txns

    except Exception as e:
        print(f"DEBUG: Gemini Vision Extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return []

# Aliases for backward compatibility with pdf_extractor.py and other modules
extract_transactions_via_ai = extract_scanned_statement
