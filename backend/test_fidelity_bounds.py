import sys
from pdf_extractor import extract_words_from_pypdf

def debug_fidelity_header(pdf_path):
    print("Testing on", pdf_path)
    words = extract_words_from_pypdf(pdf_path, 0)
    
    y_tol = 3.0
    rows = []
    for w in sorted(words, key=lambda d: (d["top"], d["x0"])):
        placed = False
        for r in rows:
            if abs(w["top"] - r["top"]) <= y_tol:
                r["words"].append(w)
                r["top"] = (r["top"] + w["top"]) / 2
                placed = True
                break
        if not placed:
            rows.append({"top": w["top"], "words": [w]})
    for r in rows:
        r["words"].sort(key=lambda d: d["x0"])
        
    print("Header Row words:")
    # Look for the row with 'Date' or 'Value Date'
    for r in rows:
        text = " ".join([w["text"] for w in r["words"]])
        if "Date" in text or "Details" in text:
            for w in r["words"]:
                print(f"'{w['text']}' at x0={w['x0']:.2f}, x1={w['x1']:.2f}")

if __name__ == "__main__":
    import glob
    import os
    latest_pdf = sorted(glob.glob("../temp_uploads/*.pdf"), key=os.path.getmtime)[-1]
    debug_fidelity_header("FIDELITY 1 2024.pdf")
