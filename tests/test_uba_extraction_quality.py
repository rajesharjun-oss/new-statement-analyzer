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
from uba_engine import _extract_uba_amount_line_transactions  # noqa: E402



class _FakeUBAPage:
    def __init__(self, words):
        self._words = words

    def extract_words(self, **_kwargs):
        return list(self._words)


class _FakeUBAPdf:
    def __init__(self, words):
        self.pages = [_FakeUBAPage(words)]


def _word(text, x0, x1, top):
    return {"text": text, "x0": x0, "x1": x1, "top": top}

class UBAExtractionQualityTests(unittest.TestCase):

    def test_uba_amount_line_parser_extracts_every_printed_amount(self):
        words = [
            _word("TRANS", 35.9, 63.7, 100.0),
            _word("DATE", 66.1, 87.9, 100.0),
            _word("VALUE", 100.1, 127.0, 100.0),
            _word("DATE", 129.5, 151.3, 100.0),
            _word("NARRATION", 197.2, 245.5, 100.0),
            _word("DEBIT", 343.9, 368.1, 100.0),
            _word("CREDIT", 425.8, 456.3, 100.0),
            _word("BALANCE", 507.0, 545.2, 100.0),
            _word("Gift", 161.2, 176.8, 116.0),
            _word("79", 179.5, 190.6, 116.0),
            _word("04-Jan-2026", 33.7, 89.8, 126.0),
            _word("03-Jan-2026", 97.4, 153.6, 126.0),
            _word("55,000.00", 435.7, 480.1, 126.0),
            _word("254,715.86", 515.1, 565.2, 126.0),
            _word("CHQ100", 161.2, 200.1, 146.0),
            _word("TRF", 202.8, 222.2, 146.0),
            _word("13-Jan-2026", 33.7, 89.8, 156.0),
            _word("13-Jan-2026", 97.4, 153.6, 156.0),
            _word("100,000.00", 345.1, 395.1, 156.0),
            _word("154,715.86", 515.1, 565.2, 156.0),
            _word("02-Feb-", 33.7, 68.7, 186.0),
            _word("02-Feb-", 97.4, 132.4, 186.0),
            _word("Transfer", 161.2, 198.4, 186.0),
            _word("from", 201.1, 221.1, 186.0),
            _word("20,000.00", 435.7, 480.1, 196.0),
            _word("174,715.86", 515.1, 565.2, 196.0),
            _word("LATIFAT", 223.8, 263.7, 196.0),
            _word("2026", 33.7, 55.9, 206.0),
            _word("2026", 97.4, 119.7, 206.0),
        ]
        txns, metadata = _extract_uba_amount_line_transactions(
            _FakeUBAPdf(words),
            {
                "statement_total_debit": "100,000.00",
                "statement_total_credit": "75,000.00",
            },
        )

        self.assertEqual(len(txns), 3)
        self.assertEqual(metadata["method"], "uba_amount_lines")
        self.assertEqual(txns[0]["description"], "Gift 79")
        self.assertEqual(txns[1]["debit"], 100000.0)
        self.assertEqual(txns[2]["date"], "02-Feb-2026")
        self.assertEqual(txns[2]["description"], "Transfer from LATIFAT")
        self.assertEqual(sum(t["debit"] for t in txns), 100000.0)
        self.assertEqual(sum(t["credit"] for t in txns), 75000.0)
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