import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGRESSION = ROOT / "tests" / "regression"
if str(REGRESSION) not in sys.path:
    sys.path.insert(0, str(REGRESSION))

from run_regression import compute_extraction_metrics  # noqa: E402


class RegressionBenchmarkTests(unittest.TestCase):
    def test_scores_complete_ascending_ledger(self):
        transactions = [
            {"date": "01-Jan-2024", "description": "Opening receipt", "debit": 0, "credit": 100, "balance": 100},
            {"date": "02-Jan-2024", "description": "Bank charge", "debit": 10, "credit": 0, "balance": 90},
            {"date": "03-Jan-2024", "description": "Customer receipt", "debit": 0, "credit": 20, "balance": 110},
        ]

        metrics = compute_extraction_metrics(transactions)

        self.assertEqual(metrics["description_coverage"], 1.0)
        self.assertEqual(metrics["date_coverage"], 1.0)
        self.assertEqual(metrics["amount_direction_coverage"], 1.0)
        self.assertEqual(metrics["balance_continuity_coverage"], 1.0)

    def test_detects_missing_description_and_invalid_amount_direction(self):
        transactions = [
            {"date": "2024-01-01", "description": "", "debit": 50, "credit": 50, "balance": 100},
            {"date": "invalid", "description": "Valid description", "debit": 10, "credit": 0, "balance": 90},
        ]

        metrics = compute_extraction_metrics(transactions)

        self.assertEqual(metrics["description_coverage"], 0.5)
        self.assertEqual(metrics["date_coverage"], 0.5)
        self.assertEqual(metrics["amount_direction_coverage"], 0.5)


if __name__ == "__main__":
    unittest.main()
