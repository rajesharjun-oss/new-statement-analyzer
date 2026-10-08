import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fcmb_engine import detect_fcmb_columns  # noqa: E402
from pdf_extractor import is_noise_row, parse_statement_metadata  # noqa: E402


def _word(text, x0, x1, top=100, bottom=None):
    return {
        "text": text,
        "x0": float(x0),
        "x1": float(x1),
        "top": float(top),
        "bottom": float(bottom if bottom is not None else top + 8),
    }


class FCMBEngineTests(unittest.TestCase):
    def test_detects_deposit_withdrawal_template(self):
        words = [
            _word("Date", 20, 50),
            _word("Reference", 80, 122),
            _word("Descrip\x00on", 160, 235),
            _word("ValueDate", 330, 390),
            _word("Deposit", 440, 493),
            _word("Withdrawal", 525, 600),
            _word("Balance", 650, 710),
        ]

        cuts = detect_fcmb_columns(words)

        self.assertIsNotNone(cuts)
        self.assertIn("credit", cuts)
        self.assertIn("debit", cuts)
        self.assertLess(cuts["credit"][0], 470)
        self.assertGreater(cuts["credit"][1], 470)
        self.assertLess(cuts["debit"][0], 560)
        self.assertGreater(cuts["debit"][1], 560)

    def test_summary_row_with_total_debit_in_value_date_is_noise(self):
        self.assertTrue(
            is_noise_row({
                "date": "01-Jan-2024",
                "value_date": "Total Debit:",
                "description": "To 31-Dec-2024 MGT OPERATIONS DOM (USD)",
                "reference": "FCMB ASSET 17A TINUBU",
            })
        )

    def test_fcmb_summary_metadata_captures_currency_and_period(self):
        text = """
        Account No: 0155203201 Currency: USD
        Account Type: CURRENT A/C FCY LTD COYS Total Credit: 2,678,010.30
        For the Period of: 01-Jan-2024 To 31-Dec-2024 Total Debit: 2,639,785.62
        Account Name: FCMB ASSET MGT OPERATIONS DOM (USD)
        Opening Balance: 21,088.03 Cr
        """

        meta = parse_statement_metadata(text)

        self.assertEqual(meta["currency"], "USD")
        self.assertEqual(meta["statement_period"], "01-Jan-2024 to 31-Dec-2024")
        self.assertEqual(meta["statement_total_debit"], 2639785.62)
        self.assertEqual(meta["statement_total_credit"], 2678010.30)


if __name__ == "__main__":
    unittest.main()
