
import { Transaction } from '../types';

// Regex Helpers
const r = (pattern: string) => new RegExp(pattern, 'i');

type Direction = 'debit' | 'credit' | 'both';

// --- CATEGORY RULES CONFIGURATION ---
// Structure: [Category Name, Regex Patterns, Direction (optional, default 'both')]
// Order matters: First match wins.
const CATEGORY_RULES: [string, RegExp[], Direction?][] = [
  // -------------------------------------------------------------------------
  // 1. INFLOWS (Credit Only) - Preserving "Smart" Inflow Logic
  // -------------------------------------------------------------------------
  ["Owner's Capital", [r("\\bcapital\\b"), r("\\bequity\\b"), r("\\bshareholder\\b"), r("\\bdirector\\b.*\\bdeposit\\b"), r("\\binjection\\b"), r("\\bfunding\\b")], 'credit'],
  ["Student Exam Fees (Pass-Through)", [r("\\bexam\\b"), r("\\bwaec\\b"), r("\\bneco\\b"), r("\\bjamb\\b"), r("\\bcambridge\\b"), r("\\bielts\\b"), r("\\btoefl\\b")], 'credit'],
  ["Inter-Account Transfer", [r("\\bself\\b"), r("\\bown account\\b"), r("\\binternal transfer\\b"), r("\\bto my\\b")], 'both'], 
  ["Interest Income", [r("\\bcredit interest\\b"), r("\\binterest paid\\b"), r("\\binterest income\\b"), r("\\bcapitali[sz]ation\\b")], 'credit'],
  ["Refund / Reversal", [r("\\brefund\\b"), r("\\breversal\\b"), r("^rev/"), r("^rvsl")], 'credit'],
  ["Operating Income", [r("\\binvoice\\b"), r("\\bconsulting\\b"), r("\\bsales\\b"), r("\\bproceeds\\b"), r("\\bretainer\\b"), r("\\bproject\\b"), r("\\bcontract\\b"), r("\\bsupply\\b"), r("\\bclient\\b"), r("\\bpayment for\\b")], 'credit'],
  
  // -------------------------------------------------------------------------
  // 2. EXPENSES (Decision Tree Implementation)
  // -------------------------------------------------------------------------

  // [Rule 1] Is it salary / staff? -> Staff Costs
  ["Staff Costs", [
    r("\\bstaff salary\\b"), r("\\bsalary\\b"), r("\\bpayroll\\b"), r("\\bwages?\\b"),
    r("\\bcasual\\b"), r("\\bpayment for casual workers\\b"),
    r("\\bstaff\\b"), r("\\bmedical\\b"), r("\\bhospital\\b"), r("\\bclinic\\b"), r("\\bhmo\\b"), // Staff health
    r("\\bchef\\b"), r("\\bdriver\\b"), r("\\bnysc\\b"), r("\\bcorpers?\\b"),
    r("\\bwelfare\\b"), r("\\bpalliative\\b"), r("\\bcola\\b"), r("\\bchild support\\b"),
    r("\\bstaff loan\\b"), r("\\btraining\\b"), r("\\bseminar\\b"), r("\\brecruitment\\b"), r("\\bhiring\\b")
  ], 'debit'],

  // [Rule 2] Is it student-related / exam / uniform? -> Cost of Service
  ["Cost of Service", [
    r("\\bexam\\b"), r("\\bwaec\\b"), r("\\bneco\\b"), r("\\bjamb\\b"), r("\\bsat\\b"), r("\\bforeign fees?\\b"),
    r("\\bstudent\\b"), r("\\btuition\\b"), r("\\buniform\\b"), r("\\bppe\\b"),
    r("\\blesson\\b"), r("\\bbooks?\\b"), r("\\bkitchen\\b"), r("\\bcanteen\\b"), r("\\bsnacks\\b"),
    r("\\bhostel\\b"), r("\\bmatron\\b"),
    r("\\bvisa\\b"), r("\\bimmigration\\b"), r("\\bpermit\\b"), r("\\bquota\\b"), r("\\bcerpac\\b"), r("\\bgreen card\\b"),
    r("\\bregistration\\b"), r("\\bform\\b")
  ], 'debit'],

  // [Rule 3] Is it repairs or servicing? -> Repairs & Maintenance
  ["Repairs & Maintenance", [
    r("\\brepairs?\\b"), r("\\bmaintenance\\b"), r("\\bservicing\\b"),
    r("\\bmechanic\\b"), r("\\bcar part\\b"), r("\\btyre\\b"), r("\\btire\\b"), r("\\balignment\\b"), r("\\bvulcanizer\\b"), r("\\bcar wash\\b"),
    r("\\bgenerator\\b"), r("\\bcleaning\\b"), r("\\bcleaner\\b")
  ], 'debit'],

  // [Rule 4] Is it utility or fuel? -> Utilities
  ["Utilities", [
    r("\\bfuel\\b"), r("\\bpetrol\\b"), r("\\bdiesel\\b"), r("\\bgas\\b"), r("\\boil\\b"), r("\\bfilling station\\b"), r("\\btotal energies\\b"),
    r("\\belectricity\\b"), r("\\bpower\\b"), r("\\bikedc\\b"), r("\\bekedc\\b"), r("\\baedc\\b"), r("\\bphcn\\b"), r("\\bnepa\\b"),
    r("\\bwater\\b"), r("\\bswc\\b"), r("\\btanker\\b"),
    r("\\bwaste\\b"), r("\\brefuse\\b"), r("\\bsewage\\b"), r("\\blawma\\b"),
    r("\\binternet\\b"), r("\\bdata\\b"), r("\\bairtime\\b"), r("\\bmtn\\b"), r("\\bglo\\b"), r("\\bairtel\\b"), r("\\b9mobile\\b"), r("\\bstarlink\\b"), r("\\bfibre\\b"), r("\\bwifi\\b")
  ], 'debit'],

  // [Rule 5] Is it bank / SMS / charges? -> Bank Charges (Preserved logic + New additions)
  ["Bank Charges", [
    r("\\bpp_fee\\b"), r("\\bpp fee\\b"), r("\\bpayment processing fee\\b"),
    r("\\bpp_fr_chg\\b"), r("\\bpp_fr_vat\\b"), r("\\bfgn electronic money transfer levy\\b"),
    r("\\belectronic money transfer levy\\b"), r("\\btransfer levy"), 
    r("\\bcharges?\\b"), r("\\bcommission\\b"), r("\\bsms\\b"), r("\\balert\\b"), 
    r("\\bstamp\\b"), r("\\bvat\\b"), r("\\bvatcharges?\\b"), r("vat\\s*charges?"), 
    r("\\btransfercharges?\\b"), r("transfer\\s*charges?"), r("\\bvalue added tax\\b"),
    r("\\bmaintenance fee\\b"),
    r("min.*bal"), // Flexible match for Minimum Balance e.g. "MIN BAL", "MINIMUM BALANCE"
    r("credit interest.*min.*bal"), // Specific match for "Credit Interest - Min Bal" charge
    r("\\binterest\\b.*\\bdebit\\b") // Explicit debit interest
  ], 'debit'],

  // [Rule 6] Is it tax? -> Tax Payable (Excluding VAT which is usually Bank Charges in this context)
  ["Tax Payable", [
    r("\\bwht\\b"), r("\\bwithholding\\b"), r("\\btax payment\\b"), 
    r("\\bfirs\\b"), r("\\blirs\\b"), r("\\bremittance\\b"), r("\\bstatutory\\b")
  ], 'debit'],

  // [Rule 7] Is it asset purchase? -> Capital Asset
  ["Capital Asset", [
    r("\\basset\\b"), r("\\bpurchase of\\b"), r("\\bacquisition\\b"),
    r("\\bproject\\b"), r("\\bworks\\b"), r("\\bconstruction\\b"), r("\\brenovation\\b"), r("\\bbuilding\\b"),
    r("\\bland\\b"), r("\\bvaluation\\b"), r("\\bvariation\\b"),
    r("\\bequipment\\b"), r("\\bfurniture\\b"), r("\\bcomputer\\b"), r("\\blaptop\\b"), r("\\bportacabins\\b"),
    r("\\bscaffolding\\b"), r("\\bcrane\\b"), r("\\bmaterials\\b"), r("\\bwood\\b"), r("\\bsteel\\b"), r("\\btiles?\\b"), r("\\bpaint\\b"),
    r("\\binstallation\\b"), r("\\bpartition\\b"), r("\\bdoors?\\b")
  ], 'debit'],

  // [Rule 8] Otherwise? -> Administrative Expenses (Catch-all for specific OpEx patterns before fallback)
  ["Administrative Expenses", [
    // Travel / Logistics
    r("\\btravel\\b"), r("\\btransport\\b"), r("\\bflight\\b"), r("\\bticket\\b"), r("\\buber\\b"), r("\\bbolt\\b"), r("\\btaxi\\b"),
    r("\\bshipping\\b"), r("\\bcargo\\b"), r("\\bfreight\\b"), r("\\bdispatch\\b"), r("\\btoll\\b"), r("\\bparking\\b"),
    
    // Office / Ops
    r("\\boffice\\b"), r("\\brent\\b"), r("\\blease\\b"), r("\\bsupplies\\b"), r("\\bstationery\\b"), 
    r("\\bprinting\\b"), r("\\bprinter\\b"), r("\\bcourier\\b"), r("\\bdhl\\b"), r("\\bfedex\\b"),
    r("\\bsoftware\\b"), r("\\bzoom\\b"), r("\\bslack\\b"), r("\\bsubscription\\b"),
    
    // Professional
    r("\\bprofessional fees?\\b"), r("accounting"), r("\\blegal\\b"), r("\\bconsulting\\b"), r("\\baudit\\b"), r("\\blawyer\\b"), r("\\bsolicitor\\b"),
    r("\\bsecurity\\b"), r("\\bmarketing\\b"), r("\\bads?\\b"), r("\\bgoogle\\b"), r("\\bfacebook\\b"), r("\\binstagram\\b"),
    
    // General
    r("\\bgeneral\\b"), r("\\bmisc\\b"), r("\\bshopping\\b"), r("\\bkonga\\b"), r("\\bjumia\\b"), r("\\bamazon\\b"), r("\\bgroceries\\b"),
    r("\\bgift\\b"), r("\\bdonation\\b"), r("\\bpaystack\\b"), r("\\bpos\\b")
  ], 'debit'],

  // Fallbacks
  ["Incoming Transfer", [r("\\btransfer from\\b"), r("\\bonb transfer from\\b")], 'credit'],
  ["Administrative Expenses", [r("\\batm\\b"), r("\\bcash\\b"), r("\\bwithdrawal\\b"), r("\\btransfer\\b"), r("\\bnip\\b"), r("\\btrf\\b")], 'debit']
];

const CHARGE_KEYWORDS = [
  "vat", "vatcharge", "vat charges", "vatcharges",
  "charge", "charges", "transfercharges", "transfer charges",
  "commission", "levy", "sms alert", "sms", "stamp duty",
  "maintenance fee"
];

// --- MAIN LOGIC ---

const getCleanDescription = (desc: string): string => {
  return desc.replace(/^(REV\/|REVERSAL\s+|REVERSAL\/)/i, '').trim();
};

const findCategoryMatch = (desc: string, isCredit: boolean): string | null => {
  for (const [category, patterns, direction] of CATEGORY_RULES) {
    // If rule is Credit-only but tx is Debit, skip
    if (direction === 'credit' && !isCredit) continue;
    // If rule is Debit-only but tx is Credit, skip
    if (direction === 'debit' && isCredit) continue;
    
    for (const pattern of patterns) {
      if (pattern.test(desc)) {
        return category;
      }
    }
  }
  return null;
};

export const categorizeTransaction = (t: Transaction): Transaction => {
  const updated = { ...t };
  const rawDesc = (t.description || "").trim();
  const rawDescLower = rawDesc.toLowerCase();
  const isCredit = (t.credit || 0) > 0;
  
  // 1. PRIORITY CHARGE CHECK (Debit Only) - STRICTLY PRESERVED
  if (!isCredit) {
    // Normalize spaces for this check
    const descNorm = rawDescLower.replace("transfercharges", "transfer charges").replace("vatcharges", "vat charges");
    const isCharge = CHARGE_KEYWORDS.some(k => descNorm.includes(k));
    if (isCharge) {
      updated.category = "Bank Charges";
      return updated;
    }
  }

  // 2. SMALL AMOUNT CHECK (Debit Only) - STRICTLY PRESERVED
  if (!isCredit) {
    const smallAmountMatches = [50.00, 3.75, 1.88].some(x => Math.abs(t.debit - x) < 0.01);
    const isVerySmall = t.debit <= 2.10;
    
    if (smallAmountMatches || isVerySmall) {
      updated.category = "Bank Charges";
      return updated;
    }
  }

  // 3. REGEX RULES MATCHING (Main Logic)
  // Check 1: Match against RAW description
  let match = findCategoryMatch(rawDesc, isCredit);
  if (match) {
    updated.category = match;
    return updated;
  }

  // Check 2: REVERSAL LOGIC
  const looksLikeReversal = /^(REV\/|REVERSAL)/i.test(rawDesc) || t.is_reversal;
  if (looksLikeReversal) {
    const cleanDesc = getCleanDescription(rawDesc);
    if (cleanDesc !== rawDesc) {
      match = findCategoryMatch(cleanDesc, isCredit);
      if (match) {
        updated.category = match;
        updated.is_reversal = true;
        return updated;
      }
    }
  }

  // 4. FALLBACK FOR UNMATCHED
  if (!updated.category || updated.category === "Unallocated") {
    // If it's a generic debit that didn't match specific Admin patterns but is likely Admin
    if (!isCredit) {
       // "Otherwise? -> Administrative Expenses"
       updated.category = "Administrative Expenses";
    }
  }
  
  return updated;
};
