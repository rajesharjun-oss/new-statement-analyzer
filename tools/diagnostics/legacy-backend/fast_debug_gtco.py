import re
import math
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
from pypdf import PdfReader

sys.path.append(str(Path(".").absolute()))
import pdf_extractor

def group_words_to_rows_stable(words, y_tol):
    if not words: return []
    sorted_words = sorted(words, key=lambda d: (d["top"], d["x0"]))
    
    rows = []
    for w in sorted_words:
        placed = False
        if rows:
            r = rows[-1]
            if abs(w["top"] - r["initial_top"]) <= y_tol:
                r["words"].append(w)
                placed = True
        
        if not placed:
            rows.append({
                "initial_top": w["top"], 
                "top": w["top"], 
                "words": [w]
            })
    
    for r in rows:
        r["words"].sort(key=lambda d: d["x0"])
    return rows

def extract_words_from_pypdf(pdf_path: str, page_idx: int) -> List[Dict[str, Any]]:
    reader = PdfReader(pdf_path)
    page = reader.pages[page_idx]
    mbox = page.mediabox
    page_height = float(mbox.height)
    
    words = []
    def visitor(text, cm, tm, fontDict, fontSize):
        if text.strip():
            # tm[4] = x0, tm[5] = y0
            x0 = float(tm[4])
            y0 = float(tm[5])
            # TM scale info is in tm[0] and tm[3] usually, but fontSize is passed
            words.append({
                "text": text,
                "x0": x0,
                "x1": x0 + (len(text) * fontSize * 0.5), # Heuristic
                "top": page_height - y0 - fontSize,
                "bottom": page_height - y0,
                "upright": True
            })
    page.extract_text(visitor_text=visitor)
    return words

pdf_path = "temp_uploads/GTCO test 2.pdf"

print("Extracting words (PYPDF)...")
words = extract_words_from_pypdf(pdf_path, 0)
print(f"Extracted {len(words)} words.")

print("Detecting columns...")
cuts = pdf_extractor.detect_column_cuts_from_header(words, "gtco")
print(f"Cuts: {cuts}")

print("Grouping rows (STABLE)...")
row_groups = group_words_to_rows_stable(words, y_tol=12.0)

all_rows = []
print("Assigning columns...")
for rg in row_groups:
    row = pdf_extractor.assign_row_to_cols(rg["words"], cuts)
    def has_any_text(row: dict) -> bool:
        for v in row.values():
            if isinstance(v, str) and v.strip(): return True
        return False
    if has_any_text(row):
        raw_text = " ".join([w["text"] for w in rg["words"]])
        row["_page"] = 1
        row["_raw_text"] = raw_text
        all_rows.append(row)
            
print(f"Total rows before merge: {len(all_rows)}")

print("\n--- FIRST 50 ROWS ---")
for idx, r in enumerate(all_rows[:50]):
    print(f"Row {idx}: {r}")
    
print("\nMerging rows...")
txns = pdf_extractor.merge_multiline_rows(all_rows)
print(f"Total transactions after merge: {len(txns)}")

print("\n--- MERGED TRANSACTIONS ---")
for t in txns:
    print(t)
