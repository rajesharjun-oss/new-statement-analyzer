import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from validation import _num, validate_totals  # noqa: E402


class ValidationDecimalTests(unittest.TestCase):
    def test_money_parser_accepts_common_bank_formats(self):
        cases = {
            "3,590.00": 3590.0,
            "NGN 1,234.56": 1234.56,
            "N500.25": 500.25,
            "(2,500.00)": -2500.0,
            "not-a-number": 0.0,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(_num(raw), expected)

    def test_totals_use_exact_decimal_arithmetic(self):
        transactions = [
            {"debit": "0.10", "credit": "0", "balance": "99.90"},
            {"debit": "0.20", "credit": "3,590.00", "balance": "3,689.70"},
        ]
        metadata = {
            "opening_balance": "100.00",
            "closing_balance": "3,689.70",
            "statement_total_debit": "0.30",
            "statement_total_credit": "3,590.00",
            "validation_tolerance": "0.00",
        }

        result = validate_totals(transactions, metadata)

        self.assertTrue(result["totals_match"])
        self.assertEqual(result["extracted_total_debit"], 0.30)
        self.assertEqual(result["extracted_total_credit"], 3590.00)
        self.assertEqual(result["debit_diff"], 0.0)
        self.assertEqual(result["credit_diff"], 0.0)

    def test_repeated_kobo_values_do_not_accumulate_float_drift(self):
        transactions = [{"debit": "0.01", "credit": 0, "balance": 0} for _ in range(1000)]
        metadata = {
            "statement_total_debit": "10.00",
            "statement_total_credit": "0.00",
            "validation_tolerance": "0.00",
        }

        result = validate_totals(transactions, metadata)

        self.assertTrue(result["totals_match"])
        self.assertEqual(result["extracted_total_debit"], 10.0)


if __name__ == "__main__":
    unittest.main()
