import base64
import os
import httpx
import json
import re
from typing import Dict, Any, List
from pathlib import Path
import fitz
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


def _safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = re.sub(r"[^\d.\-]", "", str(val))
    if not s or s in ("-", "."):
        return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def _pick(row: Dict[str, Any], names: List[str]) -> Any:
    lower_map = {str(k).strip().lower(): v for k, v in row.items()}
    for n in names:
        if n in lower_map:
            return lower_map[n]
    return ""


def _is_summary_row(desc_upper: str) -> bool:
    patterns = [
        r"\bPAGE\s+TOTAL\b",
        r"\bTOTAL\s+(DEBIT|CREDIT|WITHDRAWAL|DEPOSIT|CHARGES?)\b",
        r"^(TOTAL|GRAND\s+TOTAL)\b",
        r"\bBALANCE\s+(B/F|C/F|BROUGHT\s+FORWARD|CARRIED\s+FORWARD)\b",
        r"\bOPENING\s+BALANCE\b",
        r"\bCLOSING\s+BALANCE\b",
    ]
    return any(re.search(p, desc_upper) for p in patterns)


def extract_transactions_from_pdf_with_openai(pdf_path: str, max_pages: int = 15) -> List[Dict[str, Any]]:
    """
    Scanned-PDF fallback extraction using OpenAI Vision page-by-page.
    Returns standard transaction dicts.
    """
    out: List[Dict[str, Any]] = []
    p = Path(pdf_path)
    if not p.exists():
        return out

    try:
        doc = fitz.open(str(p))
    except Exception as e:
        print(f"DEBUG [openai_vision]: Cannot open PDF: {e}")
        return out

    page_limit = min(len(doc), max_pages)
    model_name = os.getenv("OPENAI_OCR_MODEL", "gpt-4o")

    prompt = (
        "Extract all bank transaction rows from this statement page. "
        "Return ONLY strict JSON object with key 'rows'. "
        "Each row object must have keys: date, value_date, description, debit, credit, balance. "
        "Use empty string for missing date/description and 0.00 for missing numeric fields. "
        "Do NOT include opening/closing balance summary lines or page totals."
    )

    for idx in range(page_limit):
        try:
            page = doc.load_page(idx)
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            image_bytes = pix.tobytes("png")
            client = get_openai_client()
            if not client:
                print("DEBUG [openai_vision]: No OpenAI client/key available.")
                break
            base64_image = encode_image(image_bytes)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                        ],
                    }
                ],
                temperature=0,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            parsed = json.loads(content)
            rows = parsed.get("rows", []) if isinstance(parsed, dict) else []
            if not isinstance(rows, list):
                rows = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                date_val = str(_pick(row, ["date", "tran date", "trans date", "transaction date", "date posted"])).strip()
                value_date = str(_pick(row, ["value_date", "value date"])).strip()
                desc_val = str(_pick(row, ["description", "narration", "details", "particulars", "remarks"])).strip()
                if not desc_val:
                    desc_val = str(_pick(row, ["reference", "ref", "chq no", "cheque no"])).strip()
                debit = _safe_float(_pick(row, ["debit", "withdrawal", "withdrawals", "dr"]))
                credit = _safe_float(_pick(row, ["credit", "deposit", "deposits", "cr"]))
                balance = _safe_float(_pick(row, ["balance", "running balance"]))
                desc_upper = desc_val.upper()
                if _is_summary_row(desc_upper):
                    continue
                if not date_val and not desc_val and debit == 0.0 and credit == 0.0 and balance == 0.0:
                    continue
                out.append(
                    {
                        "date": date_val,
                        "value_date": value_date,
                        "description": desc_val,
                        "debit": debit,
                        "credit": credit,
                        "balance": balance,
                        "reference": "",
                        "remarks": desc_val,
                        "category": "Uncategorized",
                    }
                )
            print(f"DEBUG [openai_vision]: Page {idx+1}/{page_limit} -> {len(rows)} raw rows")
        except Exception as e:
            print(f"DEBUG [openai_vision]: Page {idx+1} extraction failed: {e}")
            continue

    try:
        doc.close()
    except Exception:
        pass
    print(f"DEBUG [openai_vision]: Total fallback transactions: {len(out)}")
    return out
