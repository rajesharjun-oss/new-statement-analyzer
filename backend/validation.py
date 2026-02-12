"""
Validation Service - Production Version
Implements financial totals validation with accurate metadata comparison
"""
import re
from typing import Any, Dict, List

def _num(x) -> float:
    """Parse money safely. Returns 0.0 if empty/invalid."""
    if x is None:
        return 0.0
    s = str(x).strip()
    if not s:
        return 0.0
    s = s.replace("₦", "").replace("N", "").replace(",", "").strip()
    # accept only strict money-ish formats
    if not re.match(r"^-?\d+(\.\d{1,2})?$", s):
        return 0.0
    return float(s)

def validate_totals(transactions: List[Dict], metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate extracted totals against statement totals.
    This is the ONLY meaningful 'accuracy' check for bank statement extraction.
    """

    if not transactions:
        return {
            "status": "No transactions extracted",
            "totals_match": False,
            "extracted_total_debit": 0.0,
            "extracted_total_credit": 0.0,
            "statement_total_debit": metadata.get("statement_total_debit"),
            "statement_total_credit": metadata.get("statement_total_credit"),
            "debit_diff": None,
            "credit_diff": None,
        }

    extracted_debit = sum(_num(t.get("debit")) for t in transactions)
    extracted_credit = sum(_num(t.get("credit")) for t in transactions)

    # Use the statement totals you parsed from page 1
    statement_debit = metadata.get("statement_total_debit")
    statement_credit = metadata.get("statement_total_credit")

    # If statement totals are missing, we can't fully validate
    if statement_debit is None or statement_credit is None:
        return {
            "status": "Statement totals missing (cannot fully validate). Extraction totals computed.",
            "totals_match": None,
            "extracted_total_debit": extracted_debit,
            "extracted_total_credit": extracted_credit,
            "statement_total_debit": statement_debit,
            "statement_total_credit": statement_credit,
            "debit_diff": None,
            "credit_diff": None,
        }

    tolerance = 0.01  # 1 kobo tolerance
    debit_diff = extracted_debit - float(statement_debit)
    credit_diff = extracted_credit - float(statement_credit)

    debit_ok = abs(debit_diff) <= tolerance
    credit_ok = abs(credit_diff) <= tolerance
    totals_match = debit_ok and credit_ok

    if totals_match:
        status = "Totals match statement"
    else:
        status = (
            "Totals mismatch: "
            f"Debit diff={debit_diff:.2f}, Credit diff={credit_diff:.2f}"
        )

    return {
        "status": status,
        "totals_match": totals_match,
        "extracted_total_debit": extracted_debit,
        "extracted_total_credit": extracted_credit,
        "statement_total_debit": float(statement_debit),
        "statement_total_credit": float(statement_credit),
        "debit_diff": debit_diff,
        "credit_diff": credit_diff,
    }
