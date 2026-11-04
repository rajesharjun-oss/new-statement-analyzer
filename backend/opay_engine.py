import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pdfplumber


COLUMN_NAMES = (
    "transaction_time",
    "value_date",
    "description",
    "debit",
    "credit",
    "balance",
    "channel",
    "reference",
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


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


def _normalise_date(value: str, include_time: bool = False) -> str | None:
    text = _clean(value)
    formats = ("%d %b %Y %H:%M:%S",) if include_time else ("%d %b %Y",)
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.isoformat() if include_time else parsed.strftime("%d-%b-%Y")
        except ValueError:
            continue
    return None


def _normalise_period_date(value: str) -> str:
    try:
        return datetime.strptime(_clean(value), "%d %b %Y").strftime("%d-%b-%Y")
    except ValueError:
        return _clean(value)


def _region_text(
    words: List[Dict[str, Any]],
    x_min: float,
    x_max: float,
    top_min: float,
    top_max: float,
) -> str:
    selected = [
        word
        for word in words
        if x_min <= float(word["x0"]) < x_max
        and top_min <= float(word["top"]) < top_max
    ]
    return _clean(
        " ".join(
            str(word["text"])
            for word in sorted(selected, key=lambda item: (item["top"], item["x0"]))
        )
    )


def parse_opay_metadata(
    text: str,
    words: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "bank": "opay",
        "currency": "NGN",
        "method": "opay_coordinates",
    }

    account_number = re.search(r"Account\s+Number\s+(\d{10,12})", text, re.I)
    if account_number:
        metadata["account_no"] = account_number.group(1)
        metadata["account_number"] = account_number.group(1)

    account_name = re.search(
        r"Account\s+Name\s+Account\s+Number\s+Address\s+"
        r"(.+?)\s+\d{10,12}\s+",
        text,
        re.I,
    )
    if account_name:
        metadata["account_name"] = _clean(account_name.group(1))

    address = re.search(
        r"Address\s+([\s\S]*?)(?=Account\s+Number|Wallet\s+Account|Opening\s+Balance)",
        text,
        re.I,
    )
    if address:
        metadata["address"] = _clean(address.group(1))

    period = re.search(
        r"Period\s*:\s*-?\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*-?\s*"
        r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
        text,
        re.I,
    )
    if period:
        metadata["statement_period"] = (
            f"{_normalise_period_date(period.group(1))} to "
            f"{_normalise_period_date(period.group(2))}"
        )

    def summary_money(label: str) -> float | None:
        match = re.search(rf"{label}\s*₦?\s*([\d,]+\.\d{{2}})", text, re.I)
        return _money(match.group(1)) if match else None

    def summary_count(label: str) -> int | None:
        match = re.search(rf"{label}\s+(\d+)", text, re.I)
        return int(match.group(1)) if match else None

    fields = {
        "opening_balance": summary_money(r"Opening\s+Balance"),
        "statement_total_debit": summary_money(r"Total\s+Debit"),
        "statement_total_credit": summary_money(r"Total\s+Credit"),
        "closing_balance": summary_money(r"Closing\s+Balance"),
        "statement_debit_count": summary_count(r"Debit\s+Count"),
        "statement_credit_count": summary_count(r"Credit\s+Count"),
    }
    metadata.update({key: value for key, value in fields.items() if value is not None})

    if words:
        coordinate_fields = {
            "account_name": _region_text(words, 60, 220, 150, 170),
            "account_no": _region_text(words, 220, 380, 150, 170),
            "address": _region_text(words, 380, 550, 150, 180),
            "opening_balance": _money(_region_text(words, 60, 220, 250, 270)),
            "statement_total_debit": _money(_region_text(words, 220, 380, 250, 270)),
            "closing_balance": _money(_region_text(words, 60, 220, 286, 306)),
            "statement_total_credit": _money(_region_text(words, 220, 380, 286, 306)),
        }
        account_no = re.sub(r"\D", "", coordinate_fields["account_no"])
        if account_no:
            coordinate_fields["account_no"] = account_no
            coordinate_fields["account_number"] = account_no
        debit_count = re.search(r"\d+", _region_text(words, 380, 550, 250, 270))
        credit_count = re.search(r"\d+", _region_text(words, 380, 550, 286, 306))
        if debit_count:
            coordinate_fields["statement_debit_count"] = int(debit_count.group())
        if credit_count:
            coordinate_fields["statement_credit_count"] = int(credit_count.group())
        metadata.update(
            {
                key: value
                for key, value in coordinate_fields.items()
                if value not in (None, "")
            }
        )
    return metadata


def is_opay_statement(text: str) -> bool:
    normalized = _clean(text).upper()
    return (
        "ACCOUNT STATEMENT" in normalized
        and ("WALLET ACCOUNT" in normalized or "SAVINGS ACCOUNT" in normalized)
        and "TRANSACTION REFERENCE" in normalized
        and "BALANCE AFTER" in normalized
        and ("OPAY" in normalized or "OPAYWEB.COM" in normalized)
    )


def _cell_groups(page: Any) -> List[Tuple[float, float, List[Dict[str, Any]]]]:
    grouped: Dict[Tuple[float, float], List[Dict[str, Any]]] = defaultdict(list)
    for rect in page.rects:
        x0 = float(rect["x0"])
        x1 = float(rect["x1"])
        if not (60.0 <= x0 <= 480.0 and 70.0 <= x1 <= 550.0):
            continue
        grouped[(round(float(rect["top"]), 1), round(float(rect["bottom"]), 1))].append(rect)

    valid: List[Tuple[float, float, List[Dict[str, Any]]]] = []
    for (top, bottom), rects in grouped.items():
        ordered = sorted(rects, key=lambda item: float(item["x0"]))
        if len(ordered) != 8:
            continue
        if not (65.0 <= float(ordered[0]["x0"]) <= 68.5):
            continue
        if not (540.0 <= float(ordered[-1]["x1"]) <= 544.0):
            continue
        valid.append((top, bottom, ordered))
    return sorted(valid, key=lambda item: item[0])


def _layout_signature(group: Tuple[float, float, List[Dict[str, Any]]]) -> Tuple[float, ...]:
    return tuple(round(float(rect["x0"]), 1) for rect in group[2])


def _page_segments(page: Any, page_index: int, page_count: int) -> List[Dict[str, str]]:
    groups = _cell_groups(page)
    if not groups:
        return []

    words = page.extract_words(
        x_tolerance=1,
        y_tolerance=2,
        use_text_flow=False,
        keep_blank_chars=False,
    )
    clusters: List[List[Tuple[float, float, List[Dict[str, Any]]]]] = []
    for group in groups:
        if not clusters or _layout_signature(clusters[-1][-1]) != _layout_signature(group):
            clusters.append([group])
        else:
            clusters[-1].append(group)

    account_headings = sorted(
        float(word["top"])
        for word in words
        if _clean(word.get("text")).upper() in {"SAVINGS", "WALLET"}
        and float(word["x0"]) < 120
    )
    segments: List[Dict[str, str]] = []
    for cluster_index, cluster in enumerate(clusters):
        first_rects = cluster[0][2]
        x_bounds = [float(rect["x0"]) for rect in first_rects]
        x_bounds.append(float(first_rects[-1]["x1"]))
        section = "wallet" if x_bounds[1] < 132.0 else "savings"

        region_start = cluster[0][0]
        if cluster_index == 0 and page_index > 0:
            region_start = 36.0

        if cluster_index < len(clusters) - 1:
            next_start = clusters[cluster_index + 1][0][0]
            headings = [
                top
                for top in account_headings
                if cluster[-1][1] < top < next_start
            ]
            region_end = (min(headings) - 10.0) if headings else next_start
        elif page_index < page_count - 1:
            region_end = 756.0
        else:
            region_end = cluster[-1][1]

        y_bounds = {
            value
            for top, bottom, _rects in cluster
            for value in (top, bottom)
            if region_start <= value <= region_end
        }
        y_bounds.update({region_start, region_end})
        sorted_y = sorted(y_bounds)

        region_segments: List[Dict[str, str]] = []
        for top, bottom in zip(sorted_y, sorted_y[1:]):
            buckets: List[List[Dict[str, Any]]] = [[] for _ in COLUMN_NAMES]
            for word in words:
                word_mid = (
                    float(word["top"]) + float(word.get("bottom", word["top"]))
                ) / 2
                if not (top <= word_mid < bottom):
                    continue
                x0 = float(word["x0"])
                for index, (left, right) in enumerate(zip(x_bounds, x_bounds[1:])):
                    if left <= x0 < right:
                        buckets[index].append(word)
                        break

            if not any(buckets):
                continue
            segment: Dict[str, str] = {}
            for name, bucket in zip(COLUMN_NAMES, buckets):
                ordered = sorted(bucket, key=lambda item: (item["top"], item["x0"]))
                segment[name] = _clean(
                    " ".join(str(item["text"]) for item in ordered)
                )
            segment["_top"] = str(top)
            segment["_bottom"] = str(bottom)
            segment["_page"] = str(page_index + 1)
            segment["_section"] = section
            region_segments.append(segment)

        for index, segment in enumerate(region_segments):
            segment["_region_first"] = "1" if index == 0 else "0"
            segment["_region_last"] = "1" if index == len(region_segments) - 1 else "0"
        segments.extend(region_segments)
    return segments


def _is_header(segment: Dict[str, str]) -> bool:
    combined = _clean(" ".join(segment.get(name, "") for name in COLUMN_NAMES)).upper()
    return "TRANS. TIME" in combined and "DESCRIPTION" in combined


def _merge_fragment(base: Dict[str, str], fragment: Dict[str, str], prepend: bool) -> None:
    for name in COLUMN_NAMES:
        incoming = _clean(fragment.get(name))
        if not incoming:
            continue
        existing = _clean(base.get(name))
        if name == "reference":
            base[name] = re.sub(
                r"\s+",
                "",
                f"{incoming}{existing}" if prepend else f"{existing}{incoming}",
            )
        else:
            base[name] = _clean(
                f"{incoming} {existing}" if prepend else f"{existing} {incoming}"
            )


def _segment_to_transaction(segment: Dict[str, str]) -> Dict[str, Any] | None:
    timestamp = _normalise_date(segment.get("transaction_time", ""), include_time=True)
    if not timestamp:
        return None
    parsed_timestamp = datetime.fromisoformat(timestamp)
    value_date = _normalise_date(segment.get("value_date", ""))
    description = _clean(segment.get("description"))
    return {
        "date": parsed_timestamp.strftime("%d-%b-%Y"),
        "value_date": value_date or parsed_timestamp.strftime("%d-%b-%Y"),
        "transaction_time": timestamp,
        "description": description,
        "remarks": description,
        "reference": re.sub(r"\s+", "", segment.get("reference", "")),
        "debit": _money(segment.get("debit")),
        "credit": _money(segment.get("credit")),
        "balance": _money(segment.get("balance")),
        "channel": _clean(segment.get("channel")),
        "category": "Uncategorized",
        "_page": int(segment["_page"]),
        "_account_type": segment.get("_section", "wallet"),
    }


def _parse_savings_metadata(page: Any, base_metadata: Dict[str, Any]) -> Dict[str, Any]:
    words = page.extract_words(
        x_tolerance=1,
        y_tolerance=2,
        use_text_flow=False,
        keep_blank_chars=False,
    )
    savings = next(
        (
            word
            for word in words
            if _clean(word.get("text")).upper() == "SAVINGS"
            and float(word["x0"]) < 120
        ),
        None,
    )
    if savings is None:
        return {}
    top = float(savings["top"])
    period = _region_text(words, 220, 380, top - 5, top + 18)
    metadata = {
        **base_metadata,
        "bank": "opay",
        "account_type": "Savings Account",
        "statement_period": parse_opay_metadata(f"Period: {period}").get(
            "statement_period",
            base_metadata.get("statement_period"),
        ),
        "opening_balance": _money(_region_text(words, 60, 220, top + 32, top + 52)),
        "statement_total_debit": _money(_region_text(words, 220, 380, top + 32, top + 52)),
        "closing_balance": _money(_region_text(words, 60, 220, top + 68, top + 90)),
        "statement_total_credit": _money(_region_text(words, 220, 380, top + 68, top + 90)),
        "method": "opay_coordinates",
    }
    debit_count = re.search(r"\d+", _region_text(words, 380, 550, top + 32, top + 52))
    credit_count = re.search(r"\d+", _region_text(words, 380, 550, top + 68, top + 90))
    if debit_count:
        metadata["statement_debit_count"] = int(debit_count.group())
    if credit_count:
        metadata["statement_credit_count"] = int(credit_count.group())
    return metadata


def extract_opay_via_coordinates(
    pdf_path: Path,
    metadata: Dict[str, Any],
    pdf: pdfplumber.PDF | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    auto_close = False
    if pdf is None:
        pdf = pdfplumber.open(pdf_path)
        auto_close = True

    transactions: List[Dict[str, Any]] = []
    transactions_by_section: Dict[str, List[Dict[str, Any]]] = {
        "wallet": [],
        "savings": [],
    }
    pending_prefixes: Dict[str, Dict[str, str] | None] = {
        "wallet": None,
        "savings": None,
    }
    try:
        first_page = pdf.pages[0]
        first_words = first_page.extract_words(
            x_tolerance=1,
            y_tolerance=2,
            use_text_flow=False,
            keep_blank_chars=False,
        )
        metadata.update(parse_opay_metadata(first_page.extract_text() or "", first_words))
        page_count = len(pdf.pages)
        for page_index, page in enumerate(pdf.pages):
            segments = _page_segments(page, page_index, page_count)
            for segment in segments:
                if _is_header(segment):
                    continue

                section = segment.get("_section", "wallet")
                section_transactions = transactions_by_section[section]

                transaction = _segment_to_transaction(segment)
                if transaction is not None:
                    if pending_prefixes[section]:
                        _merge_fragment(segment, pending_prefixes[section], prepend=True)
                        pending_prefixes[section] = None
                        transaction = _segment_to_transaction(segment)
                    if transaction is not None:
                        transactions.append(transaction)
                        section_transactions.append(transaction)
                    continue

                has_content = any(_clean(segment.get(name)) for name in COLUMN_NAMES)
                if not has_content:
                    continue

                is_last_segment = segment.get("_region_last") == "1"
                is_first_segment = segment.get("_region_first") == "1"
                if is_last_segment and page_index < page_count - 1:
                    if pending_prefixes[section] is None:
                        pending_prefixes[section] = segment
                    else:
                        _merge_fragment(
                            pending_prefixes[section], segment, prepend=False
                        )
                elif is_first_segment and section_transactions:
                    previous = section_transactions[-1]
                    description = _clean(segment.get("description"))
                    reference = re.sub(r"\s+", "", segment.get("reference", ""))
                    if description:
                        previous["description"] = _clean(
                            f"{previous.get('description', '')} {description}"
                        )
                        previous["remarks"] = previous["description"]
                    if reference:
                        previous["reference"] = f"{previous.get('reference', '')}{reference}"

        expected_count = int(metadata.get("statement_debit_count") or 0) + int(
            metadata.get("statement_credit_count") or 0
        )
        metadata["transaction_count_expected"] = expected_count or None
        wallet_count = len(transactions_by_section["wallet"])
        metadata["transaction_count_extracted"] = wallet_count
        metadata["transaction_count_match"] = (
            expected_count == wallet_count if expected_count else None
        )
        metadata["section_transaction_counts"] = {
            section: len(items)
            for section, items in transactions_by_section.items()
        }
        return transactions, metadata
    finally:
        if auto_close:
            pdf.close()


def extract_opay_statements(
    pdf_path: Path,
    metadata: Dict[str, Any],
    pdf: pdfplumber.PDF | None = None,
) -> List[Dict[str, Any]]:
    auto_close = False
    if pdf is None:
        pdf = pdfplumber.open(pdf_path)
        auto_close = True
    try:
        transactions, wallet_metadata = extract_opay_via_coordinates(
            pdf_path,
            dict(metadata),
            pdf=pdf,
        )
        savings_metadata: Dict[str, Any] = {}
        first_savings = next(
            (
                transaction
                for transaction in transactions
                if transaction.get("_account_type") == "savings"
            ),
            None,
        )
        if first_savings:
            page_index = max(int(first_savings.get("_page") or 1) - 1, 0)
            savings_metadata = _parse_savings_metadata(
                pdf.pages[page_index],
                wallet_metadata,
            )

        results: List[Dict[str, Any]] = []
        for section, account_type, section_metadata in (
            ("wallet", "Wallet Account", wallet_metadata),
            ("savings", "Savings Account", savings_metadata),
        ):
            section_transactions = [
                transaction
                for transaction in transactions
                if transaction.get("_account_type") == section
            ]
            if not section_transactions:
                continue
            account_metadata = {
                **wallet_metadata,
                **section_metadata,
                "account_type": account_type,
            }
            expected_count = int(account_metadata.get("statement_debit_count") or 0) + int(
                account_metadata.get("statement_credit_count") or 0
            )
            account_metadata["transaction_count_expected"] = expected_count or None
            account_metadata["transaction_count_extracted"] = len(section_transactions)
            account_metadata["transaction_count_match"] = (
                expected_count == len(section_transactions) if expected_count else None
            )
            results.append(
                {
                    "transactions": section_transactions,
                    "metadata": account_metadata,
                }
            )
        return results
    finally:
        if auto_close:
            pdf.close()
