import base64
import os
import httpx
from openai import OpenAI

_openai_key_index = 0

def get_openai_client():
    """Parse comma-separated keys and return a rotated client instance"""
    global _openai_key_index
    raw_keys = os.getenv('OPENAI_API_KEY', '')
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not keys:
        return None
    
    api_key = keys[_openai_key_index % len(keys)]
    _openai_key_index += 1
    return OpenAI(api_key=api_key, http_client=httpx.Client())

def encode_image(image_bytes):
    """Encode image bytes to base64 string"""
    return base64.b64encode(image_bytes).decode('utf-8')

def extract_header_with_vision(image_bytes):
    """
    Extract text/headers from an image using OpenAI Vision.
    """
    try:
        client = get_openai_client()
        if not client:
            print("DEBUG: No valid OpenAI API key found")
            return ""
        
        base64_image = encode_image(image_bytes)

        print("DEBUG: Sending image to OpenAI Vision...")
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract table data from this bank statement image. Return ONLY valid JSON with no markdown formatting. Structure: { \"header\": [col1, col2...], \"rows\": [ {col1: val1, col2: val2...} ] }. Use exact column names from the image where possible. If a value is missing or empty, use null or empty string."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=2000,
            temperature=0,
            response_format={ "type": "json_object" }
        )
        
        content = response.choices[0].message.content
        print(f"DEBUG: Vision returned {len(content)} chars")
        return content
        
    except Exception as e:
        print(f"DEBUG: OpenAI Vision Error: {e}")
        return ""
