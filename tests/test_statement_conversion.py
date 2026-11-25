from contextlib import redirect_stdout
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import main
from statement_conversion import build_statement_workbook, XLSX_MIME
from tests.test_wema_cover_engine import create_statement


class StatementConversionTests(unittest.TestCase):
    def post_pdf(self, path, **fields):
        with TestClient(main.app) as client, redirect_stdout(StringIO()):
            return client.post("/convert", data=fields, files={
                "file": ("synthetic-statement.pdf", path.read_bytes(), "application/pdf"),
            })

    def test_single_plain_workbook_with_typed_source_columns(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "example.pdf"
            create_statement(source)
            with patch("main.categorize_transactions", side_effect=AssertionError("Categorization must not run")):
                response = self.post_pdf(source)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], XLSX_MIME)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-transaction-count"], "2")
        self.assertEqual(response.headers["x-statement-check"], "matched")
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(workbook.sheetnames, ["Transactions"])
        sheet = workbook.active
        self.assertEqual(sheet["B2"].value, "0001234567")
        self.assertEqual([c.value for c in sheet[11]], [
            "Transaction Date", "Cheque / Transaction No.", "Narration", "Debit", "Credit", "Balance",
        ])
        self.assertEqual(sheet["A12"].value, datetime(2025, 1, 6))
        self.assertEqual(sheet["B12"].value, "0000042")
        self.assertEqual(sheet["E12"].value, 1500.5)
        self.assertEqual(sheet["E12"].number_format, "#,##0.000")
        self.assertEqual(sheet["C13"].value, "Supplier payment\nAdditional narration")
        self.assertTrue(all(c.fill.patternType is None for row in sheet for c in row))
        workbook.close()

    def test_password_required_wrong_then_correct(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "locked.pdf"
            create_statement(source, password="test-only-password")
            for fields in ({}, {"password": "incorrect"}):
                response = self.post_pdf(source, **fields)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"]["code"], "pdf_password_required")
            self.assertEqual(self.post_pdf(source, password="test-only-password").status_code, 200)

    def test_do_not_download_unreconciled_rows(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "broken.pdf"
            create_statement(source, broken_balance=True)
            response = self.post_pdf(source)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "statement_mismatch")
        self.assertNotIn("content-disposition", response.headers)

    def test_invalid_bank_file_type_size_and_disabled_analysis(self):
        with TestClient(main.app) as client, patch.object(main, "ENABLE_LEGACY_ANALYSIS", False):
            self.assertEqual(client.post("/analyze").status_code, 404)
            self.assertEqual(client.post("/classify-analysis").status_code, 404)
            file = ("sample.pdf", b"not-a-pdf", "application/pdf")
            self.assertEqual(client.post("/convert", files={"file": file}).status_code, 400)
            self.assertEqual(client.post("/convert", files={"file": file}, data={"bank": "invalid"}).status_code, 400)
            with patch.object(main, "MAX_UPLOAD_BYTES", 6):
                self.assertEqual(client.post("/convert", files={"file": file}).status_code, 413)

    def test_multiple_accounts_stay_on_one_sheet_and_formulas_are_text(self):
        data = [{"metadata": {"account_name": "=1+1", "account_type": label},
                 "transactions": [{"date": "01-Jan-2025", "description": "=1+1",
                                   "debit": 1, "credit": 0, "balance": 10}]} for label in ("Wallet", "Savings")]
        workbook = load_workbook(BytesIO(build_statement_workbook(data)))
        self.assertEqual(workbook.sheetnames, ["Transactions"])
        values = [cell for row in workbook.active for cell in row if cell.value == "=1+1"]
        self.assertEqual(len(values), 4)
        self.assertTrue(all(cell.data_type == "s" for cell in values))
        workbook.close()


if __name__ == "__main__":
    unittest.main()
