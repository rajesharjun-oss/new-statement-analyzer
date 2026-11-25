"""Prepare an uncategorized, single-worksheet statement workbook."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import math
import re

import fitz
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from excel_generator import clean_for_excel
from pdf_extractor import extract_transactions
from validation import validate_totals


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SUMMARY = (
    ("Account name", "account_name"), ("Account number", "account_number"),
    ("Account type", "account_type"), ("Currency", "currency"), ("Statement period", "statement_period"),
)
DEBIT = ("Debit", "debit", "money")
CREDIT = ("Credit", "credit", "money")
BALANCE = ("Balance", "balance", "money")
NARRATION = ("Narration", "description", "text")
DATE = ("Transaction Date", "date", "date")
VALUE_DATE = ("Value Date", "value_date", "date")
WEMA_COVER = (DATE, ("Cheque / Transaction No.", "reference", "text"), NARRATION, DEBIT, CREDIT, BALANCE)
WEMA_RULED = (
    DATE, VALUE_DATE, NARRATION, ("Transaction ID", "reference", "text"), ("Cheque No.", "cheque_number", "text"),
    ("Withdrawals", "debit", "money"), ("Deposits", "credit", "money"), BALANCE,
)
CONTROLS = (
    ("Opening balance", "opening_balance"), ("Closing balance", "closing_balance"),
    ("Total debit", "statement_total_debit"), ("Total credit", "statement_total_credit"),
    ("Debit count", "statement_debit_count"), ("Credit count", "statement_credit_count"),
)


class ConversionError(Exception):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code = code
        self.status = status


def _columns(metadata, rows):
    if metadata.get("method") == "wema_summary_cover":
        return WEMA_COVER
    if metadata.get("method") == "wema_ruled":
        return WEMA_RULED
    if metadata.get("method") == "opay_coordinates":
        return (
            ("Trans. Time", "transaction_time", "datetime"), VALUE_DATE,
            ("Description", "description", "text"), DEBIT, CREDIT, ("Balance After", "balance", "money"),
            ("Channel", "channel", "text"), ("Transaction Reference", "reference", "text"),
        )
    if metadata.get("method") == "moniepoint_coordinates":
        return (
            ("Date", "transaction_time", "datetime"), ("Account Name", "account_name", "text"),
            ("Transaction Type", "transaction_type", "text"), ("Transaction Status", "transaction_status", "text"),
            ("Terminal ID", "terminal_id", "text"), ("RRN", "rrn", "text"),
            ("Transaction Ref", "reference", "text"), ("Reversal Status", "reversal_status", "text"),
            ("Transaction Amount", "transaction_amount", "money"),
            ("Settlement Debit", "debit", "money"), ("Settlement Credit", "credit", "money"),
            ("Balance Before", "balance_before", "money"), ("Balance After", "balance", "money"),
            ("Charge", "charge", "money"), ("Beneficiary", "beneficiary", "text"),
            ("Beneficiary Institution", "beneficiary_institution", "text"), ("Source", "source", "text"),
            ("Source Institution", "source_institution", "text"), NARRATION,
        )
    optional = (
        VALUE_DATE, ("Reference", "reference", "text"),
        ("Originating Branch", "originating_branch", "text"),
    )
    return (DATE, *(col for col in optional if any(row.get(col[1]) for row in rows)), NARRATION, DEBIT, CREDIT, BALANCE)


def _literal(cell, value):
    if value is None or value == "":
        return
    cell.value = clean_for_excel(str(value))
    cell.data_type = "s"


def _number(value):
    text = str(value).replace(",", "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    text = re.sub(r"^(?:NGN|N|\u20a6)\s*", "", text, flags=re.I)
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ConversionError("invalid_amount", "One or more amounts could not be read. No workbook was created.") from exc
    if not result.is_finite():
        raise ConversionError("invalid_amount", "One or more amounts could not be read. No workbook was created.")
    return result


def _date(value):
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%y"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def build_statement_workbook(statements):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Transactions"
    bold = Font(name="Arial", size=11, bold=True)
    body = Font(name="Arial", size=11)
    widths = {1: 32, 2: 36}
    row_no = 1

    for statement in statements:
        metadata = statement["metadata"]
        rows = statement["transactions"]
        columns = _columns(metadata, rows)
        number_format = "#,##0.000" if metadata.get("method") == "wema_summary_cover" else "#,##0.00"
        date_format = "dd-mm-yyyy" if metadata.get("method") == "wema_ruled" else "dd-mmm-yyyy"
        fields = CONTROLS
        if metadata.get("method") == "wema_summary_cover":
            fields = (CONTROLS[2], CONTROLS[3], ("Available balance (summary)", "available_balance"), CONTROLS[1])

        for label, key in (*SUMMARY, *fields):
            value = metadata.get(key)
            if key == "account_number" and not value:
                value = metadata.get("account_no")
            if key == "statement_period" and not value:
                value = metadata.get("period")
            if value is None or value == "":
                continue
            sheet.cell(row_no, 1, label).font = bold
            data_cell = sheet.cell(row_no, 2)
            if key.endswith(("debit", "credit", "balance", "_count")):
                data_cell.value = _number(value)
                data_cell.number_format = "0" if key.endswith("_count") else number_format
            else:
                _literal(data_cell, value)
                widths[2] = max(widths[2], min(64, len(str(value)) + 2))
            data_cell.font = body
            row_no += 1
        row_no += 1
        header_row = row_no

        for index, (label, field, kind) in enumerate(columns, 1):
            sheet.cell(row_no, index, label).font = bold
            width = 89 if field == "description" else 39 if field == "reference" else 20
            widths[index] = max(widths.get(index, 0), width, len(label) + 2)
        if sheet.freeze_panes is None:
            sheet.freeze_panes = f"A{row_no + 1}"
        row_no += 1
        for transaction in rows:
            for index, (_, field, kind) in enumerate(columns, 1):
                value = transaction.get(field)
                if field == "description" and not value:
                    value = transaction.get("remarks")
                if field == "account_name" and not value:
                    value = metadata.get("account_name")
                if value is None or value == "":
                    continue
                cell = sheet.cell(row_no, index)
                cell.font = body
                if kind == "money":
                    cell.value = _number(value)
                    cell.number_format = number_format
                elif kind in {"date", "datetime"} and (date := _date(value)) is not None:
                    cell.value = date
                    cell.number_format = date_format + (" hh:mm:ss" if kind == "datetime" else "")
                else:
                    _literal(cell, value)
                if field == "description":
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
                    lines = sum(max(1, math.ceil(len(line) / 78)) for line in str(value).splitlines())
                    if lines > 1:
                        sheet.row_dimensions[row_no].height = min(409, 5 + 15 * lines)
            row_no += 1
        if len(statements) == 1:
            sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(len(columns))}{row_no - 1}"
        row_no += 1

    for index, width in widths.items():
        sheet.column_dimensions[get_column_letter(index)].width = width
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def convert_pdf(content, bank, password, max_pages):
    with TemporaryDirectory(prefix="statement-conversion-") as directory:
        source = Path(directory) / "statement.pdf"
        try:
            with fitz.open(stream=content, filetype="pdf") as document:
                protected = document.needs_pass
                if protected and (not password or not document.authenticate(password)):
                    raise ConversionError(
                        "pdf_password_required",
                        "The PDF password is incorrect." if password else "This PDF requires a password.",
                    )
                if not document.page_count or document.page_count > max_pages:
                    raise ConversionError("pdf_page_limit", f"Use a PDF with 1 to {max_pages} pages.")
                if protected:
                    document.save(source, encryption=fitz.PDF_ENCRYPT_NONE)
                else:
                    source.write_bytes(content)
        except (RuntimeError, ValueError) as exc:
            raise ConversionError("invalid_pdf", "This PDF could not be opened. Try downloading a fresh copy.", 400) from exc
        statements = extract_transactions(source, bank, source_only=True)

    checked = [statement for statement in statements if statement["transactions"]]
    if not checked:
        raise ConversionError("no_transactions", "No transactions could be extracted. Try selecting the issuing bank or using the original statement PDF.")
    if any(not statement["transactions"] and any(
        _number(statement["metadata"].get(key) or 0) != 0
        for key in ("statement_total_debit", "statement_total_credit")
    ) for statement in statements):
        raise ConversionError("incomplete_statement", "One account has printed totals but no extracted transactions. No workbook was created.")
    verified = True
    count = 0
    for statement in checked:
        metadata = statement["metadata"]
        rows = statement["transactions"]
        evidence = validate_totals(rows, {"validation_tolerance": "0.01", **metadata})
        if (
            evidence["totals_match"] is False or metadata.get("extraction_issue")
            or metadata.get("partial_extraction") or metadata.get("transaction_count_match") is False
            or any(row.get("_inferred") for row in rows)
        ):
            raise ConversionError("statement_mismatch", "The extracted rows did not reconcile with the statement. No workbook was created.")
        verified = verified and evidence["totals_match"] is True
        count += sum(not row.get("_opening_balance_row") for row in rows)
    return build_statement_workbook(checked), count, verified
