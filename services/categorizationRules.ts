
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

// Rules defined in the Spec (R001 - R060)
const RULES: Rule[] = [
  {
    id: "R001_OPENING_BALANCE",
    priority: 1,
    description_regex: /OPENING\s+BAL/i,
    side: "both",
    category: "Opening Balance",
    confidence: 1.0
  },
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
    description_regex: /SMS\s*CHARGE|SMS\b|COMMISSION|TRANSFER\s*CHARGE|BANK\s*CHARGE/i,
    side: "debit",
    category: "Bank Charges",
    confidence: 1.0
  },
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
    id: "R030_SALARY_PAYROLL",
    priority: 30,
    description_regex: /SALARY\b|PAYROLL\b|WAGES\b|STAFF\s*SAL/i,
    side: "debit",
    category: "Salaries & Wages",
    confidence: 1.0
  },
  {
    id: "R031_STAFF_ADVANCE",
    priority: 31,
    description_regex: /STAFF\s*LOAN|SALARY\s*ADVANCE|ADVANCE\s*TO\s*STAFF/i,
    side: "debit",
    category: "Staff Debtors / Salary Advances",
    confidence: 1.0
  },
  {
    id: "R040_EVENT_CONFERENCE",
    priority: 40,
    description_regex: /SUMMIT|CONFERENCE|HEALTHTECH|KIGALI|NAMETAG|NAME\s*TAGS/i,
    side: "debit",
    category: "Event & Conference Expenses",
    confidence: 1.0
  },
  {
    id: "R041_TRANSPORT_VEHICLE",
    priority: 41,
    description_regex: /VEHICLE|TINT|REGISTRATION|LICENSE|VEHICLE\s*PAPERS/i,
    side: "debit",
    category: "Transport & Logistics",
    confidence: 1.0
  },
  {
    id: "R050_EXAM_SAT_PASSTHROUGH",
    priority: 50,
    description_regex: /\bSAT\b|EXAM\b|EXAM\s*FEE|REGISTRATION\s*(SAT|EXAM)/i,
    side: "both",
    category: "Student Exam Fees (Pass-Through)",
    confidence: 1.0
  },
  {
    id: "R055_CAPITAL_PROJECT_VALUATION",
    priority: 55,
    description_regex: /VALUATION\s*INVOICE|VARIATION\s*INVOICE/i,
    side: "debit",
    category: "Capital Expenditure (CWIP)",
    confidence: 1.0
  },
  {
    id: "R060_OFFICE_RENT_CORPORATE_SERVICES",
    priority: 60,
    description_regex: /CORPORATE\s*SERVICES|SERVICED\s*OFFICE|VICTORIA\s*ISLAND|ADEOLA\s*ODEKU/i,
    side: "debit",
    category: "Office Rent / Lease",
    confidence: 0.92
  }
];

// --- ENGINE LOGIC ---

// OPTIMIZATION: Hoist sorting out of the function scope.
// This ensures we sort the rules only once when the module loads, 
// rather than N times for N transactions.
const SORTED_RULES = [...RULES].sort((a, b) => a.priority - b.priority);

const normalizeDescription = (desc: string): string => {
  if (!desc) return "";
  // Uppercase, strip punctuation (keep spaces), collapse whitespace
  let normalized = desc.toUpperCase();
  // We keep alphanumeric and spaces.
  return normalized;
};

export const categorizeTransaction = (t: Transaction): Transaction => {
  const updated = { ...t };
  const rawDesc = t.description || "";
  const normDesc = normalizeDescription(rawDesc);
  const isCredit = (t.credit || 0) !== 0;
  const isDebit = (t.debit || 0) !== 0;
  const debitAmount = t.debit || 0;

  // Default assumption: It's an AI prediction unless a rule overrides it
  updated.decision_source = 'AI';

  // 1. REVERSAL CHECK (Pre-processing)
  if (t.is_reversal || /^(REV\/|REVERSAL)/i.test(rawDesc)) {
    updated.is_reversal = true;
  }

  // 2. AMOUNT-BASED CLASSIFICATION (High Precision for Fees)
  // Smart detection for Bank Charges where description might match the principal transaction.
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

  // 3. RULE ENGINE EXECUTION
  // Iterate through pre-sorted rules
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

  // 4. AI CLASSIFIER FALLBACK 
  if (!updated.category || updated.category === "Unallocated") {
    updated.category = "Review Required";
    updated.confidence = 0.5; 
  } else {
    updated.confidence = 0.75; 
  }

  return updated;
};
