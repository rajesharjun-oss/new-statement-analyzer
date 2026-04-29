import base64
import os
import httpx
import json
import re
from typing import Dict, Any, List, Optional
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


def _dedupe_transactions(transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for t in transactions:
        key = (
            (t.get("date") or "").strip(),
            (t.get("value_date") or "").strip(),
            (t.get("description") or "").strip(),
            round(float(t.get("debit") or 0.0), 2),
            round(float(t.get("credit") or 0.0), 2),
            round(float(t.get("balance") or 0.0), 2),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _repair_debit_credit_by_balance_chain(transactions: List[Dict[str, Any]], tol: float = 1.0) -> List[Dict[str, Any]]:
    """
    Fix likely debit/credit swaps using running balance direction.
    """
    if len(transactions) < 2:
        return transactions

    swaps = 0
    amount_repairs = 0
    prev_balance = None
    for txn in transactions:
        bal = float(txn.get("balance") or 0.0)
        if prev_balance is None:
            if bal != 0.0:
                prev_balance = bal
            continue
        if bal == 0.0:
            continue

        delta = round(bal - prev_balance, 2)
        d = float(txn.get("debit") or 0.0)
        c = float(txn.get("credit") or 0.0)
        expected_amt = round(abs(delta), 2)
        if expected_amt <= tol:
            prev_balance = bal
            continue

        # One-sided rows
        if d > 0.0 and c == 0.0:
            # Debit should decrease balance: delta ~= -d
            if abs(delta - d) <= tol and abs(delta + d) > tol:
                txn["credit"] = d
                txn["debit"] = 0.0
                swaps += 1
                d = 0.0
                c = txn["credit"]
            elif abs(delta + d) > tol:
                # Amount drift: snap debit to chain amount when side is correct but amount isn't.
                txn["debit"] = expected_amt
                amount_repairs += 1
        elif c > 0.0 and d == 0.0:
            # Credit should increase balance: delta ~= +c
            if abs(delta + c) <= tol and abs(delta - c) > tol:
                txn["debit"] = c
                txn["credit"] = 0.0
                swaps += 1
                d = txn["debit"]
                c = 0.0
            elif abs(delta - c) > tol:
                txn["credit"] = expected_amt
                amount_repairs += 1
        elif d > 0.0 and c > 0.0:
            # Keep the side that best matches delta and drop the other.
            debit_err = abs(delta + d)
            credit_err = abs(delta - c)
            if debit_err <= tol and credit_err > tol:
                txn["credit"] = 0.0
            elif credit_err <= tol and debit_err > tol:
                txn["debit"] = 0.0
            else:
                # Neither side is consistent: rebuild from balance direction.
                if delta < 0:
                    txn["debit"] = expected_amt
                    txn["credit"] = 0.0
                else:
                    txn["credit"] = expected_amt
                    txn["debit"] = 0.0
                amount_repairs += 1
        elif d == 0.0 and c == 0.0:
            # No parsed amount but balance moved: reconstruct from chain.
            if delta < 0:
                txn["debit"] = expected_amt
            else:
                txn["credit"] = expected_amt
            amount_repairs += 1

        prev_balance = bal

    if swaps:
        print(f"DEBUG [openai_vision]: Balance-chain repair swapped {swaps} rows.")
    if amount_repairs:
        print(f"DEBUG [openai_vision]: Balance-chain repair adjusted amounts on {amount_repairs} rows.")
    return transactions


def extract_statement_summary_with_openai(pdf_path: str) -> Dict[str, Any]:
    """
    Read the account summary block from page 1 (scanned statements).
    Returns keys aligned with metadata used by validation.
    """
    result = {
        "statement_total_debit": None,
        "statement_total_credit": None,
        "opening_balance": None,
        "closing_balance": None,
        "account_number": None,
        "account_name": None,
        "period": None,
    }
    p = Path(pdf_path)
    if not p.exists():
        return result

    try:
        doc = fitz.open(str(p))
        if len(doc) == 0:
            return result
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        image_bytes = pix.tobytes("png")
        doc.close()
    except Exception as e:
        print(f"DEBUG [openai_vision]: Summary render failed: {e}")
        return result

    client = get_openai_client()
    if not client:
        return result

    model_name = os.getenv("OPENAI_OCR_MODEL", "gpt-4o")
    prompt = (
        "Extract only the account summary fields from this bank statement page. "
        "Return strict JSON with keys: account_name, account_number, period, "
        "opening_balance, closing_balance, statement_total_debit, statement_total_credit. "
        "For missing values return null."
    )
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(image_bytes)}"}},
                    ],
                }
            ],
            temperature=0,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        parsed = json.loads(content) if content else {}
        if not isinstance(parsed, dict):
            return result
        result["statement_total_debit"] = _safe_float(parsed.get("statement_total_debit"))
        result["statement_total_credit"] = _safe_float(parsed.get("statement_total_credit"))
        result["opening_balance"] = _safe_float(parsed.get("opening_balance"))
        result["closing_balance"] = _safe_float(parsed.get("closing_balance"))
        result["account_number"] = (str(parsed.get("account_number") or "").strip() or None)
        result["account_name"] = (str(parsed.get("account_name") or "").strip() or None)
        result["period"] = (str(parsed.get("period") or "").strip() or None)
    except Exception as e:
        print(f"DEBUG [openai_vision]: Summary extraction failed: {e}")

    return result


def extract_transactions_from_pdf_with_openai(
    pdf_path: str,
    max_pages: int = 15,
    page_numbers: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
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
    if page_numbers:
        page_idx_list = [p - 1 for p in page_numbers if isinstance(p, int) and 1 <= p <= len(doc)]
        # Preserve order and uniqueness
        seen = set()
        page_indices = []
        for idx in page_idx_list:
            if idx in seen:
                continue
            seen.add(idx)
            page_indices.append(idx)
    else:
        page_indices = list(range(page_limit))
    model_name = os.getenv("OPENAI_OCR_MODEL", "gpt-4o")

    prompt = (
        "Extract all bank transaction rows from this statement page. "
        "Return ONLY strict JSON object with key 'rows'. "
        "Each row object must have keys: date, value_date, description, debit, credit, balance. "
        "Use empty string for missing date/description and 0.00 for missing numeric fields. "
        "Do NOT include opening/closing balance summary lines or page totals."
    )

    for idx in page_indices:
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
            print(f"DEBUG [openai_vision]: Page {idx+1}/{len(doc)} -> {len(rows)} raw rows")
        except Exception as e:
            print(f"DEBUG [openai_vision]: Page {idx+1} extraction failed: {e}")
            continue

    try:
        doc.close()
    except Exception:
        pass
    out = _dedupe_transactions(out)
    out = _repair_debit_credit_by_balance_chain(out)
    print(f"DEBUG [openai_vision]: Total fallback transactions: {len(out)}")
    return out
