"""
Validation Service - Production Version
Implements financial totals validation with accurate metadata comparison.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List


ZERO = Decimal("0")
CENT = Decimal("0.01")


def _money(value: Any) -> Decimal:
    """Parse a money value into an exact decimal, returning zero for invalid input."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value

    text = str(value).strip()
    if not text:
        return ZERO

    negative_parentheses = text.startswith("(") and text.endswith(")")
    if negative_parentheses:
        text = text[1:-1].strip()
    text = (
        text.replace("\u20a6", "")
        .replace("\u00e2\u201a\u00a6", "")
        .replace(",", "")
        .strip()
    )
    text = re.sub(r"^(?:NGN|N)\s*", "", text, flags=re.IGNORECASE)
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return ZERO
    try:
        parsed = Decimal(text)
        return -parsed if negative_parentheses else parsed
    except InvalidOperation:
        return ZERO


def _num(value: Any) -> float:
    """Parse money safely. Returns 0.0 if empty or invalid."""
    return float(_money(value))


def _output(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def validate_totals(transactions: List[Dict], metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Validate extracted totals against statement totals and balance bounds."""
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

    extracted_debit = sum((_money(t.get("debit")) for t in transactions), ZERO)
    extracted_credit = sum((_money(t.get("credit")) for t in transactions), ZERO)

    statement_debit = metadata.get("statement_total_debit")
    statement_credit = metadata.get("statement_total_credit")

    opening_bal = _money(metadata.get("opening_balance"))
    closing_bal = _money(metadata.get("closing_balance"))
    last_bal = ZERO
    for transaction in reversed(transactions):
        balance = _money(transaction.get("balance"))
        if balance != ZERO:
            last_bal = balance
            break

    if closing_bal == ZERO and last_bal != ZERO:
        closing_bal = last_bal

    implied_closing = (opening_bal + extracted_credit - extracted_debit).quantize(CENT, rounding=ROUND_HALF_UP)
    has_balance_bounds = metadata.get("opening_balance") is not None and (
        metadata.get("closing_balance") is not None or last_bal != ZERO
    )
    ledger_reconciles = has_balance_bounds and abs(implied_closing - closing_bal) <= Decimal("1.00")

    if statement_debit is None or statement_credit is None:
        status = "Statement totals missing (cannot fully validate). Extraction totals computed."
        if ledger_reconciles:
            status = "Ledger balances reconcile; statement debit/credit totals unavailable."
        return {
            "status": status,
            "totals_match": None,
            "extracted_total_debit": _output(extracted_debit),
            "extracted_total_credit": _output(extracted_credit),
            "statement_total_debit": statement_debit,
            "statement_total_credit": statement_credit,
            "debit_diff": None,
            "credit_diff": None,
            "opening_balance": _output(opening_bal),
            "closing_balance": _output(closing_bal) if has_balance_bounds else None,
            "implied_closing_balance": _output(implied_closing) if has_balance_bounds else None,
        }

    tolerance = abs(_money(metadata.get("validation_tolerance", "0.50")))
    statement_debit_value = _money(statement_debit)
    statement_credit_value = _money(statement_credit)
    debit_diff = extracted_debit - statement_debit_value
    credit_diff = extracted_credit - statement_credit_value

    debit_ok = abs(debit_diff) <= tolerance
    credit_ok = abs(credit_diff) <= tolerance
    totals_match = debit_ok and credit_ok

    # GTBank/GTCO can ship mixed-account bundles whose header summary does not
    # align with the visible ledger pages. Surface the conflict without passing it.
    if not totals_match and str(metadata.get("bank", "")).lower() in {"gtbank", "gtco"}:
        header_disagrees = abs(closing_bal - last_bal) > Decimal("1.00") if last_bal != ZERO else False
        if ledger_reconciles and header_disagrees:
            return {
                "status": (
                    "Header totals and transaction ledger conflict: ledger rows are internally "
                    "consistent, but they do not reconcile to statement header totals "
                    f"(header closing={closing_bal:.2f}, ledger closing={last_bal:.2f})."
                ),
                "totals_match": False,
                "extracted_total_debit": _output(extracted_debit),
                "extracted_total_credit": _output(extracted_credit),
                "statement_total_debit": _output(statement_debit_value),
                "statement_total_credit": _output(statement_credit_value),
                "debit_diff": _output(debit_diff),
                "credit_diff": _output(credit_diff),
                "header_closing_balance": _output(closing_bal),
                "ledger_closing_balance": _output(last_bal),
            }

    if not totals_match and ledger_reconciles:
        return {
            "status": (
                "Statement totals and transaction ledger conflict: ledger rows reconcile "
                "from opening to closing balance, but extracted debit/credit totals do not "
                "match the statement summary."
            ),
            "totals_match": False,
            "extracted_total_debit": _output(extracted_debit),
            "extracted_total_credit": _output(extracted_credit),
            "statement_total_debit": _output(statement_debit_value),
            "statement_total_credit": _output(statement_credit_value),
            "debit_diff": _output(debit_diff),
            "credit_diff": _output(credit_diff),
            "opening_balance": _output(opening_bal),
            "closing_balance": _output(closing_bal),
            "implied_closing_balance": _output(implied_closing),
        }

    status = "Totals match statement" if totals_match else (
        "Totals mismatch: "
        f"Debit diff={debit_diff:.2f}, Credit diff={credit_diff:.2f}"
    )
    if totals_match and metadata.get("extraction_issue"):
        status = metadata["extraction_issue"]
        totals_match = False

    return {
        "status": status,
        "totals_match": totals_match,
        "extracted_total_debit": _output(extracted_debit),
        "extracted_total_credit": _output(extracted_credit),
        "statement_total_debit": _output(statement_debit_value),
        "statement_total_credit": _output(statement_credit_value),
        "debit_diff": _output(debit_diff),
        "credit_diff": _output(credit_diff),
    }
