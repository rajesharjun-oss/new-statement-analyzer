"""
Bank-Specific Configuration
Defines patterns and rules for different banks
"""
from typing import Dict, Any

# Bank-specific configurations
BANK_CONFIGS = {
    "gtbank": {
        "name": "GTBank",
        "header_patterns": {
            "trans_date": r"Trans\.?\s*Date",
            "value_date": r"Value\.?\s*Date",
            "reference": r"Refer",
            "debit": r"Deb",
            "credit": r"Cred",
            "balance": r"Bal",
            "remarks": r"Remarks?"
        },
        "metadata_patterns": {
            "account_name": r"CUSTOMER STATEMENT\s*([\s\S]*?)\s*Trans\.\s*Date",
            "statement_period": r"Statement Period\s*:\s*(.+)",
            "total_debit": r"Total Debit\s*([\d,]+\.\d{2})",
            "total_credit": r"Total Credit\s*([\d,]+\.\d{2})",
            "opening_balance": r"Opening Balance\s*([\d,]+\.\d{2})",
            "closing_balance": r"Closing Balance\s*([\d,]+\.\d{2})"
        }
    },
    "accessbank": {
        "name": "Access Bank",
        "header_patterns": {
            "trans_date": r"Transaction\.?\s*Date",
            "value_date": r"Value\.?\s*Date",
            "reference": r"Ref",
            "debit": r"Debit",
            "credit": r"Credit",
            "balance": r"Balance",
            "remarks": r"Description|Narration"
        },
        "metadata_patterns": {
            "account_name": r"Account Name[:\s]+([A-Z\s&]+)",
            "statement_period": r"Period[:\s]+(\d{2}-\w{3}-\d{4})\s+to\s+(\d{2}-\w{3}-\d{4})",
            "total_debit": r"Total Debit[:\s]+([\d,]+\.\d{2})",
            "total_credit": r"Total Credit[:\s]+([\d,]+\.\d{2})",
            "opening_balance": r"Opening Balance[:\s]+([\d,]+\.\d{2})",
            "closing_balance": r"Closing Balance[:\s]+([\d,]+\.\d{2})"
        }
    },
    "firstbank": {
        "name": "First Bank",
        "header_patterns": {
            "trans_date": r"Trans\.?\s*Date",
            "value_date": r"Value\.?\s*Date",
            "reference": r"Reference",
            "debit": r"Debit",
            "credit": r"Credit",
            "balance": r"Balance",
            "remarks": r"Particulars|Details"
        },
        "metadata_patterns": {
            "account_name": r"Account Name[:\s]+([A-Z\s&]+)",
            "statement_period": r"Statement Period[:\s]+(.+)",
            "total_debit": r"Total Debit[:\s]+([\d,]+\.\d{2})",
            "total_credit": r"Total Credit[:\s]+([\d,]+\.\d{2})",
            "opening_balance": r"Opening Balance[:\s]+([\d,]+\.\d{2})",
            "closing_balance": r"Closing Balance[:\s]+([\d,]+\.\d{2})"
        }
    },
    "zenith": {
        "name": "Zenith Bank",
        "header_patterns": {
            "trans_date": r"Date",
            "value_date": r"Value\.?\s*Date",
            "reference": r"Ref",
            "debit": r"Debit",
            "credit": r"Credit",
            "balance": r"Balance",
            "remarks": r"Description"
        },
        "metadata_patterns": {
            "account_name": r"Account Name[:\s]+([A-Z\s&]+)",
            "statement_period": r"Period[:\s]+(.+)",
            "total_debit": r"Total Debit[:\s]+([\d,]+\.\d{2})",
            "total_credit": r"Total Credit[:\s]+([\d,]+\.\d{2})",
            "opening_balance": r"Opening Balance[:\s]+([\d,]+\.\d{2})",
            "closing_balance": r"Closing Balance[:\s]+([\d,]+\.\d{2})"
        }
    },
    "uba": {
        "name": "UBA",
        "header_patterns": {
            "trans_date": r"Trans\.?\s*Date",
            "value_date": r"Value\.?\s*Date",
            "reference": r"Reference",
            "debit": r"Debit",
            "credit": r"Credit",
            "balance": r"Balance",
            "remarks": r"Narration"
        },
        "metadata_patterns": {
            "account_name": r"Account Name[:\s]+([A-Z\s&]+)",
            "statement_period": r"Statement Period[:\s]+(.+)",
            "total_debit": r"Total Debit[:\s]+([\d,]+\.\d{2})",
            "total_credit": r"Total Credit[:\s]+([\d,]+\.\d{2})",
            "opening_balance": r"Opening Balance[:\s]+([\d,]+\.\d{2})",
            "closing_balance": r"Closing Balance[:\s]+([\d,]+\.\d{2})"
        }
    }
}

def get_bank_config(bank_identifier: str) -> Dict[str, Any] | None:
    """
    Get bank-specific configuration
    
    Args:
        bank_identifier: Bank identifier (e.g., 'gtbank', 'auto')
        
    Returns:
        Bank configuration dict or None for auto-detection
    """
    if bank_identifier == "auto":
        return None
    
    return BANK_CONFIGS.get(bank_identifier.lower())
