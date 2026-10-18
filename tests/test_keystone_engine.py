import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from keystone_engine import (  # noqa: E402
    detect_keystone_layout,
    extract_keystone_via_coordinates,
    parse_keystone_metadata,
)
from pdf_extractor import detect_template  # noqa: E402


def word(text, x0, top, width=None):
    width = width or max(len(text) * 4, 8)
    return {
        "text": text,
        "x0": float(x0),
        "x1": float(x0 + width),
        "top": float(top),
        "bottom": float(top + 8),
    }


def header(top=100):
    return [
        word("Date", 47, top),
        word("V.", 79, top),
        word("Date", 92, top),
        word("Narration", 175, top),
        word("Ref", 289, top),
        word("Debit", 347, top),
        word("Credit", 435, top),
        word("Balance", 522, top),
    ]


class FakePage:
    def __init__(self, words, text=""):
        self._words = words
        self._text = text

    def extract_words(self, **_kwargs):
        return self._words

    def extract_text(self):
        return self._text


class FakePdf:
    def __init__(self, pages):
        self.pages = pages


class KeystoneEngineTests(unittest.TestCase):
    def test_detects_keystone_brand(self):
        self.assertEqual(
            detect_template("www.keystonebankng.com Date V. Date Narration Debit Credit Balance"),
            "keystone",
        )

    def test_parses_keystone_summary_metadata(self):
        text = """
        Summary Statement for 01-Jan-24 To 31-Dec-24 Account No. - 1013085561
        Currency NAIRA
        Account Name                            Opening Balance - 694,819.60
        TEAMAPT LIMITED ATS INCOME ALC          Total Debits - 288.10
        Total Credits - 114,625,312.00
        Closing Balance - 115,319,843.50
        """
        metadata = parse_keystone_metadata(text)
        self.assertEqual(metadata["account_name"], "TEAMAPT LIMITED ATS INCOME ALC")
        self.assertEqual(metadata["account_number"], "1013085561")
        self.assertEqual(metadata["currency"], "NGN")
        self.assertEqual(metadata["statement_period"], "01-Jan-2024 to 31-Dec-2024")
        self.assertEqual(metadata["statement_total_debit"], 288.10)
        self.assertEqual(metadata["statement_total_credit"], 114625312.00)

    def test_detects_columns_and_preserves_cross_page_narration(self):
        first_page_words = header() + [
            word("04Jan24", 38, 120),
            word("04Jan24", 77, 120),
            word("KBLDCIR", 115, 120),
            word("12.00", 465, 120),
            word("694,831.60", 533, 120),
            word("Inc/2401032200006790", 115, 132),
        ]
        shifted_final_page_header = [
            word("Date", 41, 100),
            word("V.", 76, 100),
            word("Narration", 162, 100),
            word("Ref", 278, 100),
            word("Debit", 340, 100),
            word("Credit", 430, 100),
            word("Balance", 521, 100),
        ]
        second_page_words = shifted_final_page_header + [
            word("200007", 98, 120),
            word("DCIR", 128, 120),
            word("05Jan24", 38, 140),
            word("05Jan24", 77, 140),
            word("BANK", 115, 140),
            word("FEE", 145, 140),
            word("288.10", 370, 140),
            word("694,543.50", 533, 140),
        ]
        summary = """
        www.keystonebankng.com
        Summary Statement for 01-Jan-24 To 31-Dec-24 Account No. - 1013085561
        Currency NAIRA
        Account Name
        TEAMAPT LIMITED ATS INCOME ALC          Total Debits - 288.10
        Total Credits - 12.00
        """
        fake_pdf = FakePdf(
            [FakePage(first_page_words, summary), FakePage(second_page_words)]
        )

        self.assertIsNotNone(detect_keystone_layout(first_page_words))
        transactions, metadata = extract_keystone_via_coordinates(
            Path("unused.pdf"), {"bank": "keystone"}, pdf=fake_pdf
        )

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0]["date"], "04-Jan-2024")
        self.assertEqual(transactions[0]["credit"], 12.0)
        self.assertIn("Inc/2401032200006790 200007 DCIR", transactions[0]["description"])
        self.assertEqual(transactions[1]["debit"], 288.10)
        self.assertEqual(metadata["method"], "keystone_coordinates")


if __name__ == "__main__":
    unittest.main()
