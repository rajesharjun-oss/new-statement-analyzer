import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from moniepoint_engine import extract_moniepoint_via_coordinates  # noqa: E402
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


class MoniepointEngineTests(unittest.TestCase):
    def test_detects_moniepoint_template(self):
        text = (
            "Account Statement Account Summary Business Name Transaction Terminal "
            "RRN Transaction Ref Reversal Settlement Balance Beneficiary"
        )
        self.assertEqual(detect_template(text), "moniepoint")

    def test_extracts_settlement_columns_and_metadata(self):
        metadata_words = [
            word("TASTE", 170, 174),
            word("AND", 210, 174),
            word("SIP", 240, 174),
            word("1234567890", 170, 192),
            word("25/06/2026", 170, 224),
            word("-", 230, 224),
            word("23/09/2026", 240, 224),
            word("Lagos", 170, 242),
        ]
        transaction_words = [
            word("2026-", 10, 400),
            word("06-25T10:30:00", 38, 400),
            word("TASTE", 90, 400),
            word("Transfer", 145, 400),
            word("Successful", 230, 400),
            word("REF-001", 430, 400),
            word("3,590.00", 935, 400),
            word("0.00", 1000, 400),
            word("10,000.00", 1065, 400),
            word("6,410.00", 1122, 400),
            word("Vendor", 1528, 400),
            word("payment", 1570, 400),
        ]
        text = """
        MONIEPOINT MICROFINANCE BANK
        Opening Balance 10,000.00
        Total Debits 3,590.00
        Total Credits 0.00
        Closing Balance 6,410.00
        """
        pdf = FakePdf([FakePage(metadata_words + transaction_words, text)])

        transactions, metadata = extract_moniepoint_via_coordinates(
            Path("unused.pdf"),
            {"bank": "moniepoint"},
            pdf=pdf,
        )

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0]["date"], "25-Jun-2026")
        self.assertEqual(transactions[0]["debit"], 3590.0)
        self.assertEqual(transactions[0]["credit"], 0.0)
        self.assertEqual(transactions[0]["balance"], 6410.0)
        self.assertEqual(transactions[0]["description"], "Vendor payment")
        self.assertEqual(metadata["account_number"], "1234567890")
        self.assertEqual(metadata["statement_total_debit"], 3590.0)
        self.assertEqual(metadata["transaction_count_extracted"], 1)


if __name__ == "__main__":
    unittest.main()
