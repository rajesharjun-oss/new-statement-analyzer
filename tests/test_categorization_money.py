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

    def test_pension_credit_is_pension_income(self):
        rows = [{
            "date": "2026-01-31",
            "description": "PTAD pension payment retirement benefit",
            "remarks": "PTAD pension payment retirement benefit",
            "debit": "0.00",
            "credit": "250,000.00",
            "balance": "300,000.00",
        }]

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "",
        }):
            result = categorize_transactions(rows)

        self.assertEqual(result[0]["category"], "Pension Income")
        self.assertEqual(result[0]["ruleId"], "R003_PENSION_INCOME")

    def test_keystone_dcir_credit_is_operating_income(self):
        rows = [{
            "date": "2024-01-04",
            "description": "KBLDCIR Inc/2401032200006790 DCIR Inc/2401032200006790 Txn Amount - NGN12.00",
            "debit": 0,
            "credit": 12,
            "balance": 694831.60,
        }]

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "",
        }):
            result = categorize_transactions(rows)

        self.assertEqual(result[0]["category"], "Operating Income")
        self.assertEqual(result[0]["ruleId"], "R004E_KEYSTONE_DCIR_INCOME")
        self.assertEqual(result[0]["decision_source"], "RULE")

    def test_unmatched_credit_is_not_mislabeled_as_ai(self):
        rows = [{
            "date": "2024-01-04",
            "description": "UNRECOGNIZED CREDIT NARRATION",
            "debit": 0,
            "credit": 12,
            "balance": 694831.60,
        }]

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "",
        }):
            result = categorize_transactions(rows)

        self.assertEqual(result[0]["category"], "Uncategorized Income")
        self.assertEqual(result[0]["decision_source"], "SYSTEM")


if __name__ == "__main__":
    unittest.main()
