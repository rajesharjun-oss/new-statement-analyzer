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

from pdf_extractor import (  # noqa: E402
    assess_statement_total_match,
    get_uba_ai_page_limit,
    get_uba_ocr_page_limit,
)


class UBAExtractionQualityTests(unittest.TestCase):
    def test_partial_rows_fail_statement_total_quality_gate(self):
        transactions = [{"debit": "51,504.80", "credit": "0.00"}]
        transactions.extend({"debit": "0.00", "credit": "0.00"} for _ in range(29))
        metadata = {
            "statement_total_debit": "51,571,159.67",
            "statement_total_credit": "52,519,135.00",
        }

        result = assess_statement_total_match(transactions, metadata)

        self.assertTrue(result["has_statement_totals"])
        self.assertFalse(result["totals_match"])
        self.assertEqual(result["extracted_total_debit"], 51504.80)
        self.assertEqual(result["extracted_total_credit"], 0.0)
        self.assertTrue(math.isclose(result["debit_diff"], -51519654.87, abs_tol=0.001))
        self.assertTrue(math.isclose(result["credit_diff"], -52519135.00, abs_tol=0.001))

    def test_matching_rows_pass_statement_total_quality_gate(self):
        transactions = [
            {"debit": "51,571,159.67", "credit": "0.00"},
            {"debit": "0.00", "credit": "52,519,135.00"},
        ]
        metadata = {
            "statement_total_debit": "51,571,159.67",
            "statement_total_credit": "52,519,135.00",
        }

        result = assess_statement_total_match(transactions, metadata)

        self.assertTrue(result["has_statement_totals"])
        self.assertTrue(result["totals_match"])
        self.assertEqual(result["debit_diff"], 0.0)
        self.assertEqual(result["credit_diff"], 0.0)

    def test_missing_statement_totals_are_not_treated_as_mismatch(self):
        result = assess_statement_total_match(
            [{"debit": "1,000.00", "credit": "0.00"}],
            {"statement_total_debit": None, "statement_total_credit": None},
        )

        self.assertFalse(result["has_statement_totals"])
        self.assertIsNone(result["totals_match"])
        self.assertEqual(result["extracted_total_debit"], 1000.0)

    def test_uba_page_limits_are_bounded_and_configurable(self):
        with patch.dict(os.environ, {"UBA_OCR_MAX_PAGES": "500", "UBA_AI_MAX_PAGES": "500"}):
            self.assertEqual(get_uba_ocr_page_limit(361), 150)
            self.assertEqual(get_uba_ai_page_limit(361), 80)

        with patch.dict(os.environ, {"UBA_OCR_MAX_PAGES": "25", "UBA_AI_MAX_PAGES": "10"}):
            self.assertEqual(get_uba_ocr_page_limit(361), 25)
            self.assertEqual(get_uba_ai_page_limit(361), 10)

        with patch.dict(os.environ, {"UBA_OCR_MAX_PAGES": "not-a-number", "UBA_AI_MAX_PAGES": "not-a-number"}):
            self.assertEqual(get_uba_ocr_page_limit(12), 12)
            self.assertEqual(get_uba_ai_page_limit(12), 12)


if __name__ == "__main__":
    unittest.main()