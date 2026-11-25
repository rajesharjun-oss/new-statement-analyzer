"""Wema PDF layout with a separate account summary and a ruled ledger."""
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import re

import fitz


DATE = r"\d{2}-[A-Za-z]{3}-\d{4}"
AMOUNT = re.compile(r"[-\u2212]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2,3}")
HEADINGS = ("tran.date", "ref/chq.no", "narration", "debit", "credit", "balance")


def _spans(page):
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES
    return [
        (fitz.Rect(span["bbox"]), span["text"].strip(), span["color"])
        for block in page.get_text("dict", flags=flags)["blocks"]
        for line in block["lines"]
        for span in line["spans"]
        if span["text"].strip()
    ]


def _rectangles(page):
    return [item[1] for drawing in page.get_drawings()
            for item in drawing["items"] if item[0] == "re"]


def _contents(spans, rect):
    return sorted(
        ((box, text) for box, text, _ in spans
         if rect.x0 <= box.x0 < rect.x1 and rect.y0 <= (box.y0 + box.y1) / 2 < rect.y1),
        key=lambda value: (round(value[0].y0, 1), value[0].x0),
    )


def _amount(text):
    if AMOUNT.fullmatch(text):
        return Decimal(text.replace(",", "").replace("\u2212", "-"))
    return None


def _narration(cell):
    lines = defaultdict(list)
    for box, text in cell:
        lines[round(box.y0, 1)].append((box.x0, text))
    return "\n".join(" ".join(text for _, text in sorted(lines[y])) for y in sorted(lines))


def _cover(page):
    text = " ".join(page.get_text().split())
    if not re.search(r"\bwema\s*bank\b", text, re.I) or not re.search(r"\bsummary of account\(s\)", text, re.I):
        return None
    period = re.search(rf"\bstatement period\s*:\s*({DATE})\s+to\s+({DATE})", text, re.I)
    if not period:
        return None

    spans = _spans(page)
    bands = defaultdict(list)
    for rect in _rectangles(page):
        if rect.width >= 40:
            bands[(round(rect.y0, 1), round(rect.y1, 1))].append(rect)

    summaries = []
    for rects in bands.values():
        if len(rects) != 6:
            continue
        rects.sort(key=lambda rect: rect.x0)
        cells = [" ".join(t for _, t in _contents(spans, rect)) for rect in rects]
        if not cells[0] or not cells[1] or not re.fullmatch(r"\d{10,12}", cells[2]):
            continue
        credit, debit, available = map(_amount, cells[3:])
        if None not in (credit, debit, available):
            summaries.append({
                "account_name": cells[0],
                "account_number": cells[2],
                "account_no": cells[2],
                "account_type": cells[1],
                "statement_period": f"{period[1]} to {period[2]}",
                "statement_total_debit": float(debit),
                "statement_total_credit": float(credit),
                "available_balance": float(available),
            })
    return summaries[0] if len(summaries) == 1 else None


def _table_columns(spans, rectangles):
    for anchor, text, _ in spans:
        if text.casefold() != HEADINGS[0]:
            continue
        line = sorted(
            [(box, token.casefold()) for box, token, _ in spans if abs(box.y0 - anchor.y0) < 1.5],
            key=lambda item: item[0].x0,
        )
        if tuple(token for _, token in line) != HEADINGS:
            continue
        columns = []
        for box, _ in line:
            header_cells = [r for r in rectangles
                            if r.x0 <= box.x0 < r.x1 and r.y0 <= box.y0 < r.y1]
            if not header_cells:
                break
            columns.append(min(header_cells, key=lambda rect: rect.width))
        if len(columns) == len(HEADINGS) and all(
            abs(a.x1 - b.x0) < 1 for a, b in zip(columns, columns[1:])
        ):
            return columns
    return None


def _page_transactions(page):
    spans = _spans(page)
    rectangles = _rectangles(page)
    columns = _table_columns(spans, rectangles)
    if columns is None:
        return None
    first = columns[0]
    bands = sorted(
        {(r.y0, r.y1) for r in rectangles if r.y0 >= first.y1 - 0.25
         and abs(first.x0 - r.x0) < 0.5 and abs(first.x1 - r.x1) < 0.5},
    )
    starts = [top for top, _ in bands]
    edges = [r.x0 for r in columns] + [columns[-1].x1]
    cells = [[[] for _ in HEADINGS] for _ in bands]
    date_count = 0
    for box, text, color in spans:
        if color != 0:
            continue
        if first.x0 <= box.x0 < first.x1 and box.y0 >= first.y1 and re.fullmatch(DATE, text):
            date_count += 1
        midpoint = (box.y0 + box.y1) / 2
        row = bisect_right(starts, midpoint) - 1
        col = bisect_right(edges, box.x0) - 1
        if row >= 0 and midpoint < bands[row][1] and 0 <= col < len(HEADINGS):
            cells[row][col].append((box, text))

    transactions = []
    complete = True
    for row in cells:
        dates = [(box, text) for box, text in row[0] if re.fullmatch(DATE, text)]
        if not dates:
            continue
        if len(dates) != 1:
            complete = False
            continue
        anchor, date = dates[0]
        # Money is printed at the same baseline as the date. Avoid borrowing
        # any amounts from the document footer, which overlaps some grid rows.
        raw_money = [
            [text for box, text in cell if abs(box.y0 - anchor.y0) < 2 and AMOUNT.fullmatch(text)]
            for cell in row[-3:]
        ]
        if any(len(values) != 1 for values in raw_money):
            complete = False
            continue
        debit, credit, balance = (_amount(values[0]) for values in raw_money)
        reference = " ".join(text for _, text in sorted(row[1], key=lambda item: item[0].x0))
        narration = _narration(row[2])
        transactions.append({
            "date": datetime.strptime(date, "%d-%b-%Y").strftime("%d-%b-%Y"),
            "reference": reference,
            "description": narration,
            "remarks": narration,
            "debit": debit,
            "credit": credit,
            "balance": balance,
            "_page": page.number + 1,
        })
    return transactions, complete and date_count == len(transactions)


def _printed_closing(page):
    spans = _spans(page)
    for rect, text, color in spans:
        if re.fullmatch(r"closing\s+balance\s*:", text, re.I):
            amounts = [value for box, token, token_color in spans
                       if token_color == color and box.x0 >= rect.x1 and abs(box.y0 - rect.y0) < 1.5
                       and (value := _amount(token)) is not None]
            if len(amounts) == 1:
                return amounts[0]
    return None


def extract_wema_cover_statement(pdf_path, max_pages=None):
    """Return None for other Wema layouts; keep source balances separate from the cover's available balance."""
    with fitz.open(pdf_path) as doc:
        if doc.page_count < 2 or doc.needs_pass:
            return None
        summary = _cover(doc[0])
        if summary is None:
            return None
        first_page = _page_transactions(doc[1])
        if first_page is None:
            return None
        currency = re.search(r"\bcurrency\s*:\s*([A-Z]{3})\b", doc[1].get_text(), re.I)
        transactions = []
        page_limit = min(max_pages or doc.page_count, doc.page_count)
        complete = page_limit == doc.page_count
        for index in range(1, page_limit):
            page = first_page if index == 1 else _page_transactions(doc[index])
            if page is None:
                complete = False
                continue
            rows, page_complete = page
            transactions.extend(rows)
            complete = complete and page_complete
        closing = _printed_closing(doc[-1])

    summary.update(
        bank="wema",
        currency=currency[1].upper() if currency else "NGN",
        method="wema_summary_cover",
        validation_tolerance="0.004",
        opening_balance=None,
        closing_balance=float(closing) if closing is not None else None,
    )
    if not complete:
        summary["extraction_issue"] = "Some statement rows or pages could not be read."
    elif transactions:
        first = transactions[0]
        opening = first["balance"] + first["debit"] - first["credit"]
        summary.update(opening_balance=float(opening), opening_balance_source="first_transaction")
        balance = opening
        for row in transactions:
            if balance + row["credit"] - row["debit"] != row["balance"]:
                summary["extraction_issue"] = "The extracted running balances do not reconcile."
                break
            balance = row["balance"]
        if closing is not None and transactions[-1]["balance"] != closing:
            summary["extraction_issue"] = "The last transaction balance does not match the printed closing balance."

    for row in transactions:
        for field in ("debit", "credit", "balance"):
            row[field] = float(row[field])
    return transactions, summary
