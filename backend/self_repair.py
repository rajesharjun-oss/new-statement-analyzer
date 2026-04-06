import re
from typing import List, Dict, Any, Tuple
import pandas as pd

def parse_money(val: Any) -> float:
    """Parse money safely. Returns 0.0 if empty/invalid."""
    if val is None:
        return 0.0
    s = str(val).strip()
    if not s:
        return 0.0
    # Common OCR artifacts for Nigerian Naira or minus signs
    s = s.replace("₦", "").replace("N", "").replace(",", "").replace("(", "-").replace(")", "").strip()
    try:
        # Regex to extract numeric parts including decimal
        match = re.search(r"(-?\d+\.?\d*)", s)
        if match:
            return float(match.group(1))
        return 0.0
    except (ValueError, TypeError):
        return 0.0

def verify_balance_chain(transactions: List[Dict[str, Any]], opening_balance: float = None) -> List[Dict[str, Any]]:
    """
    Analyzes a list of transactions to find where the running balance breaks.
    Returns a list of 'Gap' descriptors indicating suspect ranges.
    """
    gaps = []
    if not transactions:
        return gaps

    # Use first transaction's balance as starting point if opening_balance not provided
    # Note: This is an assumption; ideally we get opening_balance from metadata
    current_bal = opening_balance if opening_balance is not None else 0.0
    
    # If opening_balance is None, we assume the first transaction's balance - (credit - debit)
    if opening_balance is None and len(transactions) > 0:
        first = transactions[0]
        current_bal = parse_money(first.get("balance", 0)) - (parse_money(first.get("credit", 0)) - parse_money(first.get("debit", 0)))
        current_bal = round(current_bal, 2)

    for i, txn in enumerate(transactions):
        d = parse_money(txn.get("debit", 0))
        c = parse_money(txn.get("credit", 0))
        claimed_bal = parse_money(txn.get("balance", 0))
        
        expected_bal = round(current_bal + c - d, 2)
        
        if abs(expected_bal - claimed_bal) > 0.05: # 5 kobo tolerance
            gaps.append({
                "index": i,
                "date": txn.get("date"),
                "description": txn.get("description"),
                "expected": expected_bal,
                "claimed": claimed_bal,
                "diff": round(claimed_bal - expected_bal, 2),
                "page": txn.get("page_number", "Unknown")
            })
            # Reset current_bal to the claimed balance to find the NEXT gap
            current_bal = claimed_bal
        else:
            current_bal = claimed_bal
            
    return gaps

def find_failed_pages(gaps: List[Dict[str, Any]]) -> List[int]:
    """Extract distinct page numbers from gaps."""
    pages = set()
    for g in gaps:
        p = g.get("page")
        if isinstance(p, int):
            pages.add(p)
        elif isinstance(p, str) and p.isdigit():
            pages.add(int(p))
    return sorted(list(pages))

def identify_math_leaks(transactions: List[Dict[str, Any]], statement_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Comprehensive audit of the extraction result.
    """
    total_debit = sum(parse_money(t.get("debit", 0)) for t in transactions)
    total_credit = sum(parse_money(t.get("credit", 0)) for t in transactions)
    
    stmt_debit = parse_money(statement_metadata.get("statement_total_debit", 0))
    stmt_credit = parse_money(statement_metadata.get("statement_total_credit", 0))
    
    debit_match = abs(total_debit - stmt_debit) < 0.1
    credit_match = abs(total_credit - stmt_credit) < 0.1
    
    gaps = verify_balance_chain(transactions, parse_money(statement_metadata.get("opening_balance")))
    
    return {
        "debit_match": debit_match,
        "credit_match": credit_match,
        "debit_diff": round(total_debit - stmt_debit, 2),
        "credit_diff": round(total_credit - stmt_credit, 2),
        "gaps": gaps,
        "failed_pages": find_failed_pages(gaps),
        "is_perfect": debit_match and credit_match and len(gaps) == 0
    }
