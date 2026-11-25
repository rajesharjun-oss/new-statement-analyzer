from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

import fitz
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from statement_conversion import convert_pdf


def create_ruled_statement(path):
    with fitz.open() as doc:
        p = doc.new_page(width=907, height=992)
        for x, top, text in (
            (423, 115, "Statement Period:"),
            (132, 119, "EXAMPLE SERVICES LTD"),
            (563, 121, "01-01-2025 to 31-01-2025"),
            (132, 144, "0001234567"),
            (563, 151, "500.00"),
            (759, 151, "480.00"),
            (132, 169, "NGN"),
            (132, 194, "CURRENT ACCOUNT"),
            (563, 209, "20.00"),
            (759, 215, "0.00"),
            (423, 216, "Total Debit:"),
            (653, 216, "Total Credit:"),
            (563, 246, "1"),
            (759, 246, "0"),
        ):
            p.insert_text((x, top + 8), text, fontsize=8)
        edges = [31, 121, 211, 420, 490, 560, 650, 757, 867]
        for y in (288, 313, 338, 375):
            for left, right in zip(edges, edges[1:]):
                p.draw_line((left, y), (right, y), width=0.3)
        for baseline, values in (
            (301, ("Tran Date", "Value Date", "Narration", "Tran ID", "Cheque No", "Withdrawals", "Deposits", "Balance")),
            (328, ("01-01-2025", "01-01-2025", "Balance brought forward", "", "", "0.00", "0.00", "500.00")),
            (356, ("05-01-2025", "06-01-2025", "Transfer", "0012345", "000042", "20.00", "0.00", "480.00")),
        ):
            for left, text in zip(edges, values):
                if text:
                    p.insert_text((left + 3, baseline), text, fontsize=8)
        p.insert_text((214, 367), "Continuation", fontsize=8)
        doc.save(path)


class WemaRuledTests(unittest.TestCase):
    def test_export_includes_opening_row_and_original_columns(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.pdf"
            create_ruled_statement(path)
            with redirect_stdout(StringIO()):
                output, count, verified = convert_pdf(path.read_bytes(), "auto", "", 700)
        self.assertTrue(verified)
        self.assertEqual(count, 1)
        book = load_workbook(BytesIO(output))
        sheet = book.active
        self.assertEqual(book.sheetnames, ["Transactions"])
        self.assertEqual([c.value for c in sheet[13]], [
            "Transaction Date", "Value Date", "Narration", "Transaction ID", "Cheque No.",
            "Withdrawals", "Deposits", "Balance",
        ])
        self.assertEqual(sheet["C14"].value, "Balance brought forward")
        self.assertEqual(sheet["C15"].value, "Transfer\nContinuation")
        self.assertEqual(sheet["D15"].value, "0012345")
        self.assertEqual(sheet["E15"].value, "000042")
        self.assertEqual(sheet["H15"].value, 480)
        book.close()
