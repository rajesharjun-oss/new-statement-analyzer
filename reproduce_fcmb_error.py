import sys
import os
from pathlib import Path

# Add backend to path
backend_path = os.path.join(os.getcwd(), "backend")
sys.path.insert(0, backend_path)

from excel_generator import generate_excel

def test_fcmb_error():
    # Character that breaks OpenPyXL (\x0b is vertical tab, often illegal in XML)
    buggy_description = "6090043407327 TRANSACTION CHARGE-web: Facilita\x0bon 53 NIP/251003155"
    
    transactions = [
        {
            'date': '2025-12-10',
            'value_date': '2025-12-10',
            'reference': 'S4751947',
            'description': buggy_description,
            'category': 'Charges',
            'debit': 53.00,
            'credit': 0.00,
            'balance': 30803319.11
        }
    ]
    
    validation = {
        'extracted_total_debit': 53.00,
        'extracted_total_credit': 0.00,
        'status': 'Match'
    }
    
    output_path = Path("test_fcmb_output.xlsx")
    
    try:
        print(f"Attempting to generate Excel with buggy description...")
        generate_excel(transactions, validation, output_path)
        print("SUCCESS: Excel generated successfully without IllegalCharacterError.")
    except Exception as e:
        print(f"FAILURE: Excel generation failed with error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fcmb_error()
