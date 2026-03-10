from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from typing import List, Dict, Any
import re
from pathlib import Path

# Illegal characters for Excel/XML
# See: https://stackoverflow.com/questions/13010323/illegal-characters-in-openpyxl-excel
ILLEGAL_CHARACTERS_RE = re.compile(r'[\000-\010\013\014\016-\037]')

def clean_for_excel(val):
    """Strip illegal characters that break openpyxl/XML"""
    if not isinstance(val, str):
        return val
    # Some bank statements contain characters like \0 (null) or other control chars
    return ILLEGAL_CHARACTERS_RE.sub('', val)

def generate_excel(transactions: List[Dict], validation: Dict[str, Any], output_path: Path):
    """
    Generate Excel file with transactions and summary
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    
    # Headers - Match bank statement layout
    # CANONICAL SCHEMA — bank-agnostic, always the same regardless of source bank
    headers = ['Date', 'Value Date', 'Reference', 'Description', 'Category', 'Debit', 'Credit', 'Balance']
    ws.append(headers)
    
    # Style headers
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
    
    # Add transactions - Keep columns separate
    # Write dates as STRINGS to prevent Excel from converting to Month-Year format
    for txn in transactions:
        # 'description' = narration only (no reference prefix) — avoids duplication with Reference column
        # Fall back to 'remarks' for banks whose extractors set remarks but not description
        desc = (
            txn.get('description') or
            txn.get('remarks') or
            txn.get('originating_branch') or ''
        )
        ws.append([
            clean_for_excel(str(txn.get('date', ''))),       # String prevents Excel date conversion
            clean_for_excel(str(txn.get('value_date', ''))), # String prevents Excel date conversion
            clean_for_excel(txn.get('reference', '')),
            clean_for_excel(desc),                           # Narration only — reference is already in its own column
            clean_for_excel(txn.get('category', 'Unallocated')),
            txn.get('debit', 0),
            txn.get('credit', 0),
            txn.get('balance', 0)
        ])
    
    # Add summary section
    summary_row = len(transactions) + 3
    ws[f'A{summary_row}'] = 'SUMMARY'
    ws[f'A{summary_row}'].font = Font(bold=True, size=14)
    
    ws[f'A{summary_row + 1}'] = 'Total Debit:'
    ws[f'B{summary_row + 1}'] = validation.get('extracted_total_debit', 0)
    ws[f'B{summary_row + 1}'].number_format = '#,##0.00'
    
    ws[f'A{summary_row + 2}'] = 'Total Credit:'
    ws[f'B{summary_row + 2}'] = validation.get('extracted_total_credit', 0)
    ws[f'B{summary_row + 2}'].number_format = '#,##0.00'
    
    ws[f'A{summary_row + 3}'] = 'Validation:'
    ws[f'B{summary_row + 3}'] = validation.get('status', 'Unknown')
    
    # Adjust column widths
    ws.column_dimensions['A'].width = 12   # Date
    ws.column_dimensions['B'].width = 12   # Value Date
    ws.column_dimensions['C'].width = 20   # Reference
    ws.column_dimensions['D'].width = 55   # Description (canonical)
    ws.column_dimensions['E'].width = 22   # Category
    ws.column_dimensions['F'].width = 15   # Debit
    ws.column_dimensions['G'].width = 15   # Credit
    ws.column_dimensions['H'].width = 15   # Balance
    
    # Save
    wb.save(output_path)
