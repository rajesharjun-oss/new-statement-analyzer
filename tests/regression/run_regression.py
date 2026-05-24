import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from pdf_extractor import extract_transactions  # noqa: E402
from validation import validate_totals  # noqa: E402


def money(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def load_cases(path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Expected regression file to contain a list of cases.")
    return data


def run_case(case):
    case_id = case.get("id") or case.get("file") or "unnamed-case"
    fixture = ROOT / case["file"]
    if not fixture.exists():
        return "SKIP", f"{case_id}: fixture not found at {fixture}"

    bank = case.get("bank", "auto")
    results = extract_transactions(str(fixture), bank_identifier=bank)
    txns = []
    metadata = {}
    for stmt in results:
        txns.extend(stmt.get("transactions", []))
        if not metadata and stmt.get("metadata"):
            metadata = stmt["metadata"]

    validation = validate_totals(txns, metadata)
    tolerance = money(case.get("tolerance", 0.01))
    errors = []

    expected_count = case.get("expected_transaction_count")
    if expected_count is not None and len(txns) != int(expected_count):
        errors.append(f"count expected {expected_count}, got {len(txns)}")

    expected_debit = case.get("expected_total_debit")
    if expected_debit is not None:
        actual_debit = money(validation.get("extracted_total_debit"))
        if abs(actual_debit - money(expected_debit)) > tolerance:
            errors.append(f"debit expected {money(expected_debit):.2f}, got {actual_debit:.2f}")

    expected_credit = case.get("expected_total_credit")
    if expected_credit is not None:
        actual_credit = money(validation.get("extracted_total_credit"))
        if abs(actual_credit - money(expected_credit)) > tolerance:
            errors.append(f"credit expected {money(expected_credit):.2f}, got {actual_credit:.2f}")

    expected_opening = case.get("expected_opening_balance")
    if expected_opening is not None:
        actual_opening = money(metadata.get("opening_balance"))
        if abs(actual_opening - money(expected_opening)) > tolerance:
            errors.append(f"opening expected {money(expected_opening):.2f}, got {actual_opening:.2f}")

    expected_closing = case.get("expected_closing_balance")
    if expected_closing is not None:
        actual_closing = money(metadata.get("closing_balance"))
        if abs(actual_closing - money(expected_closing)) > tolerance:
            errors.append(f"closing expected {money(expected_closing):.2f}, got {actual_closing:.2f}")

    if errors:
        return "FAIL", f"{case_id}: " + "; ".join(errors)
    return "PASS", f"{case_id}: {len(txns)} transactions"


def main():
    parser = argparse.ArgumentParser(description="Run statement extraction regression checks.")
    parser.add_argument(
        "--expectations",
        default=ROOT / "tests" / "regression" / "expected_statements.json",
        type=Path,
        help="Path to the expectations JSON file.",
    )
    args = parser.parse_args()

    cases = load_cases(args.expectations)
    active_cases = [case for case in cases if case.get("enabled", True)]
    if not active_cases:
        print("SKIP: no enabled regression cases.")
        return 0

    failed = 0
    for case in active_cases:
        status, message = run_case(case)
        print(f"{status}: {message}")
        if status == "FAIL":
            failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
