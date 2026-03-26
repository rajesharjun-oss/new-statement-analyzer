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
        # Using gemini-2.0-flash for speed/quota, heavily relying on Phase 2 strict 6-pipe PSV prompting
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
            "Task: Literal transcription of the bank statement grid into a pristine Pipe-Separated Values (PSV) format.\n"
            "Directives:\n"
            "1. NO ANALYSIS: Extract exactly what is printed. Do not attempt mathematical validation.\n"
            "2. WATERMARK AWARE: Ignore semi-transparent background logos.\n"
            "3. Numeric Format: Remove currency symbols and comma formatting. Convert to raw floats (e.g. 100.50). Handle empty values as 0.00.\n"
            "4. Descriptions: Merge multi-line descriptions into a single clean string. Do NOT drop the entire row if it wraps.\n"
            "5. Account Splits: If you see 'BALANCE BROUGHT FORWARD' or currency change, keep it as a separator row.\n"
            "6. CRITICAL ALIGNMENT: If the statement has a 'Reference' or 'Chq No' column, append its value to the DESCRIPTION. NEVER place reference numbers or account numbers into the DEBIT, CREDIT, or BALANCE fields!\n"
            "Format: Return ONLY raw PSV text (no headers, no markdown). You MUST return exactly 6 columns separated by 5 pipes: DATE|VALUE_DATE|DESCRIPTION|DEBIT|CREDIT|BALANCE. If VALUE_DATE is empty or missing, keep the pipe separators blank."
        )

        print(f"DEBUG: Gemini Vision - Executing OCR on {len(images)} pages...")
        payload_phase1 = [prompt_extractor] + images
        response_phase1 = model.generate_content(
            payload_phase1,
            generation_config=genai.types.GenerationConfig(max_output_tokens=8192)
        )
        
        if not response_phase1 or not response_phase1.text:
            print("DEBUG: Gemini Vision - Phase 1 Received empty response")
            return []

        raw_psv_text = response_phase1.text.strip()
        raw_psv_text = re.sub(r'^```(csv|psv|text)?\s*', '', raw_psv_text, flags=re.I)
        raw_psv_text = re.sub(r'```$', '', raw_psv_text, flags=re.I)
        
        # Log for debugging
        debug_psv_path = Path(pdf_path).with_suffix('.phase1.raw.psv')
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
                parsed = float(s)
                # Safety Clamp: Reject astronomically large floats (hallucinated references e.g. 1e15+)
                if abs(parsed) > 100000000000000.0:  # 100 Trillion cap
                    print(f"DEBUG: Rejected hallucinated massive float: {parsed}")
                    return 0.0
                return parsed
            except:
                return 0.0
                
        for line in raw_psv_text.split('\n'):
            if not line.strip(): continue
            parts = line.split('|')
            
            # Parse based on number of columns returned
            if len(parts) >= 6:
                # DATE|VALUE_DATE|DESCRIPTION|DEBIT|CREDIT|BALANCE
                date_val = str(parts[0]).strip()
                val_date = str(parts[1]).strip()
                desc_val = str(parts[2]).strip()
                deb_val = safe_float(parts[3])
                cred_val = safe_float(parts[4])
                bal_val = safe_float(parts[5])
            elif len(parts) == 5:
                # DATE|DESCRIPTION|DEBIT|CREDIT|BALANCE
                date_val = str(parts[0]).strip()
                val_date = ""
                desc_val = str(parts[1]).strip()
                deb_val = safe_float(parts[2])
                cred_val = safe_float(parts[3])
                bal_val = safe_float(parts[4])
            else:
                continue
                
            # Skip headers
            if 'DATE' in date_val.upper() or 'DESCRIPTION' in desc_val.upper(): continue
                
            standard_txns.append({
                'date': date_val,
                'value_date': val_date,
                'description': desc_val,
                'debit': deb_val,
                'credit': cred_val,
                'balance': bal_val,
                'reference': '',
                'remarks': desc_val,
                'category': 'Uncategorized'
            })
        # --- Mathematical Column Auto-Correction ---
        def auto_correct_columns(txns):
            # 1. Find blocks of transactions between valid anchor balances
            valid_anchors = []
            for i, t in enumerate(txns):
                if t['balance'] != 0.0:
                    valid_anchors.append(i)
                    
            if len(valid_anchors) < 2:
                return txns # Not enough anchors to fix anything
                
            for anchor_idx in range(len(valid_anchors) - 1):
                start = valid_anchors[anchor_idx]
                end = valid_anchors[anchor_idx + 1]
                
                # Check the block (inclusive of 'end' because 'end' txn contributed to its own balance!)
                # Wait, 'end' balance is the result AFTER 'end' debit/credit is applied.
                # So the block of transactions that caused the delta from start_balance to end_balance
                # is from (start + 1) to (end) inclusive!
                
                start_bal = txns[start]['balance']
                end_bal = txns[end]['balance']
                expected_diff = round(end_bal - start_bal, 2)
                
                actual_diff = 0.0
                for i in range(start + 1, end + 1):
                    actual_diff += txns[i]['credit'] - txns[i]['debit']
                actual_diff = round(actual_diff, 2)
                
                if expected_diff != actual_diff:
                    deficit = round(expected_diff - actual_diff, 2)
                    
                    # If deficit is perfectly 2 * X, then a transaction of value X was swapped!
                    # For example, expected = +10M, actual = -10M. Deficit = +20M. Value X = +10M.
                    # This means a 10M transaction was logged as Debit (-10M) but should be Credit (+10M).
                    
                    for i in range(start + 1, end + 1):
                        t = txns[i]
                        # Check if flipping this transaction specifically fixes the deficit exactly
                        # If it's a Debit, flipping it to Credit adds + 2 * Debit to the actual_diff
                        if t['debit'] > 0 and round(t['debit'] * 2, 2) == deficit:
                            t['credit'] = t['debit']
                            t['debit'] = 0.0
                            print(f"DEBUG: Auto-corrected hallucinated DEBIT -> CREDIT for {t['credit']}")
                            break
                        # If it's a Credit, flipping it to Debit subtracts 2 * Credit (adds - 2 * Credit)
                        elif t['credit'] > 0 and round(t['credit'] * -2, 2) == deficit:
                            t['debit'] = t['credit']
                            t['credit'] = 0.0
                            print(f"DEBUG: Auto-corrected hallucinated CREDIT -> DEBIT for {t['debit']}")
                            break
            
            return txns

        standard_txns = auto_correct_columns(standard_txns)
        
        print(f"DEBUG: Successfully parsed {len(standard_txns)} transactions.")
        return standard_txns

    except Exception as e:
        print(f"DEBUG: Gemini Vision Extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return []

# Aliases for backward compatibility with pdf_extractor.py and other modules
extract_transactions_via_ai = extract_scanned_statement
