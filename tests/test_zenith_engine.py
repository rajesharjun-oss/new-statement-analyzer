import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from zenith_engine import extract_zenith_via_coordinates  # noqa: E402


class _FakeZenithPage:
    def __init__(self, words):
        self._words = words

    def extract_words(self, **_kwargs):
        return list(self._words)


class _FakeZenithPdf:
    def __init__(self, words):
        self.pages = [_FakeZenithPage(words)]


def _word(text, x0, x1, top):
    return {"text": text, "x0": x0, "x1": x1, "top": top}


class ZenithDescriptionExtractionTests(unittest.TestCase):
    def test_multiline_description_keeps_left_prefix_and_correct_order(self):
        words = [
            _word("Date", 30, 58, 100),
            _word("Posted", 61, 98, 100),
            _word("Value", 100, 135, 100),
            _word("Date", 138, 165, 100),
            _word("Description", 260, 330, 100),
            _word("Debit", 520, 555, 100),
            _word("Credit", 600, 642, 100),
            _word("Balance", 690, 742, 100),
            _word("OPENING", 150, 205, 112),
            _word("BALANCE", 210, 260, 112),
            _word("01-Jan-2026", 30, 90, 120),
            _word("01-Jan-2026", 100, 160, 120),
            _word("NIP/FCMB/ADEBUTU", 145, 245, 120),
            _word("AJIBOLA", 250, 300, 120),
            _word("BANKOLE", 305, 365, 120),
            _word(".../NIP", 370, 415, 120),
            _word("IFO", 420, 445, 120),
            _word("Gasmart", 450, 500, 120),
            _word("1,000.00", 610, 660, 120),
            _word("1,000.00", 695, 745, 120),
            _word("Distribution", 145, 225, 132),
            _word("Limited", 230, 280, 132),
            _word("Frm", 285, 310, 132),
            _word("Adebutu", 315, 370, 132),
            _word("Ajibola", 375, 425, 132),
            _word("Ban", 430, 455, 132),
            _word("02-Jan-2026", 30, 90, 150),
            _word("02-Jan-2026", 100, 160, 150),
            _word("CQ", 145, 165, 150),
            _word("15", 170, 185, 150),
            _word("PD", 190, 210, 150),
            _word("MAIDDRANTE", 215, 295, 150),
            _word("NIGERIA", 300, 360, 150),
            _word("LTD", 365, 390, 150),
            _word("500.00", 525, 565, 150),
            _word("500.00", 695, 740, 150),
        ]

        txns, _metadata = extract_zenith_via_coordinates(
            Path("dummy.pdf"),
            {"opening_balance": "0.00"},
            pdf=_FakeZenithPdf(words),
        )

        self.assertEqual(len(txns), 2)
        self.assertEqual(
            txns[0]["description"],
            "NIP/FCMB/ADEBUTU AJIBOLA BANKOLE .../NIP IFO Gasmart "
            "Distribution Limited Frm Adebutu Ajibola Ban",
        )
        self.assertNotIn("OPENING BALANCE", txns[0]["description"])
        self.assertEqual(txns[1]["description"], "CQ 15 PD MAIDDRANTE NIGERIA LTD")


if __name__ == "__main__":
    unittest.main()