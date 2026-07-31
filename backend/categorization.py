"""
Categorization Service
Ported from services/categorizationRules.ts
"""
import re
import os
import math
from typing import List, Dict, Any, Optional
from claude_service import categorize_with_claude

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
# Exclude Transfers from being matched as Bank Charges
TRANSFER_EXCLUDE = r"\bTRANSFER BETWEEN CUSTOMERS\b|\bNIP\b|\bGTW(?:ORLD)?\b|\bGTWORLD\b|\bGAPSLITE\b|\bGAPS?\b|\bNIBSS\b|\bTRF\b"

RULES = [
    Rule("R001_OPENING_BALANCE", 1, r"OPENING\s+BAL|BAL\s*B\/F|BALANCE\s*BROUGHT|B\/F\b|BROUGHT\s*FORWARD", "Opening Balance", 1.0, "both"),
    
    # INFLOWS (High Priority)
    Rule("R004A_TRANSFER_VIA", 4, r"\bTRANSFER\s*BETWEEN\s*CUSTOMERS\b.*\bVIA\b", "Operating Income", 0.95, "credit"),
    Rule("R004B_GTWORLD", 4, r"\bGTW(?:ORLD)?\b|\bGTWORLD\b", "Operating Income", 0.92, "credit"),
    Rule("R004C_NIP_TRF_FROM", 4, r"\bNIP\b.*\bTRF(?:FOR|FRM|FROM)?\b|\bTRF\s*FRM\b|\bTRF\s*FROM\b|\bTRFFOR\b", "Operating Income", 0.93, "credit"),
    Rule("R004D_GAPS", 4, r"\bGAPSLITE\b|\bGAPS?\b", "Operating Income", 0.92, "credit"),

    Rule("R005_INWARD_TRANSFERS", 5, r"NIP\s*FROM|TRF\s*FROM|CREDIT\s*FROM|DEPOSIT\b|INFLOW\b", "Operating Income", 0.9, "credit"),
    
    # BANK CHARGES & LEVIES (High Priority)

    # DEBIT: transfers out / treasury / payments (Priority 9) - BEFORE Bank Charges
    Rule("R009A_TRANSFER_BETWEEN", 9, r"\bTRANSFER BETWEEN CUSTOMERS\b|\bNIBSS\b", "Inter-Account / Treasury Transfer", 0.90, "debit"),
    Rule("R009B_NIP_TRF_TO", 9, r"\bNIP\b.*\bTO\b|\bTRF\s*TO\b|\bTRFTO\b|\bNIP\s*TO\b", "Inter-Account / Treasury Transfer", 0.88, "debit"),
    Rule("R009C_GTWORLD_GAPS", 9, r"\bGTW(?:ORLD)?\b|\bGTWORLD\b|\bGAPSLITE\b|\bGAPS?\b|\bGAP\b", "Inter-Account / Treasury Transfer", 0.85, "debit"),

    Rule("R010_BANK_STAMP_DUTY", 10, r"\bSTAMP\s*DUTY\b", "Bank Charges", 1.0, "debit"),
    Rule("R011_BANK_CHARGES_CORE", 11, r"\bSMS\s*CHARGE\b|\bCOMMISSION\b|\bMAINTENANCE\b|\bACCOUNT\s*MAINTENANCE\b", "Bank Charges", 1.0, "debit", exclude=TRANSFER_EXCLUDE),
    Rule("R012_GOVT_LEVIES_TAXES", 12, r"\bVAT\b|\bVATCHARGES\b|\bTAX\b|\bLEVY\b", "Bank Charges", 1.0, "debit", exclude=TRANSFER_EXCLUDE),
    
    # --- FIX 9: BANK CHARGES CLASSIFICATION ---
    # Rule("R013_LEVY_50_AMOUNT", 13, r"LEVY", "Bank Charges", 1.0, "debit"), # Handled by R012 + Amount Check
    # Rule("R014_SPECIFIC_AMOUNT_CHARGES", 14, r".*", "Bank Charges", 0.8, "debit"), # Removed placeholder

    # INTEREST
    Rule("R020_WHT_ON_INTEREST_DEBIT", 20, r"CREDIT\s*INTEREST|INTEREST\b", "WHT Receivable", 1.0, "debit", exclude=r"OVERDRAFT\s*INTEREST|LOAN\s*INTEREST|INTEREST\s*CHARGE"),
    Rule("R021_INTEREST_INCOME_CREDIT", 21, r"CREDIT\s*INTEREST|INTEREST\b", "Interest Income", 1.0, "credit", exclude=r"OVERDRAFT\s*INTEREST|LOAN\s*INTEREST|INTEREST\s*CHARGE"),
    
    # --- FIX 13: INTEREST REVERSAL ---
    Rule("R022_INTEREST_REVERSAL_DEBIT", 22, r"CURRENT\s*ACT\s*CREDIT\s*INTEREST", "Interest Reversal / Adjustment", 1.0, "debit"),
    Rule("R023_INTEREST_INCOME_SPECIFIC", 23, r"CURRENT\s*ACT\s*CREDIT\s*INTEREST", "Interest Income", 1.0, "credit"),
    
    # STAFF (Priority 6 - Override Transfers/Charges)
    Rule("R006A_SALARY_PAYROLL", 6, r"SALARY\b|PAYROLL\b|WAGES\b|STAFF\s*SAL", "Salaries & Wages", 1.0, "debit"),
    Rule("R006B_STAFF_ADVANCE", 6, r"STAFF\s*LOAN|SALARY\s*ADVANCE|ADVANCE\s*TO\s*STAFF", "Staff Debtors / Salary Advances", 1.0, "debit"),
    Rule("R006C_STAFF_WELFARE", 6, r"WELFARE|LUNCH|CATERING|TEAM\s*BONDING|GROCERIES", "Staff Welfare", 0.9, "debit"),
    Rule("R006D_STAFF_TRAINING", 6, r"TRAINING|WORKSHOP|SEMINAR|COURSE\b|UDEMY|COURSERA", "Staff Training & Development", 0.9, "debit"),
    
    # EXPENSES (Priority 7 - Override Transfers/Charges)
    Rule("R007A_EVENT_CONFERENCE", 7, r"SUMMIT|CONFERENCE|HEALTHTECH|KIGALI|NAMETAG|NAME\s*TAGS", "Event & Conference Expenses", 1.0, "debit"),
    Rule("R007B_TRANSPORT_VEHICLE", 7, r"VEHICLE|TINT|VEHICLE\s*REG|CAR\s*REG|LICENSE|VEHICLE\s*PAPERS|FUEL\b|DIESEL\b|TRANSPORT\b", "Transport & Logistics", 1.0, "debit"),
    Rule("R007C_REPAIRS_MAINTENANCE", 7, r"REPAIR|MAINTENANCE\s*(?!FEE|CHG|CHARGE|ACCT|ACCOUNT)|SERVICING|PLUMBING|ELECTRICAL|CARPENTRY", "Repairs & Maintenance", 0.9, "debit"),
    
    # --- NEW: SECURITY & SAFETY ---
    # Priority 8 to override "Transfer" (Rule 9)
    Rule("R008_SECURITY_EXPENSES", 8, r"SECURITY\s*EXPENSE|SECURITY\b|POLICE|VIGILANTE|GUARD|ESCORT|SAFETY", "Security & Safety", 0.95, "debit"),
    
    Rule("R007D_FOREIGN_EXAM_FEES", 7, r"\bSAT\b|TOEFL\b|IELTS\b|GRE\b|GMAT\b", "Foreign Exam Fees", 1.0, "both"),
    Rule("R007E_EXAM_GENERIC_PASSTHROUGH", 7, r"\bEXAM\b|EXAM\s*FEE|REGISTRATION\s*(?:EXAM|FORM|FEE)|ADMISSION|APPLICATION\s*FORM|COMMON\s*ENTRANCE", "Student Exam Fees (Pass-Through)", 0.95, "both"),
    
    Rule("R007F_CAPITAL_PROJECT_VALUATION", 7, r"VALUATION\s*INVOICE|VARIATION\s*INVOICE", "Capital Expenditure (CWIP)", 1.0, "debit"),
    Rule("R080_OFFICE_RENT_CORPORATE_SERVICES", 80, r"CORPORATE\s*SERVICES|SERVICED\s*OFFICE|ADEOLA\s*ODEKU", "Office Rent / Lease", 0.92, "debit"),
    # Remove broad "VICTORIA ISLAND" from here, as it's common bank boilerplate
    
    Rule("R007H_ADMINISTRATIVE_EXPENSES", 7, r"MISCELLANEOUS|MISC\b|OFFICE\s*EXP|STATIONERY|PRINTING|COURIER|NEWSPAPER|SUBSCRIPTION|REGISTRATION\b|INTERNET|DATA\s*BUNDLE|AIRTIME", "Administrative Expenses", 0.95, "debit"),
    
    # CATCH-ALL OUTWARD TRANSFERS (Lowest Priority Rule)
    Rule("R090_GENERIC_OUTWARD_TRANSFER", 90, r"NIP\s*TO|TRF\s*TO|TRF\s*IFO|LOCAL\s*TRANSFERS", "Inter-Account / Treasury Transfer", 0.6, "debit"),
]

# --- 2. VENDOR KNOWLEDGE BASE ---
VENDOR_MAPPING = {
    "Utilities & Bills": [
        "IKEDC", "EKEDC", "PHCN", "KEDCO", "AEDC", "JEDC", "DSTV", "GOTV", "STARTIMES", "SMILE", "SPECTRANET", "OLUSESI WA"
    ],
    "Fuel & Energy": [
        "TOTALENERGIES", "TOTAL\s+SERVICE", "NNPC", "OANDO", "BOVAS", "NORTH\s+WEST", "ETERNAL", "ARDova", "MOBIL", "EVELAND", "DAMAC OIL"
    ],
    "Telecommunications": [
        "MTN", "AIRTEL", "GLO\b", "9MOBILE", "ETISALAT"
    ],
    "Staff Welfare & Catering": [
        "CHICKEN\s+REPUBLIC", "THE\s+PLACE", "KFC", "DOMINO", "COLDSTONE", "MEGA\s+CHICKEN", "SWEET\s+SENSATION", "MAMA\s+CASS", "FOOD\s+COURT", "SHERBET FARMS", "GLOBAL LOKO"
    ],
    "Transport & Logistics": [
        "UBER", "BOLT", "GIGL", "GIG\s+LOGISTICS", "DHL", "FEDEX", "UPS", "RED\s+STAR", "KAVUANI"
    ],
    "Professional Fees": [
        "LAWYER", "AUDITOR", "CONSULTANT", "RETAINER", "LEGAL", "COVENANT\s+PARTNER"
    ],
    "Administrative Expenses": [
        "JUMIA", "KONGA", "AMAZON", "STATIONERY", "OFFICE\s+DEPOT", "PAPER\s+PLUS", "SWIFT NETW"
    ],
    "Event & Conference Expenses": [
        "CJ MULTI TRADE", "HEALTHTECH", "KIGALI", "SUMMIT"
    ],
    "Technical & Operations": [
        "PROMOTEC", "SUNBETH GLOBAL"
    ],
    "General Vendor": [
         "GREAT OMA"
    ],
    "Salaries & Wages": [
        "OKPANACHI IVIE EMILY"
    ]
}

# Convert Vendor Mapping to actual Rules for the Engine
for category, keywords in VENDOR_MAPPING.items():
    for i, keyword in enumerate(keywords):
        RULES.append(Rule(
            id=f"VEND_{category.replace(' ', '_').upper()}_{i}",
            priority=15, # Higher than generic transfers (90) but lower than specific charges
            pattern=rf"\b{keyword}\b",
            category=category,
            confidence=0.95,
            side='debit'
        ))

# Sort rules by priority (ascending)
SORTED_RULES = sorted(RULES, key=lambda r: r.priority)

def extract_entity_from_narration(norm_desc: str) -> str:
    """
    Attempt to isolate the 'Subject' of the transaction (e.g. Vendor name).
    Works across Access, Ecobank, Wema, and GTBank patterns.
    """
    entity = norm_desc

    # 1. Clean common NIP/TRF/GAPS prefixes
    prefixes = [
        r"NIP TRANSFER", r"COB TRF TO", r"COB TRF", r"TRF FROM", r"NIP FROM",
        r"PP ", r"REV PP", r"ONB TRANSFER FROM", r"POS PURCHASE", r"OMNI BO",
        r"TRN IFO NIP OUTWARD ACCOUNT", r"LOCAL TRANSFERS OTHER BANKS",
        r"GAPS\d*", r"TRSF IFO", r"FT IFO", r"BO\s+[\w\s]+\s+IFO"
    ]
    for p in prefixes:
        entity = re.sub(r"^" + p, "", entity, flags=re.IGNORECASE).strip()
    
    # 2. Split by common delimiters (Order matters: comma/slash usually last)
    # Wema/Standard: " TO ", " FROM ", " IFO ", ":"
    # Ecobank: ","
    # Access: "/"
    for delim in [" TO ", " FROM ", " IFO ", ":", ",", "/"]:
        if entity and delim in str(entity):
            parts = str(entity).split(delim)
            # For Ecobank ([ID] : [NAR] , [ENTITY]), we often want the last part
            # For Access ([PURPOSE]/[BANK]/[ENTITY]), we often want the last part
            # Let's iterate from the end to find the most likely name
            for part in reversed(parts):
                p = part.strip()
                # Skip numeric IDs, short codes, or boilerplate
                if len(p) > 3 and not re.match(r"^\d+$", p):
                    if not any(p.startswith(x) for x in ["PP_", "GAPS", "REV_"]):
                        # Skip generic purpose words
                        if p.upper() not in ["OPERATIONS", "SALARY", "MAY SALARY", "JUNE SALARY"]:
                            entity = p
                            break
    
    # 3. Strip trailing junk (IDs, branch codes like 2505...)
    entity = re.sub(r"\b\d{5,}\b", "", entity).strip()
    
    return entity

def normalize_description(desc: str) -> str:
    if not desc:
        return ""
    desc = str(desc).upper()
    
    # --- BOILERPLATE SCRUBBING ---
    boilerplate = [
        "PLEASE ADDRESS ALL ENQUIRIES",
        "P.O.BOX",
        "VICTORIA IS",  # Catches Victoria Is and Victoria Island
        "IKOYI",
        "LAGOS",
        "RC NO",
        "RC ",          # Catches RC 12345
        "REGISTERED OFFICE",
        "MEMBER OF THE NIGERIA DEPOSIT INSURANCE CORPORATION",
        "NDIC",
        "WWW.",
        "PLOT 635, AKIN ADESOLA",
    ]
    for b in boilerplate:
        desc = desc.replace(b, " ")
    
    # 1. Remove phone numbers (Nigerian format)
    desc = re.sub(r'\b0[7-9][0-1]\d{8}\b', ' ', desc)
    
    # 2. Remove long numeric strings (likely IDs)
    desc = re.sub(r'\b\d{10,}\b', ' ', desc)
    
    # 3. Final cleanup: alphanumeric, spaces, and slash/comma (used in bank structures)
    desc = re.sub(r'[^A-Z0-9\s/,]', ' ', desc)
    desc = re.sub(r'\s+', ' ', desc)
    return desc.strip()

def parse_money_amount(value: Any) -> float:
    """Parse bank amount values that may contain commas, symbols, or blanks."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else 0.0

    text = str(value).strip()
    if not text:
        return 0.0

    is_parenthesized_negative = text.startswith("(") and text.endswith(")")
    cleaned = text.replace(",", "")
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)
    if not cleaned or cleaned in {"-", ".", "-."}:
        return 0.0

    try:
        parsed = float(cleaned)
    except (TypeError, ValueError):
        return 0.0

    if not math.isfinite(parsed):
        return 0.0
    return -abs(parsed) if is_parenthesized_negative else parsed

print("--- CATEGORIZATION MODULE LOADED ---")

def categorize_single_transaction(txn: Dict) -> Dict:
    """
    Apply rules to a single transaction in place.
    """
    # Use 'remarks' (full combined text: reference + branch + narration) for rule matching.
    # Fall back to 'description' if remarks is empty (non-GTBank paths).
    raw_desc = txn.get('remarks', '') or txn.get('description', '')
    norm_desc = normalize_description(raw_desc)
    
    # Parse amounts safely. Some OCR/bank parsers return formatted strings
    # such as "3,590.00"; normalize them here before downstream logic sees them.
    debit = parse_money_amount(txn.get('debit'))
    credit = parse_money_amount(txn.get('credit'))
    txn['debit'] = debit
    txn['credit'] = credit
    is_debit = debit != 0
    is_credit = credit != 0
    
    updated_cat = None
    confidence = 0.0
    rule_id = None
    decision_source = None

    decision_source = None
    
    # 0. CHECK REVERSALS
    if re.search(r"REVERSAL|REV\b|RET\b|ERR\b", norm_desc) or re.search(r"REV\s*TRF", norm_desc):
        txn['is_reversal'] = True
    else:
        txn['is_reversal'] = False
        
    # --- ENTITY EXTRACTION ---
    # Attempt to isolate the "Who" (Vendor/Counterparty)
    entity = extract_entity_from_narration(norm_desc)
    txn['entity'] = entity
    
    # Store cleaned description for reference/UI if needed, but we use norm_desc for rules
    txn['clean_description'] = norm_desc

    # 1. AMOUNT-BASED CLASSIFICATION (Standard Fees & Specific Rules)
    if is_debit:
        # --- FIX 9: SPECIFIC AMOUNT RULES ---
        abs_amt = abs(debit)
        
        # Rule: Amount == 50 AND ("STAMP" or "LEVY") -> Bank Charges
        if math.isclose(abs_amt, 50.00, abs_tol=0.01) and any(x in norm_desc for x in ["STAMP", "LEVY"]):
             updated_cat = "Bank Charges"
             confidence = 1.0
             rule_id = "R010_BANK_STAMP_DUTY"
             decision_source = "RULE_SPECIFIC"

        # Rule: Amount == 3.75 or 53.75 (NIP fee) or 26.88 (SMS) -> Bank Charges
        elif any(math.isclose(abs_amt, amt, abs_tol=0.01) for amt in [3.75, 53.75, 26.88]):
             updated_cat = "Bank Charges"
             confidence = 1.0
             rule_id = "R014_SPECIFIC_AMOUNT_CHARGES"
             decision_source = "RULE_SPECIFIC"

        # Corrected Standard Fee Checks (fallback with guard)
        elif any(math.isclose(abs_amt, amt, abs_tol=0.01) for amt in [50.00, 52.50, 10.00, 4.00]):
            looks_like_charge = re.search(r"CHG|FEE|VAT|SMS|COMM|MAINT|LEVY|DUTY", norm_desc)
            looks_like_transfer = re.search(r"TRF|NIP|PAYMENT|PYMT|WEB|POS|ATM|DATA|AIRTIME", norm_desc)
            
            if looks_like_charge or (not looks_like_transfer and not re.search(r"OPENING\s*BAL", norm_desc)):
                updated_cat = "Bank Charges"
                confidence = 0.99
                rule_id = "AMT_STD_FEE"
                decision_source = "RULE"

    # 2. RULE ENGINE EXECUTION
    if not updated_cat:
        for rule in SORTED_RULES:
            if rule.side == 'debit' and not is_debit: continue
            if rule.side == 'credit' and not is_credit: continue
            
            # Use pattern match on the full normalized description
            if rule.pattern.search(norm_desc or ""):
                if rule.exclude and rule.exclude.search(norm_desc or ""):
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
            decision_source = "AI_HEURISTIC"
            
        else:
            updated_cat = "Uncategorized Expense" if is_debit else "Uncategorized Income"
            confidence = 0.0
            decision_source = "AI"

    txn['category'] = updated_cat
    txn['confidence'] = confidence
    if rule_id:
        txn['ruleId'] = rule_id
    if decision_source:
        txn['decision_source'] = decision_source
    
    # DEBUG LOG for specific cases
    if "SECURITY" in norm_desc or "HEALTH" in norm_desc:
        print(f"DEBUG: Entity='{entity}' | Cat='{updated_cat}' | Source='{decision_source}' | Desc='{norm_desc}'")

    return txn



from openai import OpenAI
from gemini_client import generate_gemini_text
import httpx

class AIState:
    openai_key_index = 0

def get_openai_client():
    """Parse comma-separated keys and return a rotated client instance"""
    raw_keys = os.getenv('OPENAI_API_KEY', '')
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not keys:
        return None
    
    api_key = keys[AIState.openai_key_index % len(keys)]
    AIState.openai_key_index += 1
    return OpenAI(api_key=api_key, http_client=httpx.Client())

# ... (keep existing imports and rules)

def categorize_transactions(transactions: List[Dict]) -> List[Dict]:
    """
    Categorize transactions using rules + AI fallback
    """
    unallocated_indices = []
    
    for i, txn in enumerate(transactions):
        categorize_single_transaction(txn)
        cat = txn.get('category')
        conf = txn.get('confidence', 0.0)
        source = txn.get('decision_source')
        
        is_unallocated = cat in ['Unallocated', 'Uncategorized Expense', 'Uncategorized Income']
        is_low_conf_transfer = (cat == 'Inter-Account / Treasury Transfer' and source == 'AI_HEURISTIC' and conf <= 0.6)
        
        if is_unallocated or is_low_conf_transfer:
            unallocated_indices.append(i)
            
    # AI fallback for unallocated (batch processing)
    if unallocated_indices:
        try:
            unallocated = [transactions[i] for i in unallocated_indices]
            if unallocated:
                # Get all categories from VENDOR_MAPPING + Standard ones
                available_categories = list(VENDOR_MAPPING.keys()) + [
                    "Operating Income", "Inter-Account / Treasury Transfer", "Bank Charges", 
                    "Salaries & Wages", "Staff Welfare", "Security & Safety", 
                    "Repairs & Maintenance", "Office Rent / Lease", "WHT Receivable", "Interest Income"
                ]
                available_categories = sorted(list(set(available_categories)))

                if os.getenv('ANTHROPIC_API_KEY'):
                    categorize_with_claude(unallocated, available_categories)
                elif os.getenv('OPENAI_API_KEY'):
                    categorize_with_openai(unallocated)
                elif os.getenv('GEMINI_API_KEY'):
                    categorize_with_gemini(unallocated)
        except Exception as e:
            print(f"AI categorization failed: {e}")
            
    return transactions

def _clean_ai_json(text: str) -> str:
    """Helper to clean common AI JSON formatting issues"""
    if not text: return "[]"
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()

def categorize_with_openai(transactions: List[Dict]):
    """
    Use OpenAI (GPT-4o) to categorize unallocated transactions
    """
    client = get_openai_client()
    if not client: return
    
    # Get all categories from VENDOR_MAPPING + Standard ones
    available_categories = list(VENDOR_MAPPING.keys()) + [
        "Operating Income", "Inter-Account / Treasury Transfer", "Bank Charges", 
        "Salaries & Wages", "Staff Welfare", "Security & Safety", 
        "Repairs & Maintenance", "Office Rent / Lease", "WHT Receivable", "Interest Income"
    ]
    # Remove duplicates
    available_categories = sorted(list(set(available_categories)))
    
    input_data = []
    for t in transactions:
        desc = t.get('remarks', '') or t.get('description', '')
        entity = t.get('entity', 'Unknown')
        amt = t.get('debit', 0) or t.get('credit', 0)
        input_data.append(f"Entity: {entity} | Narration: {desc} | Amount: {amt}")
    
    categories_str = "\n".join([f"- {c}" for c in available_categories])
    
    prompt = f"""You are an expert accountant specializing in Nigerian bank statement analysis.
Categorize these transactions into the EXACT categories provided below.

CATEGORIES:
{categories_str}

TRANSACTIONS:
{chr(10).join(f'{i+1}. {data}' for i, data in enumerate(input_data))}

INSTRUCTIONS:
1. Return ONLY a JSON array of category names in the exact same order as the input.
2. Example output: ["Salaries & Wages", "Bank Charges", "Utilities & Bills"]
3. If an entity like 'IKEDC' or 'EKEDC' is present, categorize as 'Utilities & Bills'.
4. If it looks like a personal transfer to a person (e.g. 'OLAPEJU'), use 'Inter-Account / Treasury Transfer'.
5. If it relates to 'SUMMIT', 'KIGALI', or 'HEALTHTECH', use 'Event & Conference Expenses'.
6. If it's a small amount (50, 53.75, 26.88) with words like 'LEVY', 'DUTY', 'CHARGE', use 'Bank Charges'.
"""
    
    try:
        # Use gpt-4o for high intelligence
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        content = _clean_ai_json(response.choices[0].message.content)
        import json
        categories = json.loads(content)
        
        for i, category in enumerate(categories):
            if i < len(transactions):
                # Ensure the category is valid
                if category in available_categories:
                    transactions[i]['category'] = category
                else:
                    # Fuzzy match or fallback
                    transactions[i]['category'] = "Uncategorized Expense"
                
                transactions[i]['decision_source'] = "AI_GPT4"
                transactions[i]['confidence'] = 0.9
                
    except Exception as e:
        print(f"OpenAI GPT-4 Categorization Error: {e}")

def categorize_with_gemini(transactions: List[Dict]):
    """
    Use secondary Gemini fallback for categorization
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: return
    
    available_categories = list(VENDOR_MAPPING.keys()) + [
        "Operating Income", "Inter-Account / Treasury Transfer", "Bank Charges", 
        "Salaries & Wages", "Staff Welfare", "Security & Safety", 
        "Repairs & Maintenance", "Office Rent / Lease"
    ]
    available_categories = sorted(list(set(available_categories)))
    
    input_data = [
        f"Entity: {t.get('entity', 'Unknown')} | Narration: {t.get('remarks', '') or t.get('description', '')}" 
        for t in transactions
    ]
    
    prompt = f"""Categorize these bank transactions:
CATEGORIES: {", ".join(available_categories)}

TRANSACTIONS:
{chr(10).join(f'{i+1}. {data}' for i, data in enumerate(input_data))}

Return ONLY a JSON array of categories.
"""
    
    try:
        response_text = generate_gemini_text(api_key, "gemini-1.5-flash", prompt)
        
        import json
        content = _clean_ai_json(response_text)
        categories = json.loads(content)
        
        for i, category in enumerate(categories):
            if i < len(transactions):
                transactions[i]['category'] = category
                transactions[i]['decision_source'] = "AI_GEMINI"
                transactions[i]['confidence'] = 0.8
                
    except Exception as e:
        print(f"Gemini Categorization Fallback Error: {e}")
