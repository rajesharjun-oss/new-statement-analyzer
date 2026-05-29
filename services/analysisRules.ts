import { AnalysisTemplate, ClassifiedTransaction, ConfidenceLabel, ReconciliationCheck, Transaction } from "../types";

const reviewCategory = "Review Required";
const notApplicableKeywords = [
  "stamp duty",
  "sms alert",
  "account maintenance",
  "acct maint",
  "vat on bank charge",
  "value added tax on charge",
  "card charge",
  "transfer charge",
  "commission",
  "nip charge",
  "pos stamp duty",
  "reversal",
  "reversed",
  "failed",
  "opening balance",
  "closing balance",
  "internal transfer",
  "own account transfer",
  "balance brought forward"
];
const strongEntityKeywords = [
  "ltd",
  "limited",
  "plc",
  "enterprise",
  "enterprises",
  "ventures",
  "company",
  "incorporated",
  "nigeria limited",
  "firs",
  "federal inland revenue",
  "wht",
  "cit",
  "tax payment"
];
const salaryKeywords = ["salary", "payroll", "staff salary", "wages"];
const commonTransferChargeAmounts = [1.25, 2.5, 3.75, 6.83, 10, 25, 26.88, 50, 53.75, 90.96, 100, 107.5];

function money(value: unknown): number {
  const n = typeof value === "number" ? value : Number(String(value ?? "0").replace(/,/g, ""));
  return Number.isFinite(n) ? n : 0;
}

function tokenizeKeywords(value: string): string[] {
  return value.split(",").map(k => k.trim()).filter(Boolean);
}

export function cleanupTransactionDescription(value: string): string {
  return String(value || "")
    .normalize("NFKC")
    .replace(/[\u00a0\u1680\u180e\u2000-\u200d\u2028\u2029\u202f\u205f\u2060\ufeff\u00ad]/g, " ")
    .replace(/\bL\s*T\s*D\b/gi, "LTD")
    .replace(/\bLIMITE\b/gi, "LIMITED")
    .replace(/\b\d{1,2}\/\d{1,2}\/\d{4}\s+Details\b/gi, " ")
    .replace(/\bTransaction\s+Date\b/gi, " ")
    .replace(/\bValue\s+Date\b/gi, " ")
    .replace(/\bDetails\b/gi, " ")
    .replace(/\b\d+\s+of\s+\d+\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function normalizeNarration(value: string): string {
  return cleanupTransactionDescription(value)
    .normalize("NFKC")
    .replace(/[\u00a0\u1680\u180e\u2000-\u200d\u2028\u2029\u202f\u205f\u2060\ufeff\u00ad]/g, " ")
    .replace(/[\u2010-\u2015]/g, "-")
    .replace(/[\u2018\u2019`´]/g, "'")
    .replace(/[\u201c\u201d]/g, "\"")
    .replace(/\bL\s*T\s*D\b/gi, "LTD")
    .replace(/\bLIMITE\b/gi, "LIMITED")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}@&*'/-]+/gu, " ")
    .replace(/[-_/]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function normalizeTransactions(transactions: Transaction[], sourceFileName: string): ClassifiedTransaction[] {
  return transactions.map((t, index) => {
    const rawText = t.rawText || t.description || "";
    return {
      ...t,
      id: t.id || `txn-${index + 1}`,
      sourceFileName,
      pageNumber: t.pageNumber ?? t.page_number ?? t._page,
      rowNumber: t.rowNumber ?? index + 1,
      transactionDate: t.transactionDate || t.date,
      valueDate: t.valueDate,
      reference: t.reference || "",
      rawText,
      description: cleanupTransactionDescription(t.description || ""),
      debit: money(t.debit),
      credit: money(t.credit),
      balance: money(t.balance),
      category: t.category || reviewCategory,
      subCategory: t.subCategory ?? null,
      taxAuthority: t.taxAuthority ?? null,
      confidence: normalizeConfidence(t.confidence),
      reason: t.reason || "Extracted from statement.",
      decisionSource: t.decisionSource || t.decision_source || "SYSTEM",
      reviewRequired: Boolean(t.reviewRequired)
    };
  });
}

export function normalizeConfidence(value: unknown): ConfidenceLabel {
  if (value === "High" || value === "Medium" || value === "Low") return value;
  if (typeof value === "number") {
    if (value >= 0.8) return "High";
    if (value >= 0.55) return "Medium";
  }
  return "Low";
}

function appliesToScope(txn: ClassifiedTransaction, scope: "debit" | "credit" | "both") {
  if (scope === "both") return true;
  if (scope === "debit") return (txn.debit || 0) > 0;
  return (txn.credit || 0) > 0;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function keywordMatches(normalizedText: string, keyword: string) {
  const normalizedKeyword = normalizeNarration(keyword);
  if (!normalizedKeyword) return false;
  const words = normalizedKeyword.split(" ").filter(Boolean);
  if (words.length === 1) {
    return new RegExp(`(^|\\s)${escapeRegExp(normalizedKeyword)}(?=\\s|$)`).test(normalizedText);
  }
  return normalizedText.includes(normalizedKeyword);
}

function includesAny(text: string, keywords: string[]) {
  return keywords.some(keyword => keywordMatches(text, keyword));
}

function hasStrongEntityIndicator(text: string) {
  return includesAny(text, strongEntityKeywords);
}

function isPosPurchase(text: string) {
  return keywordMatches(text, "pos purchase") || keywordMatches(text, "pos purch") || text.startsWith("pos ");
}

function isCommonTransferCharge(transaction: ClassifiedTransaction, text: string) {
  const debit = money(transaction.debit);
  if (debit <= 0 || money(transaction.credit) > 0) return false;
  const isCommonAmount = commonTransferChargeAmounts.some(amount => Math.abs(debit - amount) <= 0.01);
  if (!isCommonAmount) return false;
  return includesAny(text, ["cob trf to", "nip transfer", "nip", "transfer fee", "transfer charge", "cob trf", "trf", "interbank transfer", "bank transfer", "others"]);
}

function isNotApplicable(transaction: ClassifiedTransaction, text: string) {
  return includesAny(text, notApplicableKeywords) || isCommonTransferCharge(transaction, text);
}

function inferIndividualName(text: string) {
  if (hasStrongEntityIndicator(text) || isPosPurchase(text) || isNotApplicable({ debit: 0, credit: 0 } as ClassifiedTransaction, text)) return false;
  if (includesAny(text, ["vendor", "vendors", "supplier", "subscription", "internet", "merchant", "services", "cleaning", "medical", "digital", "logistics", "tutoring"])) return false;
  if (includesAny(text, ["mr", "mrs", "miss", "dr"])) return true;

  const cleaned = text
    .replace(/\b(cob|trf|transfer|to|from|nip|neft|payment|paid|for|on|behalf|beh)\b/g, " ")
    .replace(/[@*&0-9]+/g, " ");
  const tokens = cleaned.split(/\s+/).filter(t => /^[a-z]{3,}$/.test(t));
  return tokens.length >= 2 && tokens.slice(0, 4).some(t => t.length > 3);
}

function firsTaxAuthority(category: string) {
  return (category === "FIRS" || category === "SIRS" || category === "Not Applicable" || category === "Review Required")
    ? category
    : null;
}

function applyFirsSirsRules(transaction: ClassifiedTransaction, template: AnalysisTemplate): ClassifiedTransaction {
  const text = normalizeNarration(`${transaction.description} ${transaction.reference || ""} ${transaction.rawText || ""}`);

  if (isNotApplicable(transaction, text)) {
    return {
      ...transaction,
      category: "Not Applicable",
      taxAuthority: "Not Applicable",
      confidence: "High",
      reason: isCommonTransferCharge(transaction, text)
        ? "Matched common bank transfer/NIP charge pattern."
        : "Matched non-taxable bank item before entity classification.",
      decisionSource: "RULE",
      reviewRequired: false
    };
  }

  if (isPosPurchase(text)) {
    if (hasStrongEntityIndicator(text)) {
      return {
        ...transaction,
        category: "FIRS",
        taxAuthority: "FIRS",
        confidence: "High",
        reason: "POS narration contains a strong company/entity indicator.",
        decisionSource: "RULE",
        reviewRequired: false
      };
    }
    return {
      ...transaction,
      category: reviewCategory,
      taxAuthority: "Review Required",
      confidence: "Low",
      reason: "POS merchant name has no strong company/entity indicator.",
      decisionSource: "SYSTEM",
      reviewRequired: template.markUncertainAsReview
    };
  }

  if (hasStrongEntityIndicator(text)) {
    return {
      ...transaction,
      category: "FIRS",
      taxAuthority: "FIRS",
      confidence: "High",
      reason: "Matched strong company/entity or tax authority indicator.",
      decisionSource: "RULE",
      reviewRequired: false
    };
  }

  if (includesAny(text, ["limi"])) {
    return {
      ...transaction,
      category: reviewCategory,
      taxAuthority: "Review Required",
      confidence: "Medium",
      reason: "Possible broken LIMITED suffix needs review.",
      decisionSource: "SYSTEM",
      reviewRequired: template.markUncertainAsReview
    };
  }

  if (includesAny(text, salaryKeywords)) {
    const salaryTreatment = template.salaryTreatment || (template.treatSalaryAsSirs ? "sirs" : "review");
    if (salaryTreatment === "sirs") {
      return {
        ...transaction,
        category: "SIRS",
        taxAuthority: "SIRS",
        confidence: "Medium",
        reason: "Salary/payroll setting treats staff payments as SIRS.",
        decisionSource: "RULE",
        reviewRequired: false
      };
    }
    if (salaryTreatment === "not_applicable") {
      return {
        ...transaction,
        category: "Not Applicable",
        taxAuthority: "Not Applicable",
        confidence: "Medium",
        reason: "Salary/payroll setting treats staff payments as Not Applicable.",
        decisionSource: "RULE",
        reviewRequired: false
      };
    }
    return {
      ...transaction,
      category: reviewCategory,
      taxAuthority: "Review Required",
      confidence: "Low",
      reason: "Salary/payroll payment requires review.",
      decisionSource: "SYSTEM",
      reviewRequired: template.markUncertainAsReview
    };
  }

  const sirsRule = template.categories.find(rule => rule.outputLabel === "SIRS");
  if (sirsRule && includesAny(text, sirsRule.includeKeywords) && !includesAny(text, sirsRule.excludeKeywords)) {
    return {
      ...transaction,
      category: "SIRS",
      taxAuthority: "SIRS",
      confidence: "Medium",
      reason: "Matched individual-payment rule keyword.",
      decisionSource: "RULE",
      reviewRequired: false
    };
  }

  if (inferIndividualName(text)) {
    return {
      ...transaction,
      category: "SIRS",
      taxAuthority: "SIRS",
      confidence: "Medium",
      reason: "Narration resembles a personal-name payment.",
      decisionSource: "RULE",
      reviewRequired: false
    };
  }

  return {
    ...transaction,
    category: reviewCategory,
    taxAuthority: "Review Required",
    confidence: "Low",
    reason: "No deterministic rule matched.",
    decisionSource: "SYSTEM",
    reviewRequired: template.markUncertainAsReview
  };
}

export function applyDeterministicRules(
  transaction: ClassifiedTransaction,
  template: AnalysisTemplate
): ClassifiedTransaction {
  if (!appliesToScope(transaction, template.scope)) {
    return {
      ...transaction,
      category: "Out of Scope",
      confidence: "High",
      reason: `Template analyzes ${template.scope} transactions only.`,
      decisionSource: "SYSTEM",
      reviewRequired: false
    };
  }

  if (template.id === "firs-sirs-na") {
    return applyFirsSirsRules(transaction, template);
  }

  const text = normalizeNarration(`${transaction.description} ${transaction.reference || ""} ${transaction.rawText || ""}`);
  const rules = [...template.categories].sort((a, b) => b.priority - a.priority);

  for (const rule of rules) {
    if (!appliesToScope(transaction, rule.appliesTo)) continue;
    const include = rule.includeKeywords.length === 0 || includesAny(text, rule.includeKeywords);
    const exclude = rule.excludeKeywords.length > 0 && includesAny(text, rule.excludeKeywords);
    if (include && !exclude && rule.includeKeywords.length > 0) {
      const taxAuthority = template.id === "firs-sirs-na"
        ? firsTaxAuthority(rule.outputLabel)
        : null;
      return {
        ...transaction,
        category: rule.outputLabel,
        taxAuthority: taxAuthority as any,
        confidence: "High",
        reason: `Matched rule "${rule.name}" by keyword.`,
        decisionSource: "RULE",
        reviewRequired: false
      };
    }
  }

  return {
    ...transaction,
    category: reviewCategory,
    taxAuthority: template.id === "firs-sirs-na" ? "Review Required" : transaction.taxAuthority ?? null,
    confidence: "Low",
    reason: "No deterministic rule matched.",
    decisionSource: "SYSTEM",
    reviewRequired: template.markUncertainAsReview
  };
}

export function classifyByTemplateRules(
  transactions: ClassifiedTransaction[],
  template: AnalysisTemplate
): ClassifiedTransaction[] {
  return transactions.map(txn => applyDeterministicRules(txn, template));
}

export function parseKeywordInput(value: string): string[] {
  return tokenizeKeywords(value);
}

export function calculateCategorySummary(transactions: ClassifiedTransaction[]) {
  const map = new Map<string, { category: string; debitTotal: number; creditTotal: number; netMovement: number; transactionCount: number }>();
  transactions.forEach(t => {
    const category = t.category || reviewCategory;
    const row = map.get(category) || { category, debitTotal: 0, creditTotal: 0, netMovement: 0, transactionCount: 0 };
    row.debitTotal += money(t.debit);
    row.creditTotal += money(t.credit);
    row.netMovement = row.creditTotal - row.debitTotal;
    row.transactionCount += 1;
    map.set(category, row);
  });
  return Array.from(map.values()).sort((a, b) => Math.abs(b.netMovement) - Math.abs(a.netMovement));
}

export function calculateMonthlySummary(transactions: ClassifiedTransaction[]) {
  const map = new Map<string, { month: string; category: string; debitTotal: number; creditTotal: number; netMovement: number; transactionCount: number }>();
  transactions.forEach(t => {
    const date = new Date(t.transactionDate || t.date);
    const month = Number.isNaN(date.getTime()) ? "Unknown" : `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    const category = t.category || reviewCategory;
    const key = `${month}|${category}`;
    const row = map.get(key) || { month, category, debitTotal: 0, creditTotal: 0, netMovement: 0, transactionCount: 0 };
    row.debitTotal += money(t.debit);
    row.creditTotal += money(t.credit);
    row.netMovement = row.creditTotal - row.debitTotal;
    row.transactionCount += 1;
    map.set(key, row);
  });
  return Array.from(map.values()).sort((a, b) => a.month.localeCompare(b.month) || a.category.localeCompare(b.category));
}

export function calculateReconciliation(
  transactions: ClassifiedTransaction[],
  openingBalance?: number | null,
  closingBalance?: number | null,
  tolerance = 0.05
): ReconciliationCheck {
  const totalDebit = transactions.reduce((sum, t) => sum + money(t.debit), 0);
  const totalCredit = transactions.reduce((sum, t) => sum + money(t.credit), 0);
  const first = transactions[0];
  const last = transactions[transactions.length - 1];
  const opening = openingBalance ?? (first ? first.balance + first.debit - first.credit : null);
  const actualClosing = closingBalance ?? (last ? last.balance : null);
  const expectedClosingBalance = opening === null ? null : opening + totalCredit - totalDebit;
  const difference = expectedClosingBalance === null || actualClosing === null ? null : actualClosing - expectedClosingBalance;
  const status = difference === null ? "Unverified" : Math.abs(difference) <= tolerance ? "Passed" : "Failed";
  return { openingBalance: opening, totalDebit, totalCredit, expectedClosingBalance, actualClosingBalance: actualClosing, difference, status };
}
