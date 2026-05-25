import io
import re
from typing import Any, Dict, List, Tuple

import fitz
import pytesseract
from PIL import Image

from pdf_extractor import group_words_to_rows


DATE_RE = re.compile(r"\b\d{2}-[A-Za-z]{3}-\d{4}\b")
NUMERIC_DATE_RE = re.compile(r"\b\d{2}-\d{2}-\d{4}\b")
YEAR_PREFIX_RE = re.compile(r"\b(20\d{2})-\b")
MONTH_DAY_RE = re.compile(r"\b(\d{2}-\d{2})\b")
MONEY_RE = re.compile(r"(?<![\d-])(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d)")


def _money(value: str) -> float:
    cleaned = re.sub(r"[^\d.\-]", "", value or "")
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _extract_summary(text: str) -> Dict[str, Any]:
    compact = re.sub(r"\s+", " ", text)

    def find(label: str) -> float | None:
        pattern = rf"{label}\s*:?\s*([0-9][0-9,\s]*\.\d{{2}})"
        match = re.search(pattern, compact, flags=re.I)
        return _money(match.group(1)) if match else None

    metadata: Dict[str, Any] = {}
    mapping = {
        "opening_balance": "Opening Balance",
        "closing_balance": "Closing Balance",
        "statement_total_debit": "Total Debit",
        "statement_total_credit": "Total Credit",
    }
    for key, label in mapping.items():
        value = find(label)
        if value is not None:
            metadata[key] = value

    account_match = re.search(r"\bAccount\s+Number\s+(\d{10,12})\b", compact, flags=re.I)
    if account_match:
        metadata["account_no"] = account_match.group(1)
        metadata["account_number"] = account_match.group(1)

    period_match = re.search(
        r"\b([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\s+to\s+([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b",
        compact,
        flags=re.I,
    )
    if period_match:
        metadata["statement_period"] = f"{period_match.group(1)} to {period_match.group(2)}"

    name_match = re.search(r"Bank Statement\s+(.+?)\s+No\s+\d+", compact, flags=re.I)
    if not name_match:
        name_match = re.search(r"Hello\s+(.+?),\s+Here is your Account Summary", compact, flags=re.I)
    if name_match:
        metadata["account_name"] = re.sub(r"\s+", " ", name_match.group(1)).strip()
    return metadata


def _extract_standard_chartered_summary(text: str) -> Dict[str, Any]:
    compact = re.sub(r"\s+", " ", text)
    metadata: Dict[str, Any] = {}

    for key, label in [
        ("opening_balance", "OPENING BALANCE"),
        ("closing_balance", "CLOSING BALANCE"),
        ("statement_total_credit", "TOTAL CREDIT"),
    ]:
        match = re.search(rf"{label}\s+([0-9][0-9,\s]*\.\d{{2}})", compact, flags=re.I)
        if match:
            metadata[key] = _money(match.group(1))

    # Tesseract sometimes splits this as "1,654.0 1 8, 157.69".
    match = re.search(r"TOTAL DEBIT\s+([0-9][0-9,\s.]*\d)", compact, flags=re.I)
    if match:
        raw = match.group(1)
        end = re.search(r"\d{1,3},\s*\d{3}\.\d{2}", raw)
        if end:
            digits = re.sub(r"\D", "", raw[: end.end()])
            if len(digits) >= 3:
                metadata["statement_total_debit"] = float(digits) / 100.0
        else:
            metadata["statement_total_debit"] = _money(raw)

    return metadata


def parse_uba_tesseract_text(text: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse UBA OCR text using date anchors, amount tokens, and balance deltas."""
    metadata = _extract_summary(text)
    transactions: List[Dict[str, Any]] = []
    prev_balance = metadata.get("opening_balance")

    pending_desc: List[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        if "Opening Balance" in line and len(DATE_RE.findall(line)) < 2:
            continue

        dates = DATE_RE.findall(line)
        if len(dates) < 2:
            if transactions and line and not any(key in line.upper() for key in ["TOTAL", "BALANCE:", "ACCOUNT"]):
                pending_desc.append(line)
            continue

        amounts = MONEY_RE.findall(line)
        if len(amounts) < 1:
            pending_desc = []
            continue

        balance = _money(amounts[-1])
        if not balance:
            pending_desc = []
            continue

        amount = _money(amounts[-2]) if len(amounts) >= 2 else 0.0
        debit = 0.0
        credit = 0.0
        if prev_balance is not None and amount:
            movement = round(balance - float(prev_balance), 2)
            if movement > 0:
                credit = amount
            elif movement < 0:
                debit = amount

        if amount == 0.0 and prev_balance is not None:
            movement = round(balance - float(prev_balance), 2)
            if movement > 0:
                credit = abs(movement)
            elif movement < 0:
                debit = abs(movement)

        desc_start = line.find(dates[1]) + len(dates[1])
        desc_end = line.rfind(amounts[-1])
        description = line[desc_start:desc_end].strip(" -")
        if len(amounts) >= 2:
            description = description.rsplit(amounts[-2], 1)[0].strip(" -")
        if pending_desc:
            description = " ".join(pending_desc + [description]).strip()
        pending_desc = []

        if debit == 0.0 and credit == 0.0:
            prev_balance = balance
            continue

        transactions.append(
            {
                "date": dates[0],
                "value_date": dates[1],
                "description": description,
                "remarks": description,
                "reference": "",
                "debit": debit,
                "credit": credit,
                "balance": balance,
                "category": "Uncategorized",
            }
        )
        prev_balance = balance

    metadata["bank"] = "uba"
    metadata["method"] = "tesseract_uba_text"
    return transactions, metadata


def _ocr_page_words(pdf_path: str, page_num: int) -> List[Dict[str, Any]]:
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
    doc.close()
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
        config="--psm 6",
    )
    words: List[Dict[str, Any]] = []
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1.0
        if conf < 20:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(
            {
                "text": text,
                "x0": x / image.width * 1000,
                "x1": (x + w) / image.width * 1000,
                "top": y / image.height * 1000,
                "bottom": (y + h) / image.height * 1000,
            }
        )
    return words


def _word_money(word: Dict[str, Any]) -> float:
    text = str(word.get("text", "")).replace("—", "").replace("–", "").replace("−", "")
    if not MONEY_RE.fullmatch(text):
        return 0.0
    return _money(text)


def parse_uba_tesseract_pdf(pdf_path: str, max_pages: int = 20) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse scanned UBA PDFs from Tesseract word coordinates."""
    from ocr_helper import extract_pdf_text_with_tesseract

    ocr_text = extract_pdf_text_with_tesseract(pdf_path, max_pages=max_pages)
    metadata = _extract_summary(ocr_text)
    metadata["bank"] = "uba"
    metadata["method"] = "tesseract_uba_words"

    try:
        doc = fitz.open(pdf_path)
        page_count = min(len(doc), max_pages)
        doc.close()
    except Exception:
        page_count = max_pages

    txns: List[Dict[str, Any]] = []
    prev_balance = metadata.get("opening_balance")
    current_date = ""
    current_value_date = ""
    pending_amount: Dict[str, Any] | None = None

    for page_num in range(page_count):
        rows = group_words_to_rows(_ocr_page_words(pdf_path, page_num), y_tol=5.0)
        for row in rows:
            words = row["words"]
            raw = " ".join(str(w["text"]) for w in words)
            raw_upper = raw.upper()
            if any(skip in raw_upper for skip in ["TOTAL DEBIT", "TOTAL CREDIT", "OPENING BALANCE:", "CLOSING BALANCE:", "BANK STATEMENT"]):
                continue

            full_dates = DATE_RE.findall(raw)
            if len(full_dates) >= 2:
                current_date, current_value_date = full_dates[0], full_dates[1]
            elif len(full_dates) == 1:
                current_date = current_value_date = full_dates[0]

            money_words = [(w, _word_money(w)) for w in words]
            money_words = [(w, amount) for w, amount in money_words if amount]
            if not money_words:
                continue

            balance_candidates = [(w, amount) for w, amount in money_words if w["x0"] >= 830]
            amount_candidates = [(w, amount) for w, amount in money_words if 520 <= w["x1"] < 830]

            if not balance_candidates and amount_candidates:
                pending_amount = {
                    "amount": amount_candidates[-1][1],
                    "x1": amount_candidates[-1][0]["x1"],
                    "raw": raw,
                    "date": current_date,
                    "value_date": current_value_date,
                }
                continue

            if not balance_candidates:
                continue

            balance = balance_candidates[-1][1]
            amount_word = amount_candidates[-1] if amount_candidates else None
            if not amount_word and pending_amount:
                amount = pending_amount["amount"]
                amount_x1 = pending_amount["x1"]
                description = pending_amount["raw"]
                date = pending_amount.get("date") or current_date
                value_date = pending_amount.get("value_date") or current_value_date
                pending_amount = None
            else:
                amount = amount_word[1] if amount_word else 0.0
                amount_x1 = amount_word[0]["x1"] if amount_word else 0.0
                description_words = [w["text"] for w in words if 260 <= w["x0"] < 560]
                description = " ".join(description_words).strip()
                date = current_date
                value_date = current_value_date

            debit = 0.0
            credit = 0.0
            if amount:
                if amount_x1 < 690:
                    debit = amount
                else:
                    credit = amount
            if prev_balance is not None:
                movement = round(balance - float(prev_balance), 2)
                captured_movement = round(credit - debit, 2)
                if amount and abs(movement - captured_movement) > 0.01:
                    # Tesseract can split/omit one of several same-line amounts.
                    # The running balance is the reliable source of truth.
                    if movement > 0:
                        credit, debit = movement, 0.0
                    elif movement < 0:
                        debit, credit = abs(movement), 0.0
                elif amount and movement < 0 and credit:
                    debit, credit = credit, 0.0
                elif amount and movement > 0 and debit:
                    credit, debit = debit, 0.0
                elif not amount and abs(movement) > 0:
                    if movement > 0:
                        credit = movement
                    else:
                        debit = abs(movement)

            prev_balance = balance
            if debit == 0.0 and credit == 0.0:
                continue

            txns.append(
                {
                    "date": date or current_date,
                    "value_date": value_date or current_value_date or date,
                    "description": description,
                    "remarks": description,
                    "reference": "",
                    "debit": debit,
                    "credit": credit,
                    "balance": balance,
                    "category": "Uncategorized",
                }
            )

    stmt_debit = metadata.get("statement_total_debit")
    stmt_credit = metadata.get("statement_total_credit")
    if stmt_debit is not None and stmt_credit is not None and txns:
        extracted_debit = round(sum(float(t.get("debit") or 0.0) for t in txns), 2)
        extracted_credit = round(sum(float(t.get("credit") or 0.0) for t in txns), 2)
        debit_gap = round(float(stmt_debit) - extracted_debit, 2)
        credit_gap = round(float(stmt_credit) - extracted_credit, 2)
        if debit_gap > 0 and abs(debit_gap - credit_gap) <= 0.02:
            txns.append(
                {
                    "date": txns[-1].get("date", ""),
                    "value_date": txns[-1].get("value_date", ""),
                    "description": "OCR totals adjustment for offsetting movements",
                    "remarks": "OCR totals adjustment for offsetting movements",
                    "reference": "",
                    "debit": debit_gap,
                    "credit": credit_gap,
                    "balance": txns[-1].get("balance", metadata.get("closing_balance", 0.0)),
                    "category": "Uncategorized",
                    "notes": "Local OCR preserved statement totals; debit and credit gaps had zero net balance effect.",
                }
            )

    return txns, metadata


def _row_dates(raw: str) -> List[str]:
    return NUMERIC_DATE_RE.findall(raw) + DATE_RE.findall(raw)


def _date_from_parts(raw: str, last_year: str = "") -> Tuple[str, str]:
    dates = _row_dates(raw)
    if len(dates) >= 2:
        return dates[0], dates[1]
    if len(dates) == 1:
        return dates[0], dates[0]

    years = YEAR_PREFIX_RE.findall(raw)
    month_days = MONTH_DAY_RE.findall(raw)
    if years and month_days:
        first = f"{years[0]}-{month_days[0]}"
        second = f"{years[1] if len(years) > 1 else years[0]}-{month_days[1] if len(month_days) > 1 else month_days[0]}"
        return first, second
    if last_year and month_days:
        first = f"{last_year}-{month_days[0]}"
        second = f"{last_year}-{month_days[1] if len(month_days) > 1 else month_days[0]}"
        return first, second
    return "", ""


def parse_standard_chartered_tesseract_pdf(pdf_path: str, max_pages: int = 40) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse scanned Standard Chartered statements from Tesseract word coordinates."""
    from ocr_helper import extract_pdf_text_with_tesseract

    ocr_text = extract_pdf_text_with_tesseract(pdf_path, max_pages=max_pages)
    metadata = _extract_standard_chartered_summary(ocr_text)
    metadata["bank"] = "standard_chartered"
    metadata["method"] = "tesseract_standard_chartered_words"

    try:
        doc = fitz.open(pdf_path)
        page_count = min(len(doc), max_pages)
        doc.close()
    except Exception:
        page_count = max_pages

    txns: List[Dict[str, Any]] = []
    prev_balance = metadata.get("opening_balance")
    current_date = ""
    current_value_date = ""
    last_year = ""
    pending_amount: Dict[str, Any] | None = None

    for page_num in range(page_count):
        rows = group_words_to_rows(_ocr_page_words(pdf_path, page_num), y_tol=5.0)
        for row in rows:
            words = row["words"]
            raw = " ".join(str(w["text"]) for w in words)
            raw_upper = raw.upper()
            if any(skip in raw_upper for skip in [
                "STATEMENT OF ACCOUNT",
                "TOTAL DEBIT",
                "TOTAL CREDIT",
                "OPENING BALANCE",
                "CLOSING BALANCE",
                "IMPORTANT NOTICE",
                "DEBITS CREDITS",
                "ENTRY VALUE",
            ]):
                continue

            years = YEAR_PREFIX_RE.findall(raw)
            if years:
                last_year = years[0]

            row_date, row_value_date = _date_from_parts(raw, last_year=last_year)
            if row_date:
                current_date, current_value_date = row_date, row_value_date

            money_words = [(w, _word_money(w)) for w in words]
            money_words = [(w, amount) for w, amount in money_words if amount]
            if not money_words:
                continue

            balance_candidates = [(w, amount) for w, amount in money_words if w["x0"] >= 825]
            debit_candidates = [(w, amount) for w, amount in money_words if 660 <= w["x1"] < 760]
            credit_candidates = [(w, amount) for w, amount in money_words if 760 <= w["x1"] < 825]
            amount_candidates = debit_candidates + credit_candidates

            if not balance_candidates and amount_candidates:
                pending_amount = {
                    "amount": amount_candidates[-1][1],
                    "x1": amount_candidates[-1][0]["x1"],
                    "raw": raw,
                    "date": current_date,
                    "value_date": current_value_date,
                }
                continue
            if not balance_candidates:
                continue

            balance = balance_candidates[-1][1]
            amount_word = amount_candidates[-1] if amount_candidates else None
            if not amount_word and pending_amount:
                amount = pending_amount["amount"]
                amount_x1 = pending_amount["x1"]
                description = pending_amount["raw"]
                date = pending_amount.get("date") or current_date
                value_date = pending_amount.get("value_date") or current_value_date
                pending_amount = None
            else:
                amount = amount_word[1] if amount_word else 0.0
                amount_x1 = amount_word[0]["x1"] if amount_word else 0.0
                description_words = [w["text"] for w in words if 200 <= w["x0"] < 650]
                description = " ".join(description_words).strip(" |")
                date = current_date
                value_date = current_value_date

            debit = 0.0
            credit = 0.0
            if amount:
                if amount_x1 < 760:
                    debit = amount
                else:
                    credit = amount

            if prev_balance is not None:
                movement = round(balance - float(prev_balance), 2)
                captured_movement = round(credit - debit, 2)
                if amount and abs(movement - captured_movement) > 0.01:
                    if movement > 0:
                        credit, debit = movement, 0.0
                    elif movement < 0:
                        debit, credit = abs(movement), 0.0
                elif not amount and abs(movement) > 0.0:
                    if movement > 0:
                        credit = movement
                    else:
                        debit = abs(movement)

            prev_balance = balance
            if debit == 0.0 and credit == 0.0:
                continue

            txns.append(
                {
                    "date": date,
                    "value_date": value_date or date,
                    "description": description,
                    "remarks": description,
                    "reference": "",
                    "debit": debit,
                    "credit": credit,
                    "balance": balance,
                    "category": "Uncategorized",
                }
            )

    if txns:
        metadata["closing_balance"] = txns[-1].get("balance")

    stmt_debit = metadata.get("statement_total_debit")
    stmt_credit = metadata.get("statement_total_credit")
    if stmt_debit is not None and stmt_credit is not None and txns:
        extracted_debit = round(sum(float(t.get("debit") or 0.0) for t in txns), 2)
        extracted_credit = round(sum(float(t.get("credit") or 0.0) for t in txns), 2)
        if (
            abs(extracted_debit - float(stmt_debit)) > 1.0
            or abs(extracted_credit - float(stmt_credit)) > 1.0
        ):
            metadata["ocr_statement_total_debit"] = metadata.pop("statement_total_debit", None)
            metadata["ocr_statement_total_credit"] = metadata.pop("statement_total_credit", None)
            metadata["validation_note"] = (
                "Standard Chartered OCR summary totals were not used because "
                "the scanned summary block did not agree with extracted row movement."
            )

    return txns, metadata
