"""Wema's landscape-style ruled statement with repeated account summaries."""
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import re

import fitz

from wema_cover_engine import _amount


HEADER = "tran date value date narration tran id cheque no withdrawals deposits balance"
DATE = re.compile(r"\d{2}-\d{2}-\d{4}")


def _text(words, separator=" "):
    lines = []
    for word in sorted(words, key=lambda w: (w[1], w[0])):
        if not lines or abs(word[1] - lines[-1][0][1]) > 2:
            lines.append([])
        lines[-1].append(word)
    return separator.join(" ".join(w[4] for w in sorted(line, key=lambda w: w[0])) for line in lines)


def _line_boxes(page):
    groups = defaultdict(set)
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                _, a, b = item
                if abs(a.y - b.y) < 0.1:
                    groups[round(a.y, 1)].add(tuple(sorted((round(a.x, 1), round(b.x, 1)))))
    return groups


def _layout(words, lines):
    header = next(
        (w for w in words if w[4].casefold() == "tran" and w[0] < 80
         and _text(x for x in words if abs(w[1] - x[1]) < 0.5).casefold() == HEADER),
        None,
    )
    if header is None:
        return None
    for y, spans in sorted(lines.items()):
        if not header[1] < y < header[3] + 20:
            continue
        columns = sorted(spans)
        if len(columns) != 8 or not columns[0][0] <= header[0] < columns[0][1]:
            continue
        if all(abs(a[1] - b[0]) < 1 for a, b in zip(columns, columns[1:])):
            return columns, y
    return None


def _summary(words):
    # This layout prints each header summary field in its own fixed cell.
    def cell(x0, x1, y0, y1):
        return _text(w for w in words if x0 <= w[0] < x1 and y0 <= w[1] < y1)

    if not cell(420, 560, 112, 118).casefold().startswith("statement period"):
        return None
    if not cell(420, 560, 212, 219).casefold().startswith("total debit"):
        return None
    if not cell(650, 750, 212, 219).casefold().startswith("total credit"):
        return None

    info = {
        "account_name": cell(130, 420, 116, 121),
        "account_number": cell(130, 420, 141, 148),
        "account_type": cell(130, 420, 191, 199),
        "currency": cell(130, 420, 166, 173),
        "statement_period": cell(560, 866, 119, 125),
    }
    if not info["account_name"] or not re.fullmatch(r"\d{10,12}", info["account_number"]):
        return None
    for field, box in (
        ("opening_balance", (560, 651, 149, 155)),
        ("closing_balance", (756, 866, 149, 155)),
        ("statement_total_debit", (560, 651, 205, 220)),
        ("statement_total_credit", (756, 866, 205, 220)),
        ("statement_debit_count", (560, 651, 244, 250)),
        ("statement_credit_count", (756, 866, 244, 250)),
    ):
        text = cell(*box)
        value = (int(text.replace(",", "")) if re.fullmatch(r"[\d,]+", text) else None) if field.endswith("count") else _amount(text)
        if value is None:
            return None
        info[field] = value
    return info


def _parse_page(words, lines, layout, page_number):
    columns, header_bottom = layout
    edges = [span[0] for span in columns] + [columns[-1][1]]
    bands = sorted(y for y, spans in lines.items() if y >= header_bottom and columns[0] in spans)
    cells = [[[] for _ in columns] for _ in bands[1:]]
    expected = 0
    for w in words:
        row = bisect_right(bands, (w[1] + w[3]) / 2) - 1
        col = bisect_right(edges, w[0]) - 1
        if w[1] > header_bottom and col == 0 and DATE.fullmatch(w[4]):
            expected += 1
        if 0 <= row < len(cells) and 0 <= col < len(columns):
            cells[row][col].append(w)

    transactions = []
    for cells_in_row in cells:
        date, value_date, narration, reference, cheque, debit, credit, balance = (
            _text(words, separator="\n" if j == 2 else " ") for j, words in enumerate(cells_in_row)
        )
        if not (DATE.fullmatch(date) and DATE.fullmatch(value_date)):
            continue
        amounts = tuple(map(_amount, (debit, credit, balance)))
        if None in amounts:
            continue
        transactions.append({
            "date": datetime.strptime(date, "%d-%m-%Y").strftime("%d-%b-%Y"),
            "value_date": datetime.strptime(value_date, "%d-%m-%Y").strftime("%d-%b-%Y"),
            "description": narration,
            "remarks": narration,
            "reference": reference,
            "cheque_number": cheque,
            "debit": amounts[0],
            "credit": amounts[1],
            "balance": amounts[2],
            "_page": page_number,
        })
    return transactions, expected == len(transactions)


def extract_wema_ruled_statement(pdf_path, max_pages=None):
    with fitz.open(pdf_path) as doc:
        if not doc.page_count or doc.needs_pass:
            return None
        first_words = doc[0].get_text("words")
        summary = _summary(first_words)
        if summary is None:
            return None
        lines = _line_boxes(doc[0])
        layout = _layout(first_words, lines)
        if layout is None:
            return None
        limit = min(max_pages or doc.page_count, doc.page_count)
        complete = limit == doc.page_count
        transactions = []
        for index in range(limit):
            words = first_words if index == 0 else doc[index].get_text("words")
            page_lines = lines if index == 0 else _line_boxes(doc[index])
            page_layout = layout if index == 0 else _layout(words, page_lines)
            if page_layout is None:
                complete = False
                continue
            rows, page_complete = _parse_page(words, page_lines, page_layout, index + 1)
            complete = complete and page_complete
            transactions.extend(rows)

    previous = summary["opening_balance"]
    if transactions:
        first = transactions[0]
        if first["debit"] == first["credit"] == 0 and first["balance"] == previous:
            first["_opening_balance_row"] = True
    totals = (sum(bool(t["debit"]) for t in transactions), sum(bool(t["credit"]) for t in transactions))
    if not complete:
        summary["extraction_issue"] = "Some statement rows or pages could not be read."
    elif totals != (summary["statement_debit_count"], summary["statement_credit_count"]):
        summary["extraction_issue"] = "Extracted transaction counts do not match the statement."
    else:
        for transaction in transactions:
            if previous + transaction["credit"] - transaction["debit"] != transaction["balance"]:
                summary["extraction_issue"] = "The extracted running balances do not reconcile."
                break
            previous = transaction["balance"]
        if previous != summary["closing_balance"]:
            summary.setdefault("extraction_issue", "The last transaction balance does not match the printed closing balance.")

    for row in transactions:
        for key in ("debit", "credit", "balance"):
            row[key] = float(row[key])
    summary.update(bank="wema", account_no=summary["account_number"], method="wema_ruled", validation_tolerance="0.004")
    return transactions, {key: float(value) if isinstance(value, Decimal) else value for key, value in summary.items()}
