import html
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pdfplumber


COLUMN_STARTS = [
    ("date", 0.0),
    ("account_name", 87.0),
    ("transaction_type", 139.9),
    ("transaction_status", 224.4),
    ("terminal_id", 294.2),
    ("rrn", 353.2),
    ("transaction_ref", 425.3),
    ("reversal_status", 804.9),
    ("transaction_amount", 861.2),
    ("settlement_debit", 931.0),
    ("settlement_credit", 996.1),
    ("balance_before", 1061.3),
    ("balance_after", 1118.3),
    ("charge", 1175.4),
    ("beneficiary", 1221.8),
    ("beneficiary_institution", 1291.8),
    ("source", 1360.9),
    ("source_institution", 1454.4),
    ("narration", 1523.5),
]

MONEY_FIELDS = (
    "transaction_amount",
    "settlement_debit",
    "settlement_credit",
    "balance_before",
    "balance_after",
    "charge",
)


def _clean(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\x00", " ")
    return re.sub(r"\s+", " ", text).strip()


def _money(value: Any) -> float:
    text = _clean(value).replace(",", "").replace("₦", "")
    if not text or text in {"-", "--", "N/A"}:
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = re.sub(r"[^\d.\-]", "", text)
    if not text:
        return 0.0
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return 0.0
    return float(-abs(amount) if negative else amount)


def _column_for_x(x0: float) -> str:
    selected = COLUMN_STARTS[0][0]
    for name, start in COLUMN_STARTS:
        if x0 + 0.1 >= start:
            selected = name
        else:
            break
    return selected


def _join_words(words: List[Dict[str, Any]], field: str) -> str:
    if not words:
        return ""
    words = sorted(words, key=lambda word: (word["page"], word["top"], word["x0"]))
    lines: List[List[Dict[str, Any]]] = []
    for word in words:
        if (
            not lines
            or lines[-1][-1]["page"] != word["page"]
            or abs(float(lines[-1][-1]["top"]) - float(word["top"])) > 2.5
        ):
            lines.append([word])
        else:
            lines[-1].append(word)
    line_text = [
        " ".join(item["text"] for item in sorted(line, key=lambda item: item["x0"]))
        for line in lines
    ]
    if field == "date":
        return re.sub(r"\s+", "", "".join(line_text))
    return _clean(" ".join(line_text))


def _parse_record(words: List[Dict[str, Any]], record_number: int) -> Dict[str, Any]:
    buckets: Dict[str, List[Dict[str, Any]]] = {name: [] for name, _ in COLUMN_STARTS}
    for word in words:
        buckets[_column_for_x(float(word["x0"]))].append(word)
    raw = {name: _join_words(buckets[name], name) for name, _ in COLUMN_STARTS}

    raw_timestamp = raw["date"]
    try:
        timestamp = datetime.fromisoformat(raw_timestamp)
    except ValueError as exc:
        raise ValueError(
            f"Moniepoint record {record_number} has an invalid timestamp: {raw_timestamp!r}"
        ) from exc

    description = _clean(raw["narration"])
    page_start = min(int(word["page"]) for word in words)
    page_end = max(int(word["page"]) for word in words)
    transaction = {
        "date": timestamp.strftime("%d-%b-%Y"),
        "value_date": timestamp.strftime("%d-%b-%Y"),
        "transaction_time": raw_timestamp,
        "description": description,
        "remarks": description,
        "reference": raw["transaction_ref"],
        "debit": _money(raw["settlement_debit"]),
        "credit": _money(raw["settlement_credit"]),
        "balance": _money(raw["balance_after"]),
        "transaction_amount": _money(raw["transaction_amount"]),
        "charge": _money(raw["charge"]),
        "balance_before": _money(raw["balance_before"]),
        "transaction_type": raw["transaction_type"],
        "transaction_status": raw["transaction_status"],
        "terminal_id": raw["terminal_id"],
        "rrn": raw["rrn"],
        "reversal_status": raw["reversal_status"],
        "beneficiary": raw["beneficiary"],
        "beneficiary_institution": raw["beneficiary_institution"],
        "source": raw["source"],
        "source_institution": raw["source_institution"],
        "category": "Uncategorized",
        "_page": page_start,
        "_page_end": page_end,
    }
    for field in MONEY_FIELDS:
        transaction.setdefault(field, _money(raw[field]))
    return transaction


def _region_text(
    words: List[Dict[str, Any]],
    x_min: float,
    x_max: float,
    top_min: float,
    top_max: float,
) -> str:
    selected = [
        {**word, "page": 1}
        for word in words
        if x_min <= float(word["x0"]) < x_max
        and top_min <= float(word["top"]) < top_max
    ]
    return _join_words(selected, "metadata")


def _normalise_period(value: str) -> str:
    dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", value or "")
    if len(dates) != 2:
        return _clean(value)
    parsed = [datetime.strptime(date, "%d/%m/%Y").strftime("%d-%b-%Y") for date in dates]
    return f"{parsed[0]} to {parsed[1]}"


def parse_moniepoint_metadata(page: Any) -> Dict[str, Any]:
    text = page.extract_text() or ""
    words = page.extract_words(
        x_tolerance=1,
        y_tolerance=2,
        use_text_flow=False,
        keep_blank_chars=False,
    )

    def summary_money(label: str) -> float | None:
        match = re.search(rf"{label}\s+([\d,]+\.\d{{2}})", text, re.I)
        return _money(match.group(1)) if match else None

    account_number = _region_text(words, 170, 800, 190, 207)
    metadata: Dict[str, Any] = {
        "bank": "moniepoint",
        "currency": "NGN",
        "account_name": _region_text(words, 170, 800, 172, 190),
        "account_no": account_number,
        "account_number": account_number,
        "statement_period": _normalise_period(_region_text(words, 170, 800, 222, 239)),
        "address": _region_text(words, 170, 800, 238, 295),
        "method": "moniepoint_coordinates",
    }
    fields = {
        "opening_balance": summary_money(r"Opening\s+Balance"),
        "statement_total_debit": summary_money(r"Total\s+Debits?"),
        "statement_total_credit": summary_money(r"Total\s+Credits?"),
        "closing_balance": summary_money(r"Closing\s+Balance"),
    }
    metadata.update({key: value for key, value in fields.items() if value is not None})
    return metadata


def is_moniepoint_statement(text: str) -> bool:
    normalized = _clean(text).upper()
    return (
        "ACCOUNT STATEMENT" in normalized
        and "ACCOUNT SUMMARY" in normalized
        and "BUSINESS NAME" in normalized
        and "TRANSACTION REF" in normalized
        and "RRN" in normalized
        and "TERMINAL" in normalized
        and "REVERSAL" in normalized
        and "SETTLEMENT" in normalized
        and "BENEFICIARY" in normalized
    )


def extract_moniepoint_via_coordinates(
    pdf_path: Path,
    metadata: Dict[str, Any],
    pdf: pdfplumber.PDF | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    auto_close = False
    if pdf is None:
        pdf = pdfplumber.open(pdf_path)
        auto_close = True

    transactions: List[Dict[str, Any]] = []
    current_words: List[Dict[str, Any]] = []
    try:
        metadata.update(parse_moniepoint_metadata(pdf.pages[0]))
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(
                x_tolerance=1,
                y_tolerance=2,
                use_text_flow=False,
                keep_blank_chars=False,
            )
            for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
                is_start = (
                    float(word["x0"]) < 80
                    and re.fullmatch(r"\d{4}-", str(word["text"])) is not None
                )
                if is_start:
                    if current_words:
                        transactions.append(_parse_record(current_words, len(transactions) + 1))
                    current_words = []
                if current_words or is_start:
                    current_words.append({**word, "page": page_number})

        if current_words:
            transactions.append(_parse_record(current_words, len(transactions) + 1))

        metadata["transaction_count_extracted"] = len(transactions)
        return transactions, metadata
    finally:
        if auto_close:
            pdf.close()
