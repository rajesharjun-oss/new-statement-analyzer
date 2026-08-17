import { Transaction } from '../types';

// --- CONFIGURATION: Accounting Grade Classifier Spec ---

interface Rule {
  id: string;
  priority: number; // Lower number = Higher priority
  description_regex: RegExp;
  exclude_regex?: RegExp;
  side: 'debit' | 'credit' | 'both';
  category: string;
  confidence: number;
}

// Rules defined in the Spec (R001 - R090)
const RULES: Rule[] = [
  {
    id: "R001_OPENING_BALANCE",
    priority: 1,
    // Expanded to catch B/F, BROUGHT FORWARD to handle page breaks
    description_regex: /OPENING\s+BAL|BAL\s*B\/F|BALANCE\s*BROUGHT|B\/F\b|BROUGHT\s*FORWARD/i,
    side: "both",
    category: "Opening Balance",
    confidence: 1.0
  },
  // INFLOWS (High Priority)
  {
    id: "R004_INWARD_TRANSFERS_OVERRIDE",
    priority: 4,
    description_regex: /\bTRANSFER\s*BETWEEN\s*CUSTOMERS\b.*\bVIA\b|\bGTW(?:ORLD)?\b|\bGAPSLITE\b|\bGAPS?\b/i,
    side: "credit",
    category: "Operating Income",
    confidence: 0.95
  },
  {
    id: "R003_PENSION_INCOME",
    priority: 3,
    description_regex: /\bPENSION\b|\bPENCOM\b|\bPTAD\b|\bPFA\b|RETIREMENT\s+BENEFIT|RETIREMENT\s+SAVINGS|ANNUITY/i,
    side: "credit",
    category: "Pension Income",
    confidence: 1.0
  },
  {
    id: "R005_INWARD_TRANSFERS",
    priority: 5,
    description_regex: /NIP\s*FROM|TRF\s*FROM|CREDIT\s*FROM|DEPOSIT\b|INFLOW\b/i,
    side: "credit",
    category: "Operating Income",
    confidence: 0.9
  },
  // STAFF (High Priority)
  {
    id: "R006_SALARY_PAYROLL",
    priority: 6,
    description_regex: /SALARY\b|PAYROLL\b|WAGES\b|STAFF\s*SAL/i,
    side: "debit",
    category: "Salaries & Wages",
    confidence: 1.0
  },
  // EXPENSES (High Priority)
  {
    id: "R007_EXPENSE_OVERRIDE",
    priority: 7,
    description_regex: /SUMMIT|CONFERENCE|HEALTHTECH|KIGALI|NAMETAG|VALUATION\s*INVOICE|VARIATION\s*INVOICE|CORPORATE\s*SERVICES/i,
    side: "debit",
    category: "Event & Conference Expenses", // Simplified: categorization.py uses separate ones but priority is the same
    confidence: 1.0
  },
  // SECURITY (Priority 8 - Must override Rule 9 Transfers)
  {
    id: "R008_SECURITY_EXPENSES",
    priority: 8,
    description_regex: /SECURITY\s*EXPENSE|SECURITY\b|POLICE|VIGILANTE|GUARD|ESCORT|SAFETY/i,
    side: "debit",
    category: "Security & Safety",
    confidence: 0.95
  },
  // TRANSFERS OUT (Priority 9)
  {
    id: "R009_OUTWARD_TRANSFERS_OVERRIDE",
    priority: 9,
    description_regex: /\bTRANSFER BETWEEN CUSTOMERS\b|\bNIBSS\b|\bTRF\s*TO\b|\bNIP\s*TO\b/i,
    side: "debit",
    category: "Inter-Account / Treasury Transfer",
    confidence: 0.90
  },
  // BANK CHARGES & LEVIES (Priority 10+)
  {
    id: "R010_BANK_STAMP_DUTY",
    priority: 10,
    description_regex: /STAMP\s*DUTY|FGN\s*STAMPDUTY/i,
    side: "debit",
    category: "Bank Charges",
    confidence: 1.0
  },
  {
    id: "R011_BANK_CHARGES_CORE",
    priority: 11,
    // Explicitly catching NIP/TRF charges to prevent them falling to Transfer logic
    // Updated to include Account Maintenance variations
    description_regex: /SMS\s*CHARGE|SMS\b|COMMISSION|COMM\b|TRANSFER\s*CHARGE|BANK\s*CHARGE|MAINTENANCE\s*(?:FEE|CHG|CHARGE)|ACCT\s*MAINT|ACCOUNT\s*MAINT|AMF\b|NIP\s*CHG|NIP\s*FEE|TRF\s*CHG|TRF\s*FEE|UBR\s*CHG/i,
    side: "debit",
    category: "Bank Charges",
    confidence: 1.0
  },
  {
    id: "R012_GOVT_LEVIES_TAXES",
    priority: 12,
    // Explicitly catching VAT on transfers
    description_regex: /ELECTRONIC\s*MONEY\s*TRANSFER\s*LEVY|EMTL|VAT\b|TAX\b|FGN\s*LEVY|VAT\s*ON\s*CHG|VAT\s*ON\s*TRF|VAT\s*ON\s*NIP/i,
    side: "debit",
    category: "Bank Charges",
    confidence: 1.0
  },
  // INTEREST
  {
    id: "R020_WHT_ON_INTEREST_DEBIT",
    priority: 20,
    description_regex: /CREDIT\s*INTEREST|INTEREST\b/i,
    exclude_regex: /OVERDRAFT\s*INTEREST|LOAN\s*INTEREST|INTEREST\s*CHARGE/i,
    side: "debit",
    category: "WHT Receivable",
    confidence: 1.0
  },
  {
    id: "R021_INTEREST_INCOME_CREDIT",
    priority: 21,
    description_regex: /CREDIT\s*INTEREST|INTEREST\b/i,
    exclude_regex: /OVERDRAFT\s*INTEREST|LOAN\s*INTEREST|INTEREST\s*CHARGE/i,
    side: "credit",
    category: "Interest Income",
    confidence: 1.0
  },
  {
    id: "R022_INTEREST_REVERSAL",
    priority: 22,
    description_regex: /CURRENT\s*ACT\s*CREDIT\s*INTEREST/i,
    side: "debit",
    category: "Interest Reversal / Adjustment",
    confidence: 1.0
  },
  // STAFF
  {
    id: "R031_STAFF_ADVANCE",
    priority: 31,
    description_regex: /STAFF\s*LOAN|SALARY\s*ADVANCE|ADVANCE\s*TO\s*STAFF/i,
    side: "debit",
    category: "Staff Debtors / Salary Advances",
    confidence: 1.0
  },
  {
    id: "R032_STAFF_WELFARE",
    priority: 32,
    description_regex: /WELFARE|LUNCH|CATERING|TEAM\s*BONDING|GROCERIES/i,
    side: "debit",
    category: "Staff Welfare",
    confidence: 0.9
  },
  {
    id: "R033_STAFF_TRAINING",
    priority: 33,
    description_regex: /TRAINING|WORKSHOP|SEMINAR|COURSE\b|UDEMY|COURSERA/i,
    side: "debit",
    category: "Staff Training & Development",
    confidence: 0.9
  },
  // EXPENSES
  {
    id: "R041_TRANSPORT_VEHICLE",
    priority: 41,
    // REMOVED generic "REGISTRATION" to avoid conflict with Exam/Admin registration
    // Added specific vehicle context for registration
    description_regex: /VEHICLE|TINT|VEHICLE\s*REG|CAR\s*REG|LICENSE|VEHICLE\s*PAPERS|FUEL\b|DIESEL\b/i,
    side: "debit",
    category: "Transport & Logistics",
    confidence: 1.0
  },
  {
    id: "R042_REPAIRS_MAINTENANCE",
    priority: 42,
    // Excluded Fee/Charge/Account contexts to avoid Bank Charge collisions
    description_regex: /REPAIR|MAINTENANCE\s*(?!FEE|CHG|CHARGE|ACCT|ACCOUNT)|SERVICING|PLUMBING|ELECTRICAL|CARPENTRY/i,
    side: "debit",
    category: "Repairs & Maintenance",
    confidence: 0.9
  },
  {
    id: "R049_FOREIGN_EXAM_FEES",
    priority: 49,
    description_regex: /\bSAT\b|TOEFL\b|IELTS\b|GRE\b|GMAT\b/i,
    side: "both",
    category: "Foreign Exam Fees",
    confidence: 1.0
  },
  {
    id: "R050_EXAM_GENERIC_PASSTHROUGH",
    priority: 50,
    // ADDED "REGISTRATION FORM", "ADMISSION", "APPLICATION"
    description_regex: /\bEXAM\b|EXAM\s*FEE|REGISTRATION\s*(?:EXAM|FORM|FEE)|ADMISSION|APPLICATION\s*FORM|COMMON\s*ENTRANCE/i,
    side: "both",
    category: "Student Exam Fees (Pass-Through)",
    confidence: 0.95
  },
  {
    id: "R060_OFFICE_RENT_CORPORATE_SERVICES",
    priority: 60,
    description_regex: /CORPORATE\s*SERVICES|SERVICED\s*OFFICE|VICTORIA\s*ISLAND|ADEOLA\s*ODEKU/i,
    side: "debit",
    category: "Office Rent / Lease",
    confidence: 0.92
  },
  {
    id: "R070_ADMINISTRATIVE_EXPENSES",
    priority: 70,
    // ADDED generic "REGISTRATION" here as fallback (e.g. CAC, Business name)
    description_regex: /MISCELLANEOUS|MISC\b|OFFICE\s*EXP|STATIONERY|PRINTING|COURIER|NEWSPAPER|SUBSCRIPTION|REGISTRATION\b|INTERNET|DATA\s*BUNDLE|AIRTIME/i,
    side: "debit",
    category: "Administrative Expenses",
    confidence: 0.95
  },
  {
    id: "R090_GENERIC_OUTWARD_TRANSFER",
    priority: 90,
    description_regex: /NIP\s*TO|TRF\s*TO|TRF\s*IFO|LOCAL\s*TRANSFERS/i,
    side: "debit",
    category: "Inter-Account / Treasury Transfer",
    confidence: 0.6
  }
];

// --- ENGINE LOGIC ---

// OPTIMIZATION: Hoist sorting out of the function scope.
const SORTED_RULES = [...RULES].sort((a, b) => a.priority - b.priority);

const normalizeDescription = (desc: string): string => {
  if (!desc) return "";
  // Normalization: Upper case, remove special chars except spaces, collapse multiple spaces
  return desc.toUpperCase().replace(/[^A-Z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
};

export const categorizeTransaction = (t: Transaction): Transaction => {
  const updated = { ...t };
  const rawDesc = t.description || "";
  const normDesc = normalizeDescription(rawDesc);
  const isCredit = (t.credit || 0) !== 0;
  const isDebit = (t.debit || 0) !== 0;
  const debitAmount = t.debit || 0;

  // 0. CHECK REVERSALS (New Flagging Logic)
  if (/REVERSAL|REV\b|RET\b|ERR\b/i.test(normDesc) || /REV\s*TRF/i.test(normDesc)) {
    updated.is_reversal = true;
  }

  // 1. AMOUNT-BASED CLASSIFICATION
  const isFeeAmount =
    (Math.abs(debitAmount - 50.00) < 0.001) ||
    (Math.abs(debitAmount - 3.75) < 0.001) ||
    (Math.abs(debitAmount - 52.50) < 0.001) ||
    (Math.abs(debitAmount - 10.00) < 0.001) ||
    (Math.abs(debitAmount - 4.00) < 0.001);

  if (isDebit && isFeeAmount) {
    if (!/OPENING\s*BAL/i.test(normDesc)) {
      updated.category = "Bank Charges";
      updated.confidence = 0.99;
      updated.ruleId = "AMT_STD_FEE";
      updated.decision_source = 'RULE';
      return updated;
    }
  }

  // 2. RULE ENGINE EXECUTION (Highest Priority)
  // We still run strict rules because AI can miss accounting nuances (e.g., VAT vs WHT)
  for (const rule of SORTED_RULES) {
    if (rule.side === 'debit' && !isDebit) continue;
    if (rule.side === 'credit' && !isCredit) continue;

    if (rule.description_regex.test(normDesc)) {
      if (rule.exclude_regex && rule.exclude_regex.test(normDesc)) {
        continue;
      }
      updated.category = rule.category;
      updated.confidence = rule.confidence;
      updated.ruleId = rule.id;
      updated.decision_source = 'RULE';
      return updated;
    }
  }

  // 3. AI PREDICTION CHECK
  // If the AI (from Gemini) already provided a plausible category, we accept it.
  // We check if t.category is valid and not "Unallocated"
  if (t.category && t.category !== "Unallocated") {
    updated.category = t.category;
    updated.confidence = 0.85; // AI confidence
    updated.decision_source = 'AI';
    return updated;
  }

  // 4. HEURISTICS & FALLBACKS (Last Resort)
  if (!updated.category || updated.category === "Unallocated") {

    // A. Catch-all for Bank Charges (Keywords that might have been missed)
    // Added LEVY, DUTY to ensure EMTL/Stamp Duty fallbacks are caught
    // EXCLUSION: Ensure FEES for Exams, Schools, Tuition, Legal, Consultancy are NOT captured here.
    const bankChargeKeywords = /(?:CHG|COMM|FEE|VAT|TAX|MOBL|SMS|MAINT|LEVY|DUTY)/;
    const nonBankContexts = /(?:SCHOOL|TUITION|EXAM|CLASS|LESSON|TRAINING|COURSE|SEMINAR|LEGAL|LAWYER|CONSULT|AUDIT|PROFESSIONAL|RETAINER|MEMBER|LICENSE|SUBSCRIPTION)/;

    if (isDebit && bankChargeKeywords.test(normDesc) && !nonBankContexts.test(normDesc)) {
      updated.category = "Bank Charges";
      updated.confidence = 0.8;
      updated.decision_source = 'RULE';
    }
    // B. Catch-all for Outflows (Explicit Transfer Keywords Only)
    else if (isDebit && /(?:TRF|NIP|FRM|TO|MNY|TRANSFER|PYMT|PAYMENT|WEB|POS|ATM)/.test(normDesc)) {
      updated.category = "Inter-Account / Treasury Transfer";
      updated.confidence = 0.6;
      updated.decision_source = 'AI';
    }
    // C. Everything else without a clear trigger remains Unallocated
    else {
      updated.category = "Unallocated";
      updated.confidence = 0.0;
      updated.decision_source = 'AI';
    }
  }

  return updated;
};
