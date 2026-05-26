from pathlib import Path
from typing import Any, Dict, List, Tuple

import pdfplumber

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    fitz = None
    PYMUPDF_AVAILABLE = False


def _pymupdf_words(doc: Any, page_index: int) -> List[Dict[str, Any]]:
    """Return visible-page words in pdfplumber's word shape."""
    page = doc[page_index]
    page_height = float(page.rect.height)
    words: List[Dict[str, Any]] = []
    for w in page.get_text("words"):
        text = (w[4] or "").strip()
        if not text:
            continue
        words.append({
            "text": text,
            "x0": float(w[0]),
            "top": float(w[1]),
            "x1": float(w[2]),
            "bottom": float(w[3]),
            "doctop": float(w[1]) + page_index * page_height,
        })
    return words


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
    fast_doc = None
    use_fast_words = False

    try:
        if len(pdf.pages) > 100 and PYMUPDF_AVAILABLE:
            try:
                fast_doc = fitz.open(pdf_path)
                use_fast_words = True
                print("DEBUG: FirstBank fast mode using PyMuPDF visible-page words.")
            except Exception as exc:
                print(f"DEBUG: FirstBank fast mode unavailable: {exc}")
                fast_doc = None
                use_fast_words = False

        for page_num, page in enumerate(pdf.pages, start=1):
            words = (
                _pymupdf_words(fast_doc, page_num - 1)
                if use_fast_words and fast_doc is not None
                else page.extract_words(x_tolerance=2, y_tolerance=2)
            )
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
        if fast_doc is not None:
            try:
                fast_doc.close()
            except Exception:
                pass
        if _auto_close:
            pdf.close()
