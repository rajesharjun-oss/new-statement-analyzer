"""
OpenAI Vision OCR for PDF page extraction fallback
"""
import os
import base64
from openai import OpenAI

import random

def get_api_key():
    keys = os.getenv("OPENAI_API_KEY", "").split(",")
    keys = [k.strip() for k in keys if k.strip()]
    return random.choice(keys) if keys else None

client = OpenAI(api_key=get_api_key())

def ocr_pdf_page_image(png_bytes: bytes) -> str:
    """
    OCR a single page image (PNG/JPG bytes) using OpenAI GPT-4 Vision.
    Returns plain text extracted from the image.
    
    Args:
        png_bytes: Image bytes (PNG or JPEG format)
    
    Returns:
        Extracted text from the image
    """
    # Convert image bytes to base64
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    
    # Call OpenAI Vision API
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Extract the bank statement table text exactly. "
                        "Preserve row order and column structure. "
                        "Include ALL transaction rows. "
                        "Output plain text only with columns clearly separated."
                    )
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64}"
                    }
                }
            ]
        }],
        max_tokens=4096
    )
    
    return response.choices[0].message.content


def extract_header_with_vision(png_bytes: bytes) -> str:
    """
    Extract only the table header from a bank statement page using OpenAI Vision.
    
    Args:
        png_bytes: Image bytes of the bank statement page
    
    Returns:
        Extracted column headers as plain text
    """
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Find and extract ONLY the transaction table column headers from this bank statement. "
                        "Look for headers like: Date, Transaction Date, Value Date, Description, "
                        "Narration, Reference, Debit, Credit, Withdrawals, Lodgements, Balance, etc. "
                        "Return only the column header names, separated by spaces."
                    )
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64}"
                    }
                }
            ]
        }],
        max_tokens=256
    )
    
    return response.choices[0].message.content
