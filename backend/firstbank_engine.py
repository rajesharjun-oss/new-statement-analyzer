from pathlib import Path
from typing import Any, Dict, List, Tuple

import pdfplumber


def extract_firstbank_via_coordinates(
    pdf_path: Path,
    metadata: Dict[str, Any],
    pdf: pdfplumber.PDF | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from pdf_extractor import (
        assign_row_to_cols,
        detect_firstbank_columns,
        group_words_to_rows,
        is_noise_row,
        merge_multiline_rows,
        parse_money,
    )

    _auto_close = False
    if pdf is None:
        pdf = pdfplumber.open(pdf_path)
        _auto_close = True

    all_rows: List[Dict[str, Any]] = []
    cuts = None

    try:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            if not words:
                continue

            page_cuts = detect_firstbank_columns(words)
            if page_cuts:
                cuts = page_cuts

            if not cuts:
                continue

            for rg in group_words_to_rows(words, y_tol=3.0):
                row = assign_row_to_cols(rg["words"], cuts)
                row["_raw_text"] = " ".join(w["text"] for w in rg["words"])
                if is_noise_row(row):
                    continue
                row["_page"] = page_num
                all_rows.append(row)

        txns = merge_multiline_rows(all_rows)
        cleaned: List[Dict[str, Any]] = []
        for txn in txns:
            debit = parse_money(txn.get("debit", ""))
            credit = parse_money(txn.get("credit", ""))
            balance = parse_money(txn.get("balance", ""))
            if debit == 0.0 and credit == 0.0 and balance == 0.0:
                continue
            txn["debit"] = debit
            txn["credit"] = credit
            txn["balance"] = balance
            cleaned.append(txn)

        return cleaned, metadata
    finally:
        if _auto_close:
            pdf.close()
