import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pdfplumber

try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError:
    fitz = None
    PYMUPDF_AVAILABLE = False


DATE_FORMATS = ("%d%b%y", "%d-%b-%y", "%d%b%Y", "%d-%b-%Y")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _parse_date(value: Any) -> str | None:
    text = _clean(value).replace(" ", "")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%d-%b-%Y")
        except ValueError:
            continue
    return None


def _parse_money(value: Any) -> float:
    text = _clean(value).upper()
    if not text:
        return 0.0

    negative = (text.startswith("(") and text.endswith(")")) or text.endswith("DR")
    cleaned = re.sub(r"[^\d.]", "", text)
    if not cleaned:
        return 0.0
    try:
        amount = float(cleaned)
    except ValueError:
        return 0.0
    return -abs(amount) if negative else amount


def _normalise_period_date(value: str) -> str:
    parsed = _parse_date(value)
    return parsed or _clean(value)


def parse_keystone_metadata(text: str) -> Dict[str, Any]:
    """Parse Keystone's two-column account-summary block."""
    metadata: Dict[str, Any] = {"bank": "keystone"}

    period = re.search(
        r"Summary\s+Statement\s+for\s+([0-3]?\d-[A-Za-z]{3}-\d{2,4})\s+To\s+"
        r"([0-3]?\d-[A-Za-z]{3}-\d{2,4})",
        text,
        re.I,
    )
    if period:
        metadata["statement_period"] = (
            f"{_normalise_period_date(period.group(1))} to "
            f"{_normalise_period_date(period.group(2))}"
        )

    account_number = re.search(r"Account\s+No\.?\s*(?:-|:)?\s*(\d{10,12})", text, re.I)
    if account_number:
        metadata["account_no"] = account_number.group(1)
        metadata["account_number"] = account_number.group(1)

    currency = re.search(r"\bCurrency\s+(NAIRA|NGN|USD|GBP|EUR)\b", text, re.I)
    if currency:
        raw_currency = currency.group(1).upper()
        metadata["currency"] = "NGN" if raw_currency == "NAIRA" else raw_currency

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if not re.search(r"\bAccount\s+Name\b", line, re.I):
            continue
        for raw_candidate in lines[index + 1:index + 4]:
            candidate = re.split(
                r"\s+(?:Total\s+Debits?|Total\s+Credits?|Closing\s+Balance|Cleared\s+Balance)",
                raw_candidate,
                maxsplit=1,
                flags=re.I,
            )[0]
            candidate = _clean(candidate)
            if candidate and not re.search(r"\b(?:balance|total|currency|account)\b", candidate, re.I):
                metadata["account_name"] = candidate
                break
        break

    def summary_money(label: str) -> float | None:
        match = re.search(
            rf"{label}\s*(?:-|:)?\s*([\d,]+\.\d{{2}})",
            text,
            re.I,
        )
        return _parse_money(match.group(1)) if match else None

    fields = {
        "opening_balance": summary_money(r"Opening\s+Balance"),
        "statement_total_debit": summary_money(r"Total\s+Debits?"),
        "statement_total_credit": summary_money(r"Total\s+Credits?"),
        "closing_balance": summary_money(r"Closing\s+Balance"),
    }
    metadata.update({key: value for key, value in fields.items() if value is not None})
    return metadata


def _pymupdf_words(document: Any, page_index: int) -> List[Dict[str, Any]]:
    words: List[Dict[str, Any]] = []
    page = document[page_index]
    page_height = float(page.rect.height)
    for word in page.get_text("words"):
        text = _clean(word[4])
        if not text:
            continue
        words.append(
            {
                "text": text,
                "x0": float(word[0]),
                "top": float(word[1]),
                "x1": float(word[2]),
                "bottom": float(word[3]),
                "doctop": float(word[1]) + page_index * page_height,
            }
        )
    return words


def _group_rows(words: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    rows: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for word in words:
        rows[round(float(word["top"]))].append(word)
    return [sorted(rows[y], key=lambda item: item["x0"]) for y in sorted(rows)]


def detect_keystone_layout(
    words: List[Dict[str, Any]],
) -> Tuple[Dict[str, Tuple[float, float]], float] | None:
    """Detect Keystone's Date/V.Date/Narration/Ref/Debit/Credit/Balance header."""
    for row in _group_rows(words):
        row_text = " ".join(_clean(word.get("text")).upper() for word in row)
        if not all(token in row_text for token in ("DATE", "NARRATION", "DEBIT", "CREDIT", "BALANCE")):
            continue

        def find_exact(label: str) -> Dict[str, Any] | None:
            return next((word for word in row if _clean(word.get("text")).upper() == label), None)

        date_words = [word for word in row if _clean(word.get("text")).upper() == "DATE"]
        narration = find_exact("NARRATION")
        reference = find_exact("REF")
        debit = find_exact("DEBIT")
        credit = find_exact("CREDIT")
        balance = find_exact("BALANCE")
        value_marker = next(
            (word for word in row if _clean(word.get("text")).upper() in {"V.", "V"}),
            date_words[1] if len(date_words) > 1 else None,
        )
        if not date_words or not all((value_marker, narration, reference, debit, credit, balance)):
            continue

        date_end = (float(date_words[0]["x1"]) + float(value_marker["x0"])) / 2
        description_start = max(date_end + 25.0, float(narration["x0"]) - 65.0)
        reference_start = float(reference["x0"]) - 10.0
        debit_start = float(debit["x0"]) - 10.0
        credit_start = float(credit["x0"]) - 10.0
        balance_start = float(balance["x0"]) - 10.0

        cuts = {
            "date": (-math.inf, date_end),
            "value_date": (date_end, description_start),
            "description": (description_start, reference_start),
            "reference": (reference_start, debit_start),
            "debit": (debit_start, credit_start),
            "credit": (credit_start, balance_start),
            "balance": (balance_start, math.inf),
        }
        header_bottom = max(float(word.get("bottom", word["top"])) for word in row)
        return cuts, header_bottom
    return None


def _assign_row(
    row: List[Dict[str, Any]],
    cuts: Dict[str, Tuple[float, float]],
) -> Dict[str, str]:
    buckets: Dict[str, List[str]] = {name: [] for name in cuts}
    for word in row:
        x = float(word["x0"])
        for name, (left, right) in cuts.items():
            if left <= x < right:
                buckets[name].append(_clean(word.get("text")))
                break
    return {name: _clean(" ".join(values)) for name, values in buckets.items()}


def _is_noise(text: str) -> bool:
    clean = _clean(text).upper()
    return bool(
        not clean
        or re.search(r"-\s*PAGE\s+\d+\s+OF\s+\d+\s*-", clean)
        or any(
            marker in clean
            for marker in (
                "OPEN BALANCE",
                "CLOSING BALANCE",
                "SUMMARY DETAILS",
                "PRIVATE & CONFIDENTIAL",
                "WWW.KEYSTONEBANKNG.COM",
            )
        )
    )


def _append_detail(transaction: Dict[str, Any], detail: str) -> None:
    detail = _clean(detail)
    if not detail or _is_noise(detail):
        return
    existing = _clean(transaction.get("description"))
    transaction["description"] = _clean(f"{existing} {detail}")


def extract_keystone_via_coordinates(
    pdf_path: Path,
    metadata: Dict[str, Any],
    pdf: pdfplumber.PDF | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Extract searchable Keystone statements without invoking OCR or AI."""
    auto_close = False
    if pdf is None:
        pdf = pdfplumber.open(pdf_path)
        auto_close = True

    transactions: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    cuts: Dict[str, Tuple[float, float]] | None = None
    fast_document = None

    try:
        first_text = pdf.pages[0].extract_text() or ""
        metadata.update(parse_keystone_metadata(first_text))
        metadata["method"] = "keystone_coordinates"

        page_count = len(pdf.pages)
        if page_count > 100 and PYMUPDF_AVAILABLE:
            fast_document = fitz.open(pdf_path)
            print("DEBUG: Keystone fast mode using PyMuPDF visible-page words.")

        for page_index in range(page_count):
            words = (
                _pymupdf_words(fast_document, page_index)
                if fast_document is not None
                else pdf.pages[page_index].extract_words(x_tolerance=2, y_tolerance=2)
            )
            if not words:
                continue

            layout = detect_keystone_layout(words)
            header_bottom = None
            if layout:
                cuts, header_bottom = layout
            if not cuts:
                continue

            for row in _group_rows(words):
                row_top = min(float(word["top"]) for word in row)
                if header_bottom is not None and row_top <= header_bottom + 2.0:
                    continue

                raw_text = _clean(" ".join(word.get("text", "") for word in row))
                if _is_noise(raw_text):
                    continue

                assigned = _assign_row(row, cuts)
                parsed_date = _parse_date(assigned.get("date"))
                if parsed_date:
                    if current is not None:
                        current["description"] = _clean(current.get("description"))
                        current["remarks"] = current["description"]
                        transactions.append(current)

                    current = {
                        "date": parsed_date,
                        "value_date": _parse_date(assigned.get("value_date")) or parsed_date,
                        "description": _clean(assigned.get("description")),
                        "reference": _clean(assigned.get("reference")),
                        "debit": _parse_money(assigned.get("debit")),
                        "credit": _parse_money(assigned.get("credit")),
                        "balance": _parse_money(assigned.get("balance")),
                        "remarks": "",
                        "category": "Uncategorized",
                        "_page": page_index + 1,
                    }
                    continue

                if current is not None:
                    detail = _clean(
                        " ".join(
                            part
                            for part in (assigned.get("description"), assigned.get("reference"))
                            if part
                        )
                    )
                    _append_detail(current, detail)

        if current is not None:
            current["description"] = _clean(current.get("description"))
            current["remarks"] = current["description"]
            transactions.append(current)

        transactions = [
            transaction
            for transaction in transactions
            if transaction["debit"] != 0.0
            or transaction["credit"] != 0.0
            or transaction["balance"] != 0.0
        ]
        return transactions, metadata
    finally:
        if fast_document is not None:
            fast_document.close()
        if auto_close:
            pdf.close()
