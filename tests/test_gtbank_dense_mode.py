import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from pdf_extractor import should_use_pymupdf_words_for_gt_dense  # noqa: E402

class GTBankDenseModeTests(unittest.TestCase):
    def test_gtbank_dense_mode_keeps_pdfplumber_row_words(self):
        self.assertFalse(should_use_pymupdf_words_for_gt_dense("gtbank", 142))
        self.assertFalse(should_use_pymupdf_words_for_gt_dense("gtco", 142))


if __name__ == "__main__":
    unittest.main()
