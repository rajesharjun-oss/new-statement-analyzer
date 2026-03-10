import sys
import os

# Add backend to path
backend_path = os.path.join(os.getcwd(), "backend")
sys.path.insert(0, backend_path)

from pdf_extractor import detect_firstbank_columns

def debug_header():
    # Simulated words from First Bank header
    # Headers: Trans Date | Ref. Number | Transaction Details | Value Date | Withdrawal(DR) | Deposit(CR) | Balance
    
    words = [
        {"text": "Trans", "x0": 50, "x1": 80, "top": 100, "bottom": 112},
        {"text": "Date", "x0": 85, "x1": 115, "top": 100, "bottom": 112},
        {"text": "Ref.", "x0": 130, "x1": 155, "top": 100, "bottom": 112},
        {"text": "Number", "x0": 160, "x1": 210, "top": 100, "bottom": 112},
        {"text": "Transaction", "x0": 230, "x1": 310, "top": 100, "bottom": 112},
        {"text": "Details", "x0": 315, "x1": 360, "top": 100, "bottom": 112},
        {"text": "Value", "x0": 580, "x1": 615, "top": 100, "bottom": 112},
        {"text": "Date", "x0": 620, "x1": 650, "top": 100, "bottom": 112},
        {"text": "Withdrawal", "x0": 680, "x1": 740, "top": 100, "bottom": 112},
        {"text": "(DR)", "x0": 745, "x1": 770, "top": 100, "bottom": 112},
        {"text": "Deposit", "x0": 780, "x1": 830, "top": 100, "bottom": 112},
        {"text": "(CR)", "x0": 835, "x1": 860, "top": 100, "bottom": 112},
        {"text": "Balance", "x0": 870, "x1": 930, "top": 100, "bottom": 112},
    ]
    
    print("Testing detect_firstbank_columns with exact screenshot headers...")
    cuts = detect_firstbank_columns(words)
    
    if cuts:
        print("SUCCESS: Cuts detected:")
        for col, (l, r) in cuts.items():
            print(f"  {col:12}: {l:6.1f} - {r:6.1f}")
        
        if "credit" in cuts:
            print("CREDIT COLUMN FOUND.")
        else:
            print("CREDIT COLUMN MISSING!")
    else:
        print("FAILURE: detect_firstbank_columns returned None.")

if __name__ == "__main__":
    debug_header()
