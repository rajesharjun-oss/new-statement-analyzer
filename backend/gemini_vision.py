import google.generativeai as genai
import os
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
        
        # Use gemini-1.5-flash for speed and good OCR performance
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Construct the prompt
        prompt = (
            "Perform high-quality OCR on this bank statement page. "
            "Extract all text while preserving the spatial relationship of the columns as much as possible. "
            "Group related fields (Date, Description, Debit, Credit, Balance) together in a clean row-based text format."
        )
        
        # Prepare the image parts
        image_parts = [
            {
                "mime_type": "image/png",
                "data": image_bytes
            }
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

def extract_transactions_via_ai(pdf_path: str, max_pages: int = 5) -> list:
    """
    Multimodal Fallback: Renders PDF pages to images and uses Gemini 1.5 Flash 
     to extract structured JSON transactions directly.
    """
    from ocr_helper import render_page_to_bytes
    import json
    import re
    
    global _current_key_index
    
    raw_keys = os.getenv("GEMINI_API_KEY", "")
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not keys:
         print("DEBUG: Gemini AI Fallback Failed - No Keys")
         return []

    api_key = keys[_current_key_index % len(keys)]
    _current_key_index += 1
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Prepare multiline prompt
        prompt = (
            "Extract all financial transactions from these bank statement pages. "
            "Return ONLY a JSON array of objects with these exact keys: "
            "['date', 'description', 'debit', 'credit', 'balance', 'reference']. "
            "Ensure dates are in DD-MMM-YYYY format if possible. "
            "Numbers should be floats. If a value is missing, use null or 0.0. "
            "Do not include any conversational text or markdown formatting except for the JSON structure."
        )
        
        # Render pages to images
        image_parts = []
        for i in range(max_pages):
            img_bytes = render_page_to_bytes(pdf_path, i, zoom=2.5)
            if not img_bytes:
                break
            image_parts.append({
                "mime_type": "image/png",
                "data": img_bytes
            })
            
        print(f"DEBUG: Gemini Multimodal - Rendered {len(image_parts)} pages")
        if not image_parts:
            return []

        # Combine prompt and images
        payload = [prompt] + image_parts
        print(f"DEBUG: Gemini Multimodal - Sending payload to {model.model_name}...")
        response = model.generate_content(payload)
        
        if not response.text:
            print("DEBUG: Gemini Multimodal - Received empty response")
            return []
            
        # Robust Cleaning
        clean_json = _clean_ai_json(response.text)
        print(f"DEBUG: Gemini Multimodal - Clean AI Response Sample: {clean_json[:200]}...")
        
        try:
            return json.loads(clean_json)
        except Exception as je:
            print(f"DEBUG: AI JSON Parse failed: {je}")
            # Try to find JSON array manually
            match = re.search(r'\[\s*{.*}\s*\]', clean_json, re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except:
                    pass
            return []

    except Exception as e:
        print(f"DEBUG: Gemini Multimodal Fallback failed: {e}")
        return []
