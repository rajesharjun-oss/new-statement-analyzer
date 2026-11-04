import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from main import clean_narrative_response  # noqa: E402


class AnalysisNarrativeTests(unittest.TestCase):
    def test_rejects_invented_evidence_ids_and_invalid_severity(self):
        result = clean_narrative_response(
            {
                "summary": "Verified summary",
                "findings": [{
                    "title": "Finding",
                    "body": "Evidence-backed body",
                    "severity": "Critical",
                    "evidenceTransactionIds": ["txn-1", "invented-id"],
                }],
                "caveats": ["Review source rows"],
            },
            {"txn-1"},
            "Fallback summary",
        )

        self.assertEqual(result["generatedBy"], "AI")
        self.assertEqual(result["findings"][0]["severity"], "Neutral")
        self.assertEqual(result["findings"][0]["evidenceTransactionIds"], ["txn-1"])

    def test_uses_deterministic_summary_when_ai_omits_one(self):
        result = clean_narrative_response({}, set(), "Deterministic summary")
        self.assertEqual(result["summary"], "Deterministic summary")


if __name__ == "__main__":
    unittest.main()
