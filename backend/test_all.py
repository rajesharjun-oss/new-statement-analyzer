import sys, warnings, os
warnings.filterwarnings('ignore')
import logging; logging.disable(logging.CRITICAL)
sys.path.insert(0, '.')
from pdf_extractor import extract_transactions
from pathlib import Path

LABELS = {
    "2021_Standard_Chartered_Bank_USD": "Std Chartered USD",
    "Access2.0": "Access Bank",
    "FBN_2024": "First Bank",
    "FCMB_test": "FCMB",
    "FIDELITY_1_2024": "Fidelity ODA-1",
    "FIDELITY_2_2024": "Fidelity CAA-2",
    "FIDELITY_3_2024": "Fidelity ODA-3",
    "GTCO_test": "GTBank-1",
    "GTCO_test_2": "GTBank-2",
    "Standard_chartered_test": "Std Chartered test",
    "STERLING_2024-0048033663_(2)": "Sterling (small)",
    "STERLING_test": "Sterling (large)",
    "WEMA-0122806362_2024": "WEMA (tiny)",
    "WEMA_Large": "WEMA Large",
    "WEMA_test": "WEMA test",
}

pdfs = sorted(Path('temp_uploads').glob('*.pdf'))
print(f"{'File':<24} {'Txns':>6} {'Errors':>7} {'Opening':>20} {'Closing':>20}")
print('-'*82)
for pdf in pdfs:
    short = pdf.stem
    for key in LABELS:
        if key in short:
            short = LABELS[key]; break
    else:
        short = short[:24]
    try:
        results = extract_transactions(str(pdf))
        txns = []
        for r in results:
            txns.extend(r.get('transactions', []))
        if not txns:
            print(f"{short:<24} {'0':>6} {'N/A':>7} {'NO TRANSACTIONS':>42}")
            continue
        errs = 0
        for i in range(1, len(txns)):
            pb = txns[i-1].get('balance') or 0
            cb = txns[i].get('balance') or 0
            d = txns[i].get('debit') or 0
            c = txns[i].get('credit') or 0
            if abs(round(pb - d + c, 2) - cb) > 1.0:
                errs += 1
        bals = [t.get('balance') or 0 for t in txns]
        flag = "  ✓" if errs == 0 else f"  ✗ {errs} chain errors"
        print(f"{short:<24} {len(txns):>6} {errs:>7} {bals[0]:>20,.2f} {bals[-1]:>20,.2f}{flag}")
    except Exception as e:
        print(f"{short:<24} {'ERR':>6} {'N/A':>7} {str(e)[:50]}")
    sys.stdout.flush()
