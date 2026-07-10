import math
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from categorization import categorize_transactions, parse_money_amount  # noqa: E402


class CategorizationMoneyTests(unittest.TestCase):
    def test_parse_money_amount_accepts_bank_formatted_strings(self):
        cases = {
            "3,590.00": 3590.0,
            "NGN 1,234.56": 1234.56,
            "(2,500.00)": -2500.0,
            "": 0.0,
            None: 0.0,
            "not-a-number": 0.0,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertTrue(math.isclose(parse_money_amount(raw), expected, abs_tol=0.001))

    def test_categorize_transactions_normalizes_comma_amounts(self):
        rows = [{
            "date": "2026-01-02",
            "description": "UBA TRANSFER CHARGE",
            "remarks": "UBA TRANSFER CHARGE",
            "debit": "3,590.00",
            "credit": "0.00",
            "balance": "10,000.00",
        }]

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "",
        }):
            result = categorize_transactions(rows)

        self.assertEqual(result[0]["debit"], 3590.0)
        self.assertEqual(result[0]["credit"], 0.0)
        self.assertIn("category", result[0])


if __name__ == "__main__":
    unittest.main()