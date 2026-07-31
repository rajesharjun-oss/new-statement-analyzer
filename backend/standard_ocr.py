import os
import re
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict

from gemini_client import generate_gemini_text

# Load .env from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Global index for rotation
_current_key_index = 0

def _get_gemini_keys() -> List[str]:
    raw_keys = os.getenv("GEMINI_API_KEY", "")
    return [k.strip() for k in raw_keys.split(",") if k.strip()]

def _is_quota_or_rate_limit_error(err: Exception) -> bool:
    msg = str(err).lower()
    return (
        "429" in msg
        or "resource exhausted" in msg
        or "rate limit" in msg
        or "quota" in msg
        or "overloaded" in msg
    )

def pdf_to_images(pdf_path: str, dpi: int = 150, max_pages: int = 20) -> List:
    """Convert PDF pages to PIL Images using PyMuPDF (fitz), with a strict limit."""
    import fitz
    from PIL import Image
    import io
    
    images = []
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        limit = min(total_pages, max_pages)
        
        for page_num in range(limit):
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
    keys = _get_gemini_keys()
    if not keys: return ""
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(image_bytes))

    for attempt in range(len(keys)):
        api_key = keys[_current_key_index % len(keys)]
        _current_key_index += 1
        try:
            return generate_gemini_text(
                api_key,
                "gemini-2.0-flash",
                ["Perform OCR on this bank statement page.", img],
            )
        except Exception as e:
            if _is_quota_or_rate_limit_error(e):
                print("DEBUG: Gemini OCR key quota/rate limited. Trying next key...")
                continue
            print(f"DEBUG: Gemini OCR failed on key {attempt+1}/{len(keys)}: {e}")
            continue
    return ""

def extract_scanned_statement(pdf_path: str, bank_identifier: str = "generic", max_pages: int = 20) -> List[Dict]:
    """
    Overhauled 2-Phase OCR Pipeline:
    Phase 1: High-DPI Rendering -> Vision Transcriber (Literal Grid Extraction)
    Phase 2: Text Engineer -> PSV Formatter (Cleaning & Validation)
    """
    global _current_key_index
    
    keys = _get_gemini_keys()
    if not keys:
         print("DEBUG: Gemini AI Extraction Failed - No Keys")
         return []

    # Render once to avoid repeated heavy PDF rasterization on key retries.
    images = pdf_to_images(pdf_path, dpi=150, max_pages=max_pages)
    if not images:
        return []

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

    for attempt in range(len(keys)):
        api_key = keys[_current_key_index % len(keys)]
        _current_key_index += 1

        try:
            print(f"DEBUG: Gemini Vision - Executing OCR on {len(images)} pages...")
            payload_phase1 = [prompt_extractor] + images
            raw_psv_text = generate_gemini_text(
                api_key,
                "gemini-2.0-flash",
                payload_phase1,
                max_output_tokens=8192,
            )

            if not raw_psv_text:
                print("DEBUG: Gemini Vision - Phase 1 received empty response. Trying next key...")
                continue

            raw_psv_text = re.sub(r'^```(csv|psv|text)?\s*', '', raw_psv_text, flags=re.I)
            raw_psv_text = re.sub(r'```$', '', raw_psv_text, flags=re.I)

            debug_psv_path = Path(pdf_path).with_suffix('.phase1.raw.psv')
            with open(debug_psv_path, 'w', encoding='utf-8') as f:
                f.write(raw_psv_text)

            standard_txns = []

            def safe_float(val):
                if not val or str(val).isspace():
                    return 0.0
                try:
                    s = str(val).replace(',', '').strip()
                    s = re.sub(r'[^\d\.\-]', '', s)
                    if not s or s == '-' or s == '.':
                        return 0.0
                    parsed = float(s)
                    if abs(parsed) > 10000000000.0:  # 10 Billion cap
                        print(f"DEBUG: Rejected hallucinated massive float: {parsed}")
                        return 0.0
                    return parsed
                except Exception:
                    return 0.0

            for line in raw_psv_text.split('\n'):
                if not line.strip():
                    continue
                parts = line.split('|')

                if len(parts) >= 6:
                    date_val = str(parts[0]).strip()
                    val_date = str(parts[1]).strip()
                    desc_val = str(parts[2]).strip()
                    deb_val = safe_float(parts[3])
                    cred_val = safe_float(parts[4])
                    bal_val = safe_float(parts[5])
                elif len(parts) == 5:
                    date_val = str(parts[0]).strip()
                    val_date = ""
                    desc_val = str(parts[1]).strip()
                    deb_val = safe_float(parts[2])
                    cred_val = safe_float(parts[3])
                    bal_val = safe_float(parts[4])
                else:
                    continue

                desc_upper = desc_val.upper()
                if 'DATE' in date_val.upper() or 'DESCRIPTION' in desc_upper:
                    continue
                if any(kw in desc_upper for kw in ['TOTAL', 'SUM', 'BROUGHT FORWARD', 'CARRIED FORWARD', 'BALANCE B/F', 'BALANCE C/F', 'OPENING BALANCE', 'CLOSING BALANCE', 'PAGE TOTAL']):
                    continue

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

            def auto_correct_columns(txns):
                valid_anchors = []
                for i, t in enumerate(txns):
                    if t['balance'] != 0.0:
                        valid_anchors.append(i)

                if len(valid_anchors) < 2:
                    return txns

                for anchor_idx in range(len(valid_anchors) - 1):
                    start = valid_anchors[anchor_idx]
                    end = valid_anchors[anchor_idx + 1]
                    start_bal = txns[start]['balance']
                    end_bal = txns[end]['balance']
                    expected_diff = round(end_bal - start_bal, 2)

                    actual_diff = 0.0
                    for i in range(start + 1, end + 1):
                        actual_diff += txns[i]['credit'] - txns[i]['debit']
                    actual_diff = round(actual_diff, 2)

                    if expected_diff != actual_diff:
                        deficit = round(expected_diff - actual_diff, 2)

                        for i in range(start + 1, end + 1):
                            t = txns[i]
                            if t['debit'] > 0 and round(t['debit'] * 2, 2) == deficit:
                                t['credit'] = t['debit']
                                t['debit'] = 0.0
                                print(f"DEBUG: Auto-corrected hallucinated DEBIT -> CREDIT for {t['credit']}")
                                break
                            if t['credit'] > 0 and round(t['credit'] * -2, 2) == deficit:
                                t['debit'] = t['credit']
                                t['credit'] = 0.0
                                print(f"DEBUG: Auto-corrected hallucinated CREDIT -> DEBIT for {t['debit']}")
                                break

                return txns

            standard_txns = auto_correct_columns(standard_txns)
            print(f"DEBUG: Successfully parsed {len(standard_txns)} transactions.")
            return standard_txns

        except Exception as e:
            if _is_quota_or_rate_limit_error(e):
                print("DEBUG: Gemini Vision key quota/rate limited. Trying next key...")
                continue
            print(f"DEBUG: Gemini Vision extraction failed on key {attempt + 1}/{len(keys)}: {e}")
            continue

    print("DEBUG: Gemini Vision extraction exhausted all configured keys.")
    return []

# Aliases for backward compatibility with pdf_extractor.py and other modules
extract_transactions_via_ai = extract_scanned_statement


def gemini_ocr_to_text(pdf_path: str, max_pages: int = 20) -> str:
    """
    Stage 1 of 2-stage pipeline: pure OCR only.
    Converts each PDF page to a high-DPI image and asks Gemini Vision to
    transcribe the text literally (no PSV formatting, no extraction).
    Returns a concatenated plain-text string with PAGE markers.
    """
    global _current_key_index
    keys = _get_gemini_keys()
    if not keys:
        print("DEBUG [gemini_ocr_to_text]: No GEMINI_API_KEY configured.")
        return ""

    images = pdf_to_images(pdf_path, dpi=200, max_pages=max_pages)
    if not images:
        print("DEBUG [gemini_ocr_to_text]: pdf_to_images returned no images.")
        return ""

    ocr_prompt = (
        "You are a high-precision OCR engine processing bank statement pages. "
        "For each page image provided, transcribe ALL text exactly as printed. "
        "Preserve relative column spacing using spaces. "
        "Reproduce every number exactly (all digits, commas, decimal points). "
        "Before each page's content output a marker line: === PAGE N === "
        "(where N is the page number starting from 1). "
        "Do NOT reformat, summarise, or skip any row. Output only raw transcribed text."
    )

    for attempt in range(len(keys)):
        api_key = keys[_current_key_index % len(keys)]
        _current_key_index += 1
        payload = [ocr_prompt] + images
        try:
            combined = generate_gemini_text(
                api_key,
                "gemini-2.0-flash",
                payload,
                max_output_tokens=8192,
            )
            if combined:
                print(f"DEBUG [gemini_ocr_to_text]: Batch OCR complete - {len(combined)} chars from {len(images)} pages.")
                return combined
            print("DEBUG [gemini_ocr_to_text]: Batch OCR returned empty text. Trying next key...")
            continue
        except Exception as e:
            if _is_quota_or_rate_limit_error(e):
                print("DEBUG [gemini_ocr_to_text]: Batch OCR quota/rate limited. Trying next key...")
                continue
            print(f"DEBUG [gemini_ocr_to_text]: Batch OCR failed ({e}). Falling back to per-page mode...")

        all_parts = []
        hard_fail = False
        for page_num, img in enumerate(images, 1):
            try:
                page_text = generate_gemini_text(
                    api_key,
                    "gemini-2.0-flash",
                    [ocr_prompt, img],
                    max_output_tokens=4096,
                )
                all_parts.append(f"=== PAGE {page_num} ===\n{page_text}")
                print(f"DEBUG [gemini_ocr_to_text]: Page {page_num} OCR'd ({len(page_text)} chars)")
            except Exception as e2:
                if _is_quota_or_rate_limit_error(e2):
                    print("DEBUG [gemini_ocr_to_text]: Per-page OCR quota/rate limited. Trying next key...")
                    hard_fail = True
                    break
                print(f"DEBUG [gemini_ocr_to_text]: Page {page_num} failed: {e2}")
                all_parts.append(f"=== PAGE {page_num} ===\n[OCR FAILED]")

        if hard_fail:
            continue

        combined = "\n\n".join(all_parts)
        print(f"DEBUG [gemini_ocr_to_text]: Per-page OCR done - {len(combined)} chars across {len(images)} pages.")
        return combined

    print("DEBUG [gemini_ocr_to_text]: Exhausted all configured Gemini keys.")
    return ""
