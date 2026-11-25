from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from pdf_extractor import extract_transactions
from validation import validate_totals
from wema_cover_engine import extract_wema_cover_statement


def add_cells(page, edges, top, bottom, values, *, header=False):
    for left, right, value in zip(edges, edges[1:], values):
        fill = (0.3, 0, 0.3) if header else (1, 1, 1)
        page.draw_rect(fitz.Rect(left, top, right, bottom), fill=fill)
        page.insert_text(
            (left + 4, top + 12), value, fontsize=7,
            color=(1, 1, 1) if header else (0, 0, 0),
        )


def create_statement(path, broken_balance=False, password=None):
    with fitz.open() as doc:
        cover = doc.new_page()
        cover.insert_text((25, 65), "WemaBank")
        cover.insert_text((25, 110), "Summary of Account(s)")
        cover.insert_text((25, 130), "Statement Period: 01-Jan-2025 to 31-Jan-2025")
        edges = [25, 155, 245, 310, 390, 470, 565]
        add_cells(cover, edges, 145, 170, (
            "Account Name", "Account Type", "Account Number",
            "Image not found Total Credit", "Image not found Total Debit", "Available Balance",
        ), header=True)
        add_cells(cover, edges, 170, 196, (
            "EXAMPLE SERVICES LTD", "CURRENT ACCOUNT", "0001234567",
            "1,500.50", "20.50", "105.00",
        ))
        ledger_edges = [20, 78, 132, 357, 428, 499, 573]
        for i, values in enumerate((
            ("06-Jan-2025", "0000042", "Opening transfer", "0.00", "1,500.500", "2,000.500"),
            ("07-Jan-2025", "0000043", "Supplier payment", "20.500", "0.00",
             "1,979.000" if broken_balance else "1,980.000"),
        )):
            page = doc.new_page()
            page.insert_text((25, 80), "Currency: NGN", fontsize=8)
            top = 730 if i else 220
            add_cells(page, ledger_edges, top, top + 20,
                      ("Tran.Date", "Ref/Chq.No", "Narration", "Debit", "Credit", "Balance"), header=True)
            add_cells(page, ledger_edges, top + 20, top + 52, values)
            page.insert_text((ledger_edges[2] + 4, top + 44), "Additional narration", fontsize=7)
            page.insert_text((22, top + 40), "Please verify the entries in this statement.", fontsize=7)
            if i:
                page.insert_text((398, top + 33), "Closing Balance :", fontsize=7, color=(0.3, 0, 0.3))
                page.insert_text((512, top + 33), "1,980.000", fontsize=7, color=(0.3, 0, 0.3))
        if password:
            doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=password, user_pw=password)
        else:
            doc.save(path)


class WemaCoverTests(unittest.TestCase):
    def test_auto_and_manual_routes_read_cover_and_overlapping_ledger(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.pdf"
            create_statement(path)
            for bank in ("auto", "wema"):
                with self.subTest(bank=bank), redirect_stdout(StringIO()):
                    statement, = extract_transactions(path, bank_identifier=bank)
                    metadata = statement["metadata"]
                    transactions = statement["transactions"]
                    self.assertEqual(metadata["method"], "wema_summary_cover")
                    self.assertEqual(metadata["account_name"], "EXAMPLE SERVICES LTD")
                    self.assertEqual(metadata["account_number"], "0001234567")
                    self.assertEqual(metadata["available_balance"], 105.0)
                    self.assertEqual(metadata["closing_balance"], 1980.0)
                    self.assertEqual(metadata["opening_balance"], 500.0)
                    self.assertEqual(metadata["statement_total_credit"], 1500.50)
                    self.assertEqual(metadata["statement_total_debit"], 20.50)
                    self.assertEqual([t["reference"] for t in transactions], ["0000042", "0000043"])
                    self.assertEqual([t["_page"] for t in transactions], [2, 3])
                    self.assertEqual(transactions[-1]["description"], "Supplier payment\nAdditional narration")
                    self.assertTrue(validate_totals(transactions, metadata)["totals_match"])

    def test_matching_totals_do_not_mask_running_balance_error(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.pdf"
            create_statement(path, broken_balance=True)
            transactions, metadata = extract_wema_cover_statement(path)
            validation = validate_totals(transactions, metadata)
            self.assertFalse(validation["totals_match"])
            self.assertEqual(validation["debit_diff"], 0.0)
            self.assertEqual(validation["credit_diff"], 0.0)
            self.assertIn("balance", validation["status"])

    def test_page_limit_does_not_report_complete_extraction(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "limited.pdf"
            create_statement(path)
            transactions, metadata = extract_wema_cover_statement(path, max_pages=2)
            self.assertEqual(len(transactions), 1)
            self.assertIn("extraction_issue", metadata)
            self.assertFalse(validate_totals(transactions, metadata)["totals_match"])


if __name__ == "__main__":
    unittest.main()
