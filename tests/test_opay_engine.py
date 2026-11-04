import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from opay_engine import extract_opay_statements  # noqa: E402
from pdf_extractor import detect_template  # noqa: E402


WALLET_BOUNDS = [66.8, 125.8, 172.4, 301.1, 339.1, 377.2, 418.2, 474.0, 542.2]
SAVINGS_BOUNDS = [66.8, 137.9, 192.2, 257.6, 302.6, 347.8, 398.1, 463.4, 542.2]


def word(text, x0, top, width=None):
    width = width or max(len(text) * 3, 6)
    return {
        "text": text,
        "x0": float(x0),
        "x1": float(x0 + width),
        "top": float(top),
        "bottom": float(top + 8),
    }


def cells(bounds, top, bottom):
    return [
        {
            "x0": left,
            "x1": right,
            "top": float(top),
            "bottom": float(bottom),
        }
        for left, right in zip(bounds, bounds[1:])
    ]


class FakePage:
    def __init__(self, words, rects, text=""):
        self._words = words
        self.rects = rects
        self._text = text

    def extract_words(self, **_kwargs):
        return self._words

    def extract_text(self):
        return self._text


class FakePdf:
    def __init__(self, pages):
        self.pages = pages


def wallet_metadata_words(debit="5.00", debit_count="1", credit="0.00", credit_count="0"):
    return [
        word("IBRAHIM ONAWOGA", 70, 152),
        word("7000000001", 230, 152),
        word("Lagos", 390, 152),
        word("5.00", 70, 252),
        word(debit, 230, 252),
        word(debit_count, 390, 252),
        word("0.00", 70, 288),
        word(credit, 230, 288),
        word(credit_count, 390, 288),
    ]


class OPayEngineTests(unittest.TestCase):
    def test_detects_wallet_or_savings_template(self):
        common = "OPay Account Statement Transaction Reference Balance After"
        self.assertEqual(detect_template(f"{common} Wallet Account"), "opay")
        self.assertEqual(detect_template(f"{common} Savings Account"), "opay")

    def test_preserves_cross_page_reference_fragments(self):
        first_words = wallet_metadata_words() + [word("ABC", 480, 740)]
        first_page = FakePage(
            first_words,
            cells(WALLET_BOUNDS, 350, 370),
            "OPay Account Statement Wallet Account Transaction Reference Balance After",
        )
        second_words = [
            word("01 Jan 2026 09:33:03", 70, 60),
            word("01 Jan 2026", 130, 60),
            word("Transfer fee", 180, 60),
            word("5.00", 305, 60),
            word("0.00", 378, 60),
            word("Mobile", 420, 60),
            word("123", 480, 60),
        ]
        second_page = FakePage(
            second_words,
            cells(WALLET_BOUNDS, 100, 120),
        )

        results = extract_opay_statements(
            Path("unused.pdf"),
            {"bank": "opay"},
            pdf=FakePdf([first_page, second_page]),
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0]["transactions"]), 1)
        self.assertEqual(results[0]["transactions"][0]["reference"], "ABC123")
        self.assertTrue(results[0]["metadata"]["transaction_count_match"])

    def test_splits_wallet_and_savings_layouts(self):
        savings_heading_top = 400
        words = wallet_metadata_words() + [
            word("01 Jan 2026 09:33:03", 70, 352),
            word("01 Jan 2026", 130, 352),
            word("Wallet debit", 180, 352),
            word("5.00", 305, 352),
            word("0.00", 378, 352),
            word("Mobile", 420, 352),
            word("WALLET-1", 480, 352),
            word("SAVINGS", 70, savings_heading_top),
            word("ACCOUNT", 105, savings_heading_top),
            word("01 Jan 2026 - 02 Jan 2026", 230, savings_heading_top),
            word("0.00", 70, savings_heading_top + 34),
            word("0.00", 230, savings_heading_top + 34),
            word("0", 390, savings_heading_top + 34),
            word("10.00", 70, savings_heading_top + 70),
            word("10.00", 230, savings_heading_top + 70),
            word("1", 390, savings_heading_top + 70),
            word("02 Jan 2026 10:00:00", 70, 522),
            word("02 Jan 2026", 145, 522),
            word("Savings credit", 200, 522),
            word("10.00", 310, 522),
            word("10.00", 350, 522),
            word("Mobile", 400, 522),
            word("SAVINGS-1", 470, 522),
        ]
        page = FakePage(
            words,
            cells(WALLET_BOUNDS, 350, 370) + cells(SAVINGS_BOUNDS, 520, 540),
            "OPay Account Statement Wallet Account Savings Account Transaction Reference Balance After",
        )

        results = extract_opay_statements(
            Path("unused.pdf"),
            {"bank": "opay"},
            pdf=FakePdf([page]),
        )

        self.assertEqual(
            [result["metadata"]["account_type"] for result in results],
            ["Wallet Account", "Savings Account"],
        )
        self.assertEqual(len(results[0]["transactions"]), 1)
        self.assertEqual(results[0]["transactions"][0]["debit"], 5.0)
        self.assertEqual(len(results[1]["transactions"]), 1)
        self.assertEqual(results[1]["transactions"][0]["credit"], 10.0)
        self.assertEqual(results[1]["metadata"]["statement_total_credit"], 10.0)
        self.assertTrue(results[1]["metadata"]["transaction_count_match"])


if __name__ == "__main__":
    unittest.main()
