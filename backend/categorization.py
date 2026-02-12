"""
Categorization Service
Ported from services/categorizationRules.ts
"""
import re
import os
import math
from typing import List, Dict, Any, Optional
from openai import OpenAI

# --- 1. CONFIGURATION ---

class Rule:
    def __init__(self, id: str, priority: int, pattern: str, category: str, 
                 confidence: float, side: str = 'both', exclude: Optional[str] = None):
        self.id = id
        self.priority = priority
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.category = category
        self.confidence = confidence
        self.side = side  # 'debit', 'credit', 'both'
        self.exclude = re.compile(exclude, re.IGNORECASE) if exclude else None

# Rules defined in the Spec (R001 - R090)
RULES = [
    Rule("R001_OPENING_BALANCE", 1, r"OPENING\s+BAL|BAL\s*B\/F|BALANCE\s*BROUGHT|B\/F\b|BROUGHT\s*FORWARD", "Opening Balance", 1.0, "both"),
    
    # INFLOWS (High Priority)
    Rule("R005_INWARD_TRANSFERS", 5, r"NIP\s*FROM|TRF\s*FROM|CREDIT\s*FROM|DEPOSIT\b|INFLOW\b", "Operating Income", 0.9, "credit"),
    
    # BANK CHARGES & LEVIES (High Priority)
    Rule("R010_BANK_STAMP_DUTY", 10, r"STAMP\s*DUTY|FGN\s*STAMPDUTY", "Bank Charges", 1.0, "debit"),
    Rule("R011_BANK_CHARGES_CORE", 11, r"SMS\s*CHARGE|SMS\b|COMMISSION|COMM\b|TRANSFER\s*CHARGE|BANK\s*CHARGE|MAINTENANCE\s*(?:FEE|CHG|CHARGE)|ACCT\s*MAINT|ACCOUNT\s*MAINT|AMF\b|NIP\s*CHG|NIP\s*FEE|TRF\s*CHG|TRF\s*FEE|UBR\s*CHG", "Bank Charges", 1.0, "debit"),
    Rule("R012_GOVT_LEVIES_TAXES", 12, r"ELECTRONIC\s*MONEY\s*TRANSFER\s*LEVY|EMTL|VAT\b|TAX\b|FGN\s*LEVY|VAT\s*ON\s*CHG|VAT\s*ON\s*TRF|VAT\s*ON\s*NIP", "Bank Charges", 1.0, "debit"),
    
    # --- FIX 9: BANK CHARGES CLASSIFICATION ---
    Rule("R013_LEVY_50_AMOUNT", 13, r"LEVY", "Bank Charges", 1.0, "debit"), # Will be refined by amount check in code
    Rule("R014_SPECIFIC_AMOUNT_CHARGES", 14, r".*", "Bank Charges", 0.8, "debit"), # Placeholder for Amount-based rule

    # INTEREST
    Rule("R020_WHT_ON_INTEREST_DEBIT", 20, r"CREDIT\s*INTEREST|INTEREST\b", "WHT Receivable", 1.0, "debit", exclude=r"OVERDRAFT\s*INTEREST|LOAN\s*INTEREST|INTEREST\s*CHARGE"),
    Rule("R021_INTEREST_INCOME_CREDIT", 21, r"CREDIT\s*INTEREST|INTEREST\b", "Interest Income", 1.0, "credit", exclude=r"OVERDRAFT\s*INTEREST|LOAN\s*INTEREST|INTEREST\s*CHARGE"),
    
    # --- FIX 13: INTEREST REVERSAL ---
    Rule("R022_INTEREST_REVERSAL_DEBIT", 22, r"CURRENT\s*ACT\s*CREDIT\s*INTEREST", "Interest Reversal / Adjustment", 1.0, "debit"),
    Rule("R023_INTEREST_INCOME_SPECIFIC", 23, r"CURRENT\s*ACT\s*CREDIT\s*INTEREST", "Interest Income", 1.0, "credit"),
    
    # STAFF
    Rule("R030_SALARY_PAYROLL", 30, r"SALARY\b|PAYROLL\b|WAGES\b|STAFF\s*SAL", "Salaries & Wages", 1.0, "debit"),
    Rule("R031_STAFF_ADVANCE", 31, r"STAFF\s*LOAN|SALARY\s*ADVANCE|ADVANCE\s*TO\s*STAFF", "Staff Debtors / Salary Advances", 1.0, "debit"),
    Rule("R032_STAFF_WELFARE", 32, r"WELFARE|LUNCH|CATERING|TEAM\s*BONDING|GROCERIES", "Staff Welfare", 0.9, "debit"),
    Rule("R033_STAFF_TRAINING", 33, r"TRAINING|WORKSHOP|SEMINAR|COURSE\b|UDEMY|COURSERA", "Staff Training & Development", 0.9, "debit"),
    
    # EXPENSES
    Rule("R040_EVENT_CONFERENCE", 40, r"SUMMIT|CONFERENCE|HEALTHTECH|KIGALI|NAMETAG|NAME\s*TAGS", "Event & Conference Expenses", 1.0, "debit"),
    Rule("R041_TRANSPORT_VEHICLE", 41, r"VEHICLE|TINT|VEHICLE\s*REG|CAR\s*REG|LICENSE|VEHICLE\s*PAPERS|FUEL\b|DIESEL\b", "Transport & Logistics", 1.0, "debit"),
    Rule("R042_REPAIRS_MAINTENANCE", 42, r"REPAIR|MAINTENANCE\s*(?!FEE|CHG|CHARGE|ACCT|ACCOUNT)|SERVICING|PLUMBING|ELECTRICAL|CARPENTRY", "Repairs & Maintenance", 0.9, "debit"),
    
    Rule("R049_FOREIGN_EXAM_FEES", 49, r"\bSAT\b|TOEFL\b|IELTS\b|GRE\b|GMAT\b", "Foreign Exam Fees", 1.0, "both"),
    Rule("R050_EXAM_GENERIC_PASSTHROUGH", 50, r"\bEXAM\b|EXAM\s*FEE|REGISTRATION\s*(?:EXAM|FORM|FEE)|ADMISSION|APPLICATION\s*FORM|COMMON\s*ENTRANCE", "Student Exam Fees (Pass-Through)", 0.95, "both"),
    
    Rule("R055_CAPITAL_PROJECT_VALUATION", 55, r"VALUATION\s*INVOICE|VARIATION\s*INVOICE", "Capital Expenditure (CWIP)", 1.0, "debit"),
    Rule("R060_OFFICE_RENT_CORPORATE_SERVICES", 60, r"CORPORATE\s*SERVICES|SERVICED\s*OFFICE|VICTORIA\s*ISLAND|ADEOLA\s*ODEKU", "Office Rent / Lease", 0.92, "debit"),
    
    Rule("R070_ADMINISTRATIVE_EXPENSES", 70, r"MISCELLANEOUS|MISC\b|OFFICE\s*EXP|STATIONERY|PRINTING|COURIER|NEWSPAPER|SUBSCRIPTION|REGISTRATION\b|INTERNET|DATA\s*BUNDLE|AIRTIME", "Administrative Expenses", 0.95, "debit"),
    
    # CATCH-ALL OUTWARD TRANSFERS (Lowest Priority Rule)
    Rule("R090_GENERIC_OUTWARD_TRANSFER", 90, r"NIP\s*TO|TRF\s*TO|TRF\s*IFO|LOCAL\s*TRANSFERS", "Inter-Account / Treasury Transfer", 0.6, "debit"),
]

# Sort rules by priority (ascending)
SORTED_RULES = sorted(RULES, key=lambda r: r.priority)

def normalize_description(desc: str) -> str:
    if not desc:
        return ""
    # Normalize: Upper case, remove special chars except spaces, collapse multiple spaces
    # NOTE: Python regex char classes in [] don't need escaping for many chars, but safe to match TS logic
    # TS: .replace(/[^A-Z0-9\s]/g, ' ')
    desc = desc.upper()
    desc = re.sub(r'[^A-Z0-9\s]', ' ', desc)
    desc = re.sub(r'\s+', ' ', desc)
    return desc.strip()

def categorize_single_transaction(txn: Dict) -> Dict:
    """
    Apply rules to a single transaction in place.
    """
    raw_desc = txn.get('description', '')
    norm_desc = normalize_description(raw_desc)
    
    # Parse amounts safely
    debit = float(txn.get('debit') or 0)
    credit = float(txn.get('credit') or 0)
    is_debit = debit != 0
    is_credit = credit != 0
    
    updated_cat = None
    confidence = 0.0
    rule_id = None
    decision_source = None
    
    # 0. CHECK REVERSALS
    if re.search(r"REVERSAL|REV\b|RET\b|ERR\b", norm_desc) or re.search(r"REV\s*TRF", norm_desc):
        txn['is_reversal'] = True
    else:
        txn['is_reversal'] = False
        
    # --- FIX 10: CLEAN DESCRIPTION NOISE ---
    # Remove repetitive boilerplate
    for noise in ["LOCAL TRANSFERS OTHER BANKS", "TRN IFO NIP OUTWARD ACCOUNT", "OMNI BO", "NIP TRANSFER", "FROM:"]:
        if noise in norm_desc:
            norm_desc = norm_desc.replace(noise, "").strip()
            # Also clean up double spaces resulting from removal
            norm_desc = re.sub(r'\s+', ' ', norm_desc)
    
    # Store cleaned description for reference/UI if needed, but we use norm_desc for rules
    txn['clean_description'] = norm_desc

    # 1. AMOUNT-BASED CLASSIFICATION (Standard Fees & Specific Rules)
    if is_debit:
        # --- FIX 9: SPECIFIC AMOUNT RULES ---
        abs_amt = abs(debit)
        
        # Rule: Amount == 50 AND "LEVY" -> Bank Charges
        if math.isclose(abs_amt, 50.00, abs_tol=0.01) and "LEVY" in norm_desc:
             updated_cat = "Bank Charges"
             confidence = 1.0
             rule_id = "R013_LEVY_50_AMOUNT"
             decision_source = "RULE_SPECIFIC"

        # Rule: Amount == 3.75 -> Bank Charges
        elif math.isclose(abs_amt, 3.75, abs_tol=0.01):
             updated_cat = "Bank Charges"
             confidence = 1.0
             rule_id = "R014_SPECIFIC_AMOUNT_CHARGES"
             decision_source = "RULE_SPECIFIC"

        # Existing Standard Fee Checks (fallback)
        elif any(math.isclose(abs_amt, amt, abs_tol=0.01) for amt in [50.00, 52.50, 10.00, 4.00, 26.88]):
            # 26.88 is common for some SMS charges
            if not re.search(r"OPENING\s*BAL", norm_desc):
                updated_cat = "Bank Charges"
                confidence = 0.99
                rule_id = "AMT_STD_FEE"
                decision_source = "RULE"

    # 2. RULE ENGINE EXECUTION (Highest Priority overrides Amount)
    # If amount rule triggered, we still check regex rules? 
    # TS logic: "Rule Engine Execution (Highest Priority)" comes AFTER Amount check but returns immediately.
    # WAIT: In TS, Amount check checks if(isDebit && isFeeAmount) ... return updated;
    # So Amount check TAKES PRECEDENCE over Regex rules in the TS code I read (lines 228-235).
    # BUT, the comments say "2. RULE ENGINE EXECUTION (Highest Priority)".
    # Let's perform Regex check. If it matches, it typically overwrites or captures better logic.
    # Actually, in TS code:
    # 1. Amount Check -> Returns if matched.
    # 2. Loop Rules -> Returns if matched.
    # So Amount Check IS higher priority if it matches. I will follow TS logic.
    
    if updated_cat:
        # If amount matched, we are done
        pass
    else:
        for rule in SORTED_RULES:
            if rule.side == 'debit' and not is_debit: continue
            if rule.side == 'credit' and not is_credit: continue
            
            if rule.pattern.search(norm_desc):
                if rule.exclude and rule.exclude.search(norm_desc):
                    continue
                
                updated_cat = rule.category
                confidence = rule.confidence
                rule_id = rule.id
                decision_source = "RULE"
                break
    
    # 3. AI / FALLBACK LOGIC
    if not updated_cat:
        # Heuristics
        bank_charge_keywords = re.compile(r"(?:CHG|COMM|FEE|VAT|TAX|MOBL|SMS|MAINT|LEVY|DUTY)")
        non_bank_contexts = re.compile(r"(?:SCHOOL|TUITION|EXAM|CLASS|LESSON|TRAINING|COURSE|SEMINAR|LEGAL|LAWYER|CONSULT|AUDIT|PROFESSIONAL|RETAINER|MEMBER|LICENSE|SUBSCRIPTION)")
        
        if is_debit and bank_charge_keywords.search(norm_desc) and not non_bank_contexts.search(norm_desc):
            updated_cat = "Bank Charges"
            confidence = 0.8
            decision_source = "RULE"
        
        elif is_debit and re.search(r"(?:TRF|NIP|FRM|TO|MNY|TRANSFER|PYMT|PAYMENT|WEB|POS|ATM)", norm_desc):
            updated_cat = "Inter-Account / Treasury Transfer"
            confidence = 0.6
            decision_source = "AI_HEURISTIC" # Mark as AI/Heuristic
            
        else:
            updated_cat = "Unallocated"
            confidence = 0.0
            decision_source = "AI"

    txn['category'] = updated_cat
    txn['confidence'] = confidence
    if rule_id:
        txn['ruleId'] = rule_id
    if decision_source:
        txn['decision_source'] = decision_source
        
    return txn


def categorize_transactions(transactions: List[Dict]) -> List[Dict]:
    """
    Categorize transactions using rules + AI fallback
    """
    unallocated_indices = []
    
    for i, txn in enumerate(transactions):
        categorize_single_transaction(txn)
        if txn.get('category') == 'Unallocated':
            unallocated_indices.append(i)
            
    # AI fallback for unallocated (batch processing)
    if unallocated_indices and os.getenv('OPENAI_API_KEY'):
        try:
            unallocated = [transactions[i] for i in unallocated_indices]
            # Verify we have items to categorize
            if unallocated:
                categorize_with_ai(unallocated)
        except Exception as e:
            print(f"AI categorization failed: {e}")
            
    return transactions

def categorize_with_ai(transactions: List[Dict]):
    """
    Use OpenAI to categorize unallocated transactions
    """
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    # Batch descriptions
    descriptions = [t.get('description', '') for t in transactions]
    
    prompt = f"""Categorize these bank transactions into one of these categories:
- Salaries & Wages
- Rent
- Utilities
- Fuel
- Office Supplies
- Professional Fees
- Bank Charges
- Tax
- Income
- Transfer Out
- Transfer In
- Unallocated

Transactions:
{chr(10).join(f'{i+1}. {desc}' for i, desc in enumerate(descriptions))}

Return only a JSON array of categories in order, like: ["Income", "Rent", "Utilities", ...]
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        # Parse response
        import json
        content = response.choices[0].message.content
        # robust json fix
        if "```json" in content:
            content = content.replace("```json", "").replace("```", "")
        
        categories = json.loads(content)
        
        for i, category in enumerate(categories):
            if i < len(transactions):
                transactions[i]['category'] = category
                transactions[i]['decision_source'] = "AI"
                transactions[i]['confidence'] = 0.85
                
    except Exception as e:
        print(f"OpenAI Call Error: {e}")
