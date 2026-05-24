import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from pdf_extractor import extract_transactions, parse_money  # noqa: E402
from validation import validate_totals  # noqa: E402


def guess_bank(path: Path) -> str:
    name = path.name.lower()
    if "access" in name:
        return "access"
    if "uba" in name:
        return "uba"
    if "wema" in name:
        return "wema"
    if "fcmb" in name:
        return "fcmb"
    if "zenith" in name:
        return "zenith"
    if "providus" in name:
        return "providus"
    if "sterling" in name:
        return "sterling"
    if "fidelity" in name:
        return "fidelity"
    if "fbn" in name or "first bank" in name:
        return "firstbank"
    if "gtbank" in name or "gt bank" in name or "gtco" in name:
        return "gtbank"
    return "auto"


def num(value):
    if isinstance(value, (int, float)):
        return float(value)
    return parse_money(str(value or ""))


def run_file(path: Path, bank: str) -> dict:
    started = time.perf_counter()
    result = {
        "file": str(path),
        "bank_hint": bank,
        "status": "ERROR",
        "seconds": None,
        "statements": 0,
        "transaction_count": 0,
        "extracted_total_debit": 0.0,
        "extracted_total_credit": 0.0,
        "statement_total_debit": None,
        "statement_total_credit": None,
        "opening_balance": None,
        "closing_balance": None,
        "detected_bank": None,
        "validation_status": None,
        "totals_match": None,
        "error": None,
    }
    try:
        statement_results = extract_transactions(str(path), bank_identifier=bank)
        txns = []
        primary_meta = {}
        for statement in statement_results:
            statement_txns = statement.get("transactions", [])
            txns.extend(statement_txns)
            if statement_txns and not primary_meta:
                primary_meta = statement.get("metadata", {})
        if not primary_meta and statement_results:
            primary_meta = statement_results[0].get("metadata", {})

        validation = validate_totals(txns, primary_meta)
        result.update(
            {
                "status": "OK",
                "statements": len(statement_results),
                "transaction_count": len(txns),
                "extracted_total_debit": round(sum(num(t.get("debit")) for t in txns), 2),
                "extracted_total_credit": round(sum(num(t.get("credit")) for t in txns), 2),
                "statement_total_debit": primary_meta.get("statement_total_debit"),
                "statement_total_credit": primary_meta.get("statement_total_credit"),
                "opening_balance": primary_meta.get("opening_balance"),
                "closing_balance": primary_meta.get("closing_balance"),
                "detected_bank": primary_meta.get("bank"),
                "validation_status": validation.get("status"),
                "totals_match": validation.get("totals_match"),
            }
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["seconds"] = round(time.perf_counter() - started, 2)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Baseline a folder of PDF bank statements.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "debug-output" / "statement-baseline.json")
    parser.add_argument("--top-level-only", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    pattern = "*.pdf" if args.top_level_only else "**/*.pdf"
    files = sorted(args.folder.glob(pattern))
    files = [f for f in files if "PAYE RECEIPTS" not in str(f).upper()]
    if args.limit:
        files = files[: args.limit]

    results = []
    for idx, path in enumerate(files, 1):
        bank = guess_bank(path)
        print(f"[{idx}/{len(files)}] {path.name} ({bank})", flush=True)
        result = run_file(path, bank)
        results.append(result)
        print(
            f"  {result['status']} txns={result['transaction_count']} "
            f"match={result['totals_match']} seconds={result['seconds']} "
            f"{result['validation_status'] or result['error']}",
            flush=True,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
