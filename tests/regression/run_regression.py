import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from pdf_extractor import extract_transactions  # noqa: E402
from validation import validate_totals  # noqa: E402


DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d/%m/%Y",
    "%d/%m/%y",
)


def money(value):
    try:
        return float(str(value or 0).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def parse_date(value):
    text = str(value or "").strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return None


def ratio(count, total):
    return round(count / total, 4) if total else 0.0


def balance_continuity_coverage(transactions, tolerance=0.05):
    comparable = []
    for previous, current in zip(transactions, transactions[1:]):
        previous_balance = money(previous.get("balance"))
        current_balance = money(current.get("balance"))
        if previous_balance == 0 or current_balance == 0:
            continue
        comparable.append((previous, current, previous_balance, current_balance))
    if not comparable:
        return None

    ascending_matches = 0
    descending_matches = 0
    for previous, current, previous_balance, current_balance in comparable:
        ascending_expected = previous_balance + money(current.get("credit")) - money(current.get("debit"))
        descending_expected = current_balance + money(previous.get("credit")) - money(previous.get("debit"))
        if abs(current_balance - ascending_expected) <= tolerance:
            ascending_matches += 1
        if abs(previous_balance - descending_expected) <= tolerance:
            descending_matches += 1
    return round(max(ascending_matches, descending_matches) / len(comparable), 4)


def compute_extraction_metrics(transactions, balance_tolerance=0.05):
    total = len(transactions)
    descriptions = sum(1 for row in transactions if str(row.get("description") or row.get("remarks") or "").strip())
    dates = sum(1 for row in transactions if parse_date(row.get("date") or row.get("transactionDate")))
    valid_amount_direction = sum(
        1 for row in transactions
        if (money(row.get("debit")) > 0) != (money(row.get("credit")) > 0)
    )
    description_lengths = [
        len(str(row.get("description") or row.get("remarks") or "").strip())
        for row in transactions
        if str(row.get("description") or row.get("remarks") or "").strip()
    ]
    return {
        "transaction_count": total,
        "description_coverage": ratio(descriptions, total),
        "date_coverage": ratio(dates, total),
        "amount_direction_coverage": ratio(valid_amount_direction, total),
        "balance_continuity_coverage": balance_continuity_coverage(transactions, balance_tolerance),
        "median_description_length": round(statistics.median(description_lengths), 2) if description_lengths else 0.0,
    }


def load_cases(path):
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("Expected regression file to contain a list of cases.")
    return data


def evaluate_check(checks, name, passed, weight, actual, expected):
    checks.append({
        "name": name,
        "passed": bool(passed),
        "weight": weight,
        "actual": actual,
        "expected": expected,
    })


def run_case(case):
    case_id = case.get("id") or case.get("file") or "unnamed-case"
    fixture = ROOT / case["file"]
    if not fixture.exists():
        return {
            "id": case_id,
            "status": "SKIP",
            "message": f"fixture not found at {fixture}",
            "score": None,
            "checks": [],
        }

    bank = case.get("bank", "auto")
    results = extract_transactions(str(fixture), bank_identifier=bank)
    transactions = []
    metadata = {}
    for statement in results:
        transactions.extend(statement.get("transactions", []))
        if not metadata and statement.get("metadata"):
            metadata = statement["metadata"]

    validation = validate_totals(transactions, metadata)
    tolerance = money(case.get("tolerance", 0.01))
    metrics = compute_extraction_metrics(
        transactions,
        balance_tolerance=money(case.get("balance_tolerance", 0.05)),
    )
    checks = []
    errors = []

    expected_count = case.get("expected_transaction_count")
    count_passed = expected_count is None or len(transactions) == int(expected_count)
    evaluate_check(checks, "transaction_count", count_passed, 15, len(transactions), expected_count)
    if not count_passed:
        errors.append(f"count expected {expected_count}, got {len(transactions)}")

    expected_debit = case.get("expected_total_debit")
    actual_debit = money(validation.get("extracted_total_debit"))
    debit_passed = expected_debit is None or abs(actual_debit - money(expected_debit)) <= tolerance
    evaluate_check(checks, "total_debit", debit_passed, 20, actual_debit, expected_debit)
    if not debit_passed:
        errors.append(f"debit expected {money(expected_debit):.2f}, got {actual_debit:.2f}")

    expected_credit = case.get("expected_total_credit")
    actual_credit = money(validation.get("extracted_total_credit"))
    credit_passed = expected_credit is None or abs(actual_credit - money(expected_credit)) <= tolerance
    evaluate_check(checks, "total_credit", credit_passed, 20, actual_credit, expected_credit)
    if not credit_passed:
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

    quality_thresholds = (
        ("description_coverage", "minimum_description_coverage", 15, 0.90),
        ("date_coverage", "minimum_date_coverage", 10, 0.95),
        ("amount_direction_coverage", "minimum_amount_direction_coverage", 10, 0.99),
        ("balance_continuity_coverage", "minimum_balance_continuity_coverage", 10, 0.90),
    )
    for metric_name, setting_name, weight, default_threshold in quality_thresholds:
        threshold = float(case.get(setting_name, default_threshold))
        actual = metrics[metric_name]
        passed = actual is not None and actual >= threshold
        evaluate_check(checks, metric_name, passed, weight, actual, threshold)
        if not passed and setting_name in case:
            errors.append(f"{metric_name} expected >= {threshold:.2%}, got {actual if actual is not None else 'unavailable'}")

    score = round(sum(check["weight"] for check in checks if check["passed"]), 2)
    minimum_score = float(case.get("minimum_score", 0))
    if score < minimum_score:
        errors.append(f"benchmark score expected >= {minimum_score:.0f}, got {score:.0f}")

    return {
        "id": case_id,
        "bank": bank,
        "status": "FAIL" if errors else "PASS",
        "message": "; ".join(errors) if errors else f"{len(transactions)} transactions, score {score:.0f}/100",
        "score": score,
        "metrics": metrics,
        "validation": {
            "totals_match": validation.get("totals_match"),
            "extracted_total_debit": actual_debit,
            "extracted_total_credit": actual_credit,
        },
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description="Run scored statement extraction regression checks.")
    parser.add_argument(
        "--expectations",
        default=ROOT / "tests" / "regression" / "expected_statements.json",
        type=Path,
        help="Path to the expectations JSON file.",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        help="Optional path for a machine-readable benchmark report.",
    )
    args = parser.parse_args()

    cases = load_cases(args.expectations)
    active_cases = [case for case in cases if case.get("enabled", True)]
    if not active_cases:
        print("SKIP: no enabled regression cases.")
        return 0

    reports = []
    for case in active_cases:
        report = run_case(case)
        reports.append(report)
        print(f"{report['status']}: {report['id']}: {report['message']}")

    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(reports, indent=2), encoding="utf-8")

    return 1 if any(report["status"] == "FAIL" for report in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
