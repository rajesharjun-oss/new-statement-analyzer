import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from wema_engine import (  # noqa: E402
    build_wema_description,
    detect_wema_columns_in_pages,
    get_wema_header_scan_limit,
    repair_wema_transaction_descriptions,
)


class FakePage:
    def __init__(self, words):
        self._words = words

    def extract_words(self, *args, **kwargs):
        return self._words


class FakePdf:
    def __init__(self, pages):
        self.pages = pages


def word(text, x0, x1, top=100):
    return {"text": text, "x0": float(x0), "x1": float(x1), "top": float(top)}


class WemaEngineTests(unittest.TestCase):
    def test_detect_wema_columns_scans_past_summary_pages(self):
        header_words = [
            word("Tran", 20, 48),
            word("Date", 50, 82),
            word("Narration", 150, 220),
            word("ID", 300, 318),
            word("Withdrawals", 420, 500),
            word("Deposits", 560, 625),
            word("Balance", 690, 750),
        ]
        fake_pdf = FakePdf([
            FakePage([]),
            FakePage([word("Account", 20, 80), word("Summary", 90, 160)]),
            FakePage(header_words),
        ])

        cuts, page_index = detect_wema_columns_in_pages(fake_pdf, max_pages=3)

        self.assertEqual(page_index, 2)
        self.assertIsNotNone(cuts)
        self.assertIn("description", cuts)
        self.assertIn("debit", cuts)

    def test_detect_wema_columns_respects_scan_limit(self):
        header_words = [
            word("Tran", 20, 48),
            word("Date", 50, 82),
            word("Narration", 150, 220),
            word("ID", 300, 318),
            word("Withdrawals", 420, 500),
            word("Deposits", 560, 625),
            word("Balance", 690, 750),
        ]
        fake_pdf = FakePdf([FakePage([]), FakePage([]), FakePage(header_words)])

        cuts, page_index = detect_wema_columns_in_pages(fake_pdf, max_pages=2)

        self.assertIsNone(cuts)
        self.assertIsNone(page_index)

    def test_build_wema_description_uses_row_text_when_narration_slice_is_empty(self):
        cuts = {
            "date": (15.0, 72.0),
            "description": (150.0, 260.0),
            "tran_id": (260.0, 390.0),
            "debit": (420.0, 550.0),
            "credit": (555.0, 680.0),
            "balance": (685.0, 1000.0),
        }
        row_words = [
            word("02-Mar-2026", 18, 70),
            word("TRANSFER", 95, 160),
            word("FROM", 166, 198),
            word("CUSTOMER", 205, 255),
            word("N0129/AT68_TRF2MPTHYMYX2027643", 265, 388),
            word("7,000.00", 570, 630),
            word("2,947,000.00", 700, 780),
        ]
        row_data = {
            "description": "",
            "tran_id": "N0129/AT68_TRF2MPTHYMYX2027643",
        }

        description = build_wema_description(row_words, cuts, row_data)

        self.assertIn("TRANSFER FROM CUSTOMER", description)
        self.assertIn("N0129/AT68_TRF2MPTHYMYX2027643", description)
        self.assertNotIn("02-Mar-2026", description)
        self.assertNotIn("7,000.00", description)

    def test_repair_wema_transaction_descriptions_uses_reference_as_last_resort(self):
        rows = [{"description": "", "reference": "N029/AT68_TRF2MPTHYMYX20276470"}]

        repaired = repair_wema_transaction_descriptions(rows)

        self.assertEqual(repaired[0]["description"], "N029/AT68_TRF2MPTHYMYX20276470")
        self.assertEqual(repaired[0]["remarks"], "N029/AT68_TRF2MPTHYMYX20276470")

    def test_wema_header_scan_limit_is_configurable_and_bounded(self):
        with patch.dict(os.environ, {"WEMA_HEADER_SCAN_PAGES": "40"}):
            self.assertEqual(get_wema_header_scan_limit(100), 40)
        with patch.dict(os.environ, {"WEMA_HEADER_SCAN_PAGES": "500"}):
            self.assertEqual(get_wema_header_scan_limit(100), 50)
        with patch.dict(os.environ, {"WEMA_HEADER_SCAN_PAGES": "not-a-number"}):
            self.assertEqual(get_wema_header_scan_limit(8), 8)


if __name__ == "__main__":
    unittest.main()