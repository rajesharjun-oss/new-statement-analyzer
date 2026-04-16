"""
Claude Extraction Fallback
Sends PDFs natively to Claude via base64 for structured extraction.
Only triggers when pdfplumber + Gemini fail or produce low-quality results.
"""
import os
import re
import base64
import json
import anthropic
from pathlib import Path
from typing import List, Dict, Any


def get_claude_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def extract_with_claude(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extract bank statement transactions using Claude's native PDF understanding.
    
    Sends the full PDF as base64 to Claude, which reads all pages visually
    and returns structured PSV data. This is the ultimate fallback when
    pdfplumber column detection and Gemini Vision both fail.
    
    Returns: List of transaction dicts matching the standard format.
    """
    client = get_claude_client()
    if not client:
        print("DEBUG [claude_extraction]: No ANTHROPIC_API_KEY configured. Skipping.")
        return []

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"DEBUG [claude_extraction]: PDF not found: {pdf_path}")
        return []

    # --- SAFETY CAP: Slice PDF to max_pages ---
    from pypdf import PdfReader, PdfWriter
    import io

    max_pages = 15
    reader = PdfReader(pdf_file)
    total_orig_pages = len(reader.pages)
    
    if total_orig_pages > max_pages:
        print(f"DEBUG [claude_extraction]: Slicing PDF from {total_orig_pages} to {max_pages} pages for safety.")
        writer = PdfWriter()
        for i in range(max_pages):
            writer.add_page(reader.pages[i])
        
        output_buffer = io.BytesIO()
        writer.write(output_buffer)
        pdf_bytes = output_buffer.getvalue()
    else:
        pdf_bytes = pdf_file.read_bytes()

    pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
    pdf_base64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    print(f"DEBUG [claude_extraction]: Sending {pdf_size_mb:.1f}MB PDF to Claude for extraction...")

    prompt = (
        "You are a high-precision Financial OCR and Extraction Engine specialized in Nigerian bank statements.\n\n"
        "TASK: Extract ALL transaction rows from this bank statement PDF into Pipe-Separated Values (PSV) format.\n\n"
        "DIRECTIVES:\n"
        "1. Extract EVERY transaction row exactly as printed. Do NOT skip any rows.\n"
        "2. Ignore watermarks, logos, headers, footers, and page numbers.\n"
        "3. Merge multi-line descriptions into a single clean string on one row.\n"
        "4. Numbers: Remove currency symbols and thousand separators. Output raw floats (e.g. 100500.00). Use 0.00 for empty amounts.\n"
        "5. If the statement has a Reference/Chq No column, append its value to the DESCRIPTION. NEVER put reference numbers into DEBIT, CREDIT, or BALANCE.\n"
        "6. Skip summary/total rows like 'OPENING BALANCE', 'CLOSING BALANCE', 'TOTAL DEBIT', 'TOTAL CREDIT', 'BALANCE B/F', 'BALANCE C/F'.\n"
        "7. If the statement contains multiple accounts, separate them with a line: ---ACCOUNT_BREAK---\n\n"
        "OUTPUT FORMAT:\n"
        "Return ONLY raw PSV text with NO headers, NO markdown, NO explanations.\n"
        "Each row must have exactly 6 columns separated by 5 pipes:\n"
        "DATE|VALUE_DATE|DESCRIPTION|DEBIT|CREDIT|BALANCE\n\n"
        "If VALUE_DATE is missing or the same as DATE, leave it blank but keep the pipe separators.\n"
        "Example row: 15-Jan-2024||NIP TRF TO JOHN DOE|50000.00|0.00|1250000.50\n"
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        raw_text = response.content[0].text.strip()
        
        # Clean markdown fences if Claude wrapped the output
        raw_text = re.sub(r'^```(?:csv|psv|text)?\s*', '', raw_text, flags=re.I)
        raw_text = re.sub(r'```$', '', raw_text, flags=re.I).strip()

        # Debug: save raw output for inspection
        debug_path = pdf_file.with_suffix('.claude_raw.psv')
        try:
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(raw_text)
            print(f"DEBUG [claude_extraction]: Raw PSV saved to {debug_path}")
        except Exception:
            pass

        # Parse PSV into transaction dicts
        transactions = _parse_psv(raw_text)
        
        # Apply column auto-correction (same logic as standard_ocr.py)
        transactions = _auto_correct_columns(transactions)

        print(f"DEBUG [claude_extraction]: Successfully extracted {len(transactions)} transactions via Claude.")
        return transactions

    except Exception as e:
        print(f"ERROR [claude_extraction]: Claude extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return []


def _safe_float(val: str) -> float:
    """Parse a money string to float, with safety guards."""
    if not val or str(val).isspace():
        return 0.0
    try:
        s = str(val).replace(',', '').strip()
        s = re.sub(r'[^\d.\-]', '', s)
        if not s or s in ('-', '.'):
            return 0.0
        parsed = float(s)
        # Safety: reject astronomically large values (hallucinated references)
        if abs(parsed) > 10_000_000_000.0:  # 10 Billion cap
            print(f"DEBUG [claude_extraction]: Rejected massive float: {parsed}")
            return 0.0
        return parsed
    except (ValueError, TypeError):
        return 0.0


def _parse_psv(text: str) -> List[Dict[str, Any]]:
    """Parse pipe-separated text into standard transaction dicts."""
    transactions = []

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('---ACCOUNT_BREAK---'):
            continue

        parts = line.split('|')

        if len(parts) >= 6:
            date_val = parts[0].strip()
            val_date = parts[1].strip()
            desc_val = parts[2].strip()
            deb_val = _safe_float(parts[3])
            cred_val = _safe_float(parts[4])
            bal_val = _safe_float(parts[5])
        elif len(parts) == 5:
            date_val = parts[0].strip()
            val_date = ""
            desc_val = parts[1].strip()
            deb_val = _safe_float(parts[2])
            cred_val = _safe_float(parts[3])
            bal_val = _safe_float(parts[4])
        else:
            continue

        # Skip header-like rows
        desc_upper = desc_val.upper()
        if 'DATE' in date_val.upper() and 'DESCRIPTION' in desc_upper:
            continue
        
        # Skip summary rows
        skip_keywords = [
            'TOTAL', 'SUM', 'BROUGHT FORWARD', 'CARRIED FORWARD',
            'BALANCE B/F', 'BALANCE C/F', 'OPENING BALANCE',
            'CLOSING BALANCE', 'PAGE TOTAL'
        ]
        if any(kw in desc_upper for kw in skip_keywords):
            continue

        transactions.append({
            'date': date_val,
            'value_date': val_date,
            'description': desc_val,
            'debit': deb_val,
            'credit': cred_val,
            'balance': bal_val,
            'reference': '',
            'remarks': desc_val,
            'category': 'Uncategorized',
        })

    return transactions


def extract_from_ocr_text(ocr_text: str, bank_hint: str = "") -> List[Dict[str, Any]]:
    """
    Stage 2 of 2-stage pipeline: structured extraction from Gemini-OCR'd plain text.
    
    Takes raw OCR text (from gemini_ocr_to_text) and asks Claude Sonnet to parse it
    into structured PSV transactions. This separates OCR (Gemini's strength) from
    context-aware extraction (Claude's strength).
    
    Args:
        ocr_text: Concatenated plain text from Gemini OCR, with === PAGE N === markers.
        bank_hint: Optional bank name/identifier for context.
    
    Returns: List of transaction dicts matching the standard format.
    """
    client = get_claude_client()
    if not client:
        print("DEBUG [claude_extraction]: No ANTHROPIC_API_KEY configured. Skipping.")
        return []

    if not ocr_text.strip():
        print("DEBUG [claude_extraction]: Empty OCR text supplied.")
        return []

    bank_context = f"Bank: {bank_hint}\n" if bank_hint else ""

    # Chunk large OCR text: Claude max_tokens=8192 output; cap input at ~80k chars (~20k tokens)
    MAX_INPUT_CHARS = 80_000
    chunks = []
    if len(ocr_text) <= MAX_INPUT_CHARS:
        chunks = [ocr_text]
    else:
        # Split on PAGE markers so we don't cut mid-row
        import re as _re
        pages = _re.split(r'(=== PAGE \d+ ===)', ocr_text)
        current = ""
        for part in pages:
            if len(current) + len(part) > MAX_INPUT_CHARS and current:
                chunks.append(current)
                current = part
            else:
                current += part
        if current:
            chunks.append(current)
        print(f"DEBUG [claude_extraction]: OCR text split into {len(chunks)} chunk(s) for Claude.")

    prompt_template = (
        "You are a high-precision Financial Extraction Engine specialised in Nigerian bank statements.\n"
        "{bank_context}"
        "Below is OCR-transcribed text from a bank statement PDF. Extract ALL transaction rows.\n\n"
        "DIRECTIVES:\n"
        "1. Extract EVERY transaction row. Do NOT skip any.\n"
        "2. Ignore page headers, footers, watermarks, page numbers, and === PAGE N === markers.\n"
        "3. Merge multi-line descriptions into a single clean row.\n"
        "4. Numbers: Remove currency symbols and commas. Output raw floats (e.g. 100500.00). Use 0.00 for empty.\n"
        "5. Reference/Chq No column: append its value to the DESCRIPTION field. "
        "NEVER put reference numbers into DEBIT, CREDIT, or BALANCE.\n"
        "6. Skip summary rows: OPENING BALANCE, CLOSING BALANCE, TOTAL DEBIT, TOTAL CREDIT, "
        "BALANCE B/F, BALANCE C/F, PAGE TOTAL.\n"
        "7. Multiple accounts: separate with a line containing only ---ACCOUNT_BREAK---\n\n"
        "OUTPUT FORMAT: Raw PSV only (NO headers, NO markdown, NO explanations).\n"
        "Each row must have exactly 6 columns: DATE|VALUE_DATE|DESCRIPTION|DEBIT|CREDIT|BALANCE\n"
        "If VALUE_DATE is absent or equals DATE, leave it blank: "
        "15-Jan-2024||NIP TRF TO JOHN DOE|50000.00|0.00|1250000.50\n\n"
        "OCR TEXT:\n"
        "{ocr_text}"
    )

    all_transactions: List[Dict[str, Any]] = []

    for chunk_idx, chunk in enumerate(chunks, 1):
        prompt = prompt_template.format(bank_context=bank_context, ocr_text=chunk)
        try:
            print(f"DEBUG [claude_extraction]: Sending OCR chunk {chunk_idx}/{len(chunks)} "
                  f"({len(chunk):,} chars) to Claude for extraction...")
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.content[0].text.strip()
            raw_text = re.sub(r'^```(?:csv|psv|text)?\s*', '', raw_text, flags=re.I)
            raw_text = re.sub(r'```$', '', raw_text, flags=re.I).strip()

            # Debug: save raw PSV per chunk
            debug_path = Path(f"/tmp/claude_ocr_chunk_{chunk_idx}.psv")
            try:
                debug_path.write_text(raw_text, encoding="utf-8")
            except Exception:
                pass

            chunk_txns = _parse_psv(raw_text)
            print(f"DEBUG [claude_extraction]: Chunk {chunk_idx} → {len(chunk_txns)} transactions.")
            all_transactions.extend(chunk_txns)

        except Exception as e:
            print(f"ERROR [claude_extraction]: OCR chunk {chunk_idx} extraction failed: {e}")
            import traceback
            traceback.print_exc()

    if not all_transactions:
        return []

    all_transactions = _auto_correct_columns(all_transactions)
    print(f"DEBUG [claude_extraction]: Total extracted from OCR text: {len(all_transactions)} transactions.")
    return all_transactions


def _auto_correct_columns(txns: List[Dict]) -> List[Dict]:
    """
    Mathematical column auto-correction.
    Uses balance anchors to detect and fix swapped debit/credit columns.
    Same logic as standard_ocr.py.
    """
    valid_anchors = [i for i, t in enumerate(txns) if t['balance'] != 0.0]

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
                    print(f"DEBUG [claude_extraction]: Auto-corrected DEBIT -> CREDIT for {t['credit']}")
                    break
                elif t['credit'] > 0 and round(t['credit'] * -2, 2) == deficit:
                    t['debit'] = t['credit']
                    t['credit'] = 0.0
                    print(f"DEBUG [claude_extraction]: Auto-corrected CREDIT -> DEBIT for {t['debit']}")
                    break

    return txns
