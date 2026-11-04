import {
  AnalysisQualityIssue,
  AnalysisQualityReport,
  AnalysisInsights,
  AnalysisNarrative,
  AnalysisTemplate,
  ClassifiedTransaction,
  ConfidenceLabel,
  ReconciliationCheck,
  Transaction
} from "../types";

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
  "counter cheque issue charge",
  "counter chq issue charge",
  "cheque issue charge",
  "chq issue charge",
  "vat counter chq",
  "vat counter cheque",
  "vat on cheque",
  "cheque book charge",
  "cheque charge",
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
const commonTransferChargeAmounts = [1.25, 2.5, 3.75, 6.83, 10, 10.75, 25, 26.88, 50, 53.75, 90.96, 100, 107.5];

function money(value: unknown): number {
  const n = typeof value === "number" ? value : Number(String(value ?? "0").replace(/,/g, ""));
  return Number.isFinite(n) ? n : 0;
}

function toMinorUnits(value: unknown): number {
  return Math.round(money(value) * 100);
}

function fromMinorUnits(value: number): number {
  return value / 100;
}

function percent(count: number, total: number): number {
  return total > 0 ? Math.round((count / total) * 1000) / 10 : 0;
}

function validUtcDate(year: number, month: number, day: number): number | null {
  const value = Date.UTC(year, month - 1, day);
  const date = new Date(value);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return value;
}

export function parseTransactionDate(value: unknown): number | null {
  const text = String(value ?? "").trim();
  if (!text) return null;

  let match = text.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
  if (match) return validUtcDate(Number(match[1]), Number(match[2]), Number(match[3]));

  match = text.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})$/);
  if (match) {
    const year = Number(match[3]) < 100 ? 2000 + Number(match[3]) : Number(match[3]);
    return validUtcDate(year, Number(match[2]), Number(match[1]));
  }

  match = text.match(/^(\d{1,2})[-\s]([A-Za-z]{3,9})[-\s](\d{2}|\d{4})$/);
  if (match) {
    const months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
    const month = months.indexOf(match[2].slice(0, 3).toLowerCase()) + 1;
    const year = Number(match[3]) < 100 ? 2000 + Number(match[3]) : Number(match[3]);
    return month > 0 ? validUtcDate(year, month, Number(match[1])) : null;
  }

  return null;
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
    .replace(/\s+\d{1,2}\/\d{1,2}\/\d{4}\s*$/g, "")
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
  if (includesAny(text, ["cob trf", "trf to", "nip transfer"])) return false;

  const cleaned = text
    .replace(/\b(cob|trf|transfer|to|from|nip|neft|payment|paid|for|on|behalf|beh)\b/g, " ")
    .replace(/[@*&0-9]+/g, " ");
  const tokens = cleaned.split(/\s+/).filter(t => /^[a-z]{3,}$/.test(t));
  return tokens.length >= 2 && tokens.slice(0, 4).some(t => t.length > 3);
}

function looksLikeUnregisteredTradeName(text: string) {
  if (hasStrongEntityIndicator(text) || isNotApplicable({ debit: 0, credit: 0 } as ClassifiedTransaction, text)) return false;
  if (!includesAny(text, ["cob trf", "trf to", "transfer to", "nip transfer", "pos purchase"])) return false;
  if (includesAny(text, ["mr", "mrs", "miss", "dr", "salary", "payroll"])) return false;
  const tradeHints = [
    "oil", "print", "cakes", "eng", "engineering", "office", "music", "mus", "gold", "stores",
    "superstores", "food", "foods", "market", "ventures", "logistics", "cleaning", "medical",
    "digital", "internet", "subscription", "school", "academy", "studio", "fashion", "pharmacy",
    "mart", "shop", "enterprise", "attainable", "ryteprint", "goldmender", "damac", "palmacedar"
  ];
  if (includesAny(text, tradeHints)) return true;
  const cleaned = text
    .replace(/\b(cob|trf|transfer|to|from|nip|neft|payment|paid|for|on|behalf|beh|pos|purchase)\b/g, " ")
    .replace(/[@*&0-9]+/g, " ");
  const tokens = cleaned.split(/\s+/).filter(t => /^[a-z]{3,}$/.test(t));
  return tokens.length >= 1 && tokens.length <= 3;
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

  if (looksLikeUnregisteredTradeName(text)) {
    const treatment = template.tradeNameTreatment || "review";
    if (treatment === "firs") {
      return {
        ...transaction,
        category: "FIRS",
        taxAuthority: "FIRS",
        confidence: "Medium",
        reason: "Unregistered business/trade-name setting treats this row as FIRS.",
        decisionSource: "RULE",
        reviewRequired: false
      };
    }
    if (treatment === "sirs") {
      return {
        ...transaction,
        category: "SIRS",
        taxAuthority: "SIRS",
        confidence: "Medium",
        reason: "Unregistered business/trade-name setting treats this row as SIRS.",
        decisionSource: "RULE",
        reviewRequired: false
      };
    }
    return {
      ...transaction,
      category: reviewCategory,
      taxAuthority: "Review Required",
      confidence: "Low",
      reason: "Possible unregistered business/trade name requires review.",
      decisionSource: "SYSTEM",
      reviewRequired: template.markUncertainAsReview
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
    row.debitTotal = fromMinorUnits(toMinorUnits(row.debitTotal) + toMinorUnits(t.debit));
    row.creditTotal = fromMinorUnits(toMinorUnits(row.creditTotal) + toMinorUnits(t.credit));
    row.netMovement = fromMinorUnits(toMinorUnits(row.creditTotal) - toMinorUnits(row.debitTotal));
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
    row.debitTotal = fromMinorUnits(toMinorUnits(row.debitTotal) + toMinorUnits(t.debit));
    row.creditTotal = fromMinorUnits(toMinorUnits(row.creditTotal) + toMinorUnits(t.credit));
    row.netMovement = fromMinorUnits(toMinorUnits(row.creditTotal) - toMinorUnits(row.debitTotal));
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
  const totalDebitMinor = transactions.reduce((sum, t) => sum + toMinorUnits(t.debit), 0);
  const totalCreditMinor = transactions.reduce((sum, t) => sum + toMinorUnits(t.credit), 0);
  const first = transactions[0];
  const last = transactions[transactions.length - 1];
  const hasExtractedBalances = transactions.some(transaction => toMinorUnits(transaction.balance) !== 0);
  const openingMinor = openingBalance !== undefined && openingBalance !== null
    ? toMinorUnits(openingBalance)
    : first && hasExtractedBalances
      ? toMinorUnits(first.balance) + toMinorUnits(first.debit) - toMinorUnits(first.credit)
      : null;
  const actualClosingMinor = closingBalance !== undefined && closingBalance !== null
    ? toMinorUnits(closingBalance)
    : last && hasExtractedBalances
      ? toMinorUnits(last.balance)
      : null;
  const expectedClosingMinor = openingMinor === null ? null : openingMinor + totalCreditMinor - totalDebitMinor;
  const differenceMinor = expectedClosingMinor === null || actualClosingMinor === null
    ? null
    : actualClosingMinor - expectedClosingMinor;
  const toleranceMinor = Math.max(0, toMinorUnits(tolerance));
  const status = differenceMinor === null ? "Unverified" : Math.abs(differenceMinor) <= toleranceMinor ? "Passed" : "Failed";
  return {
    openingBalance: openingMinor === null ? null : fromMinorUnits(openingMinor),
    totalDebit: fromMinorUnits(totalDebitMinor),
    totalCredit: fromMinorUnits(totalCreditMinor),
    expectedClosingBalance: expectedClosingMinor === null ? null : fromMinorUnits(expectedClosingMinor),
    actualClosingBalance: actualClosingMinor === null ? null : fromMinorUnits(actualClosingMinor),
    difference: differenceMinor === null ? null : fromMinorUnits(differenceMinor),
    status
  };
}

function transactionIds(rows: ClassifiedTransaction[]): string[] {
  return rows.slice(0, 100).map(row => row.id);
}

export function calculateAnalysisQuality(
  transactions: ClassifiedTransaction[],
  reconciliation: ReconciliationCheck
): AnalysisQualityReport {
  const total = transactions.length;
  if (total === 0) {
    return {
      score: 0,
      grade: "Unreliable",
      status: "Failed",
      transactionCount: 0,
      classificationCoveragePercent: 0,
      highConfidencePercent: 0,
      sourceEvidencePercent: 0,
      reviewCount: 0,
      duplicateCount: 0,
      missingDescriptionCount: 0,
      invalidDateCount: 0,
      outOfOrderDateCount: 0,
      invalidAmountDirectionCount: 0,
      balanceContinuityIssueCount: 0,
      issues: [{
        code: "NO_TRANSACTIONS",
        severity: "Critical",
        count: 1,
        message: "No transactions are available for analysis.",
        transactionIds: []
      }]
    };
  }

  const reviewRows = transactions.filter(row => {
    const category = String(row.category || "").trim().toLowerCase();
    return row.reviewRequired || ["review required", "unallocated", "uncategorized", "unallocated/review required"].includes(category);
  });
  const highConfidenceRows = transactions.filter(row => row.confidence === "High");
  const missingDescriptionRows = transactions.filter(row => !String(row.description || "").trim());
  const invalidDateRows = transactions.filter(row => parseTransactionDate(row.transactionDate || row.date) === null);
  const evidenceGapRows = transactions.filter(row => {
    const locator = (row.pageNumber ?? row.page_number ?? row._page ?? row.rowNumber) !== undefined;
    const sourceText = String(row.rawText || row.description || "").trim();
    return !String(row.sourceFileName || "").trim() || !locator || !sourceText;
  });
  const invalidAmountRows = transactions.filter(row => {
    const debit = toMinorUnits(row.debit);
    const credit = toMinorUnits(row.credit);
    const balanceMarkerText = normalizeNarration(`${row.category} ${row.description}`);
    const isBalanceMarker = balanceMarkerText.includes("opening balance") || balanceMarkerText.includes("closing balance");
    return debit < 0 || credit < 0 || (debit > 0 && credit > 0) || (!isBalanceMarker && debit === 0 && credit === 0);
  });

  const duplicateRows: ClassifiedTransaction[] = [];
  const seen = new Set<string>();
  transactions.forEach(row => {
    const key = [
      String(row.transactionDate || row.date || "").trim().toLowerCase(),
      normalizeNarration(row.reference || ""),
      normalizeNarration(row.description || ""),
      toMinorUnits(row.debit),
      toMinorUnits(row.credit),
      toMinorUnits(row.balance)
    ].join("|");
    if (seen.has(key)) duplicateRows.push(row);
    else seen.add(key);
  });

  const datedRows = transactions
    .map(row => ({ row, value: parseTransactionDate(row.transactionDate || row.date) }))
    .filter((item): item is { row: ClassifiedTransaction; value: number } => item.value !== null);
  const ascending = datedRows.length < 2 || datedRows[datedRows.length - 1].value >= datedRows[0].value;
  const outOfOrderRows: ClassifiedTransaction[] = [];
  for (let index = 1; index < datedRows.length; index += 1) {
    const previous = datedRows[index - 1];
    const current = datedRows[index];
    if ((ascending && current.value < previous.value) || (!ascending && current.value > previous.value)) {
      outOfOrderRows.push(current.row);
    }
  }

  const balanceIssueRows: ClassifiedTransaction[] = [];
  const balanceToleranceMinor = 5;
  for (let index = 1; index < transactions.length; index += 1) {
    const previous = transactions[index - 1];
    const current = transactions[index];
    const previousBalance = toMinorUnits(previous.balance);
    const currentBalance = toMinorUnits(current.balance);
    if (previousBalance === 0 || currentBalance === 0) continue;

    const difference = ascending
      ? currentBalance - (previousBalance + toMinorUnits(current.credit) - toMinorUnits(current.debit))
      : previousBalance - (currentBalance + toMinorUnits(previous.credit) - toMinorUnits(previous.debit));
    if (Math.abs(difference) > balanceToleranceMinor) balanceIssueRows.push(current);
  }

  const issues: AnalysisQualityIssue[] = [];
  const addIssue = (
    code: string,
    severity: AnalysisQualityIssue["severity"],
    rows: ClassifiedTransaction[],
    message: string,
    count = rows.length
  ) => {
    if (count > 0) issues.push({ code, severity, count, message, transactionIds: transactionIds(rows) });
  };

  if (reconciliation.status === "Failed") {
    issues.push({
      code: "RECONCILIATION_FAILED",
      severity: "Critical",
      count: 1,
      message: "Opening balance plus credits minus debits does not equal the closing balance.",
      transactionIds: []
    });
  } else if (reconciliation.status === "Unverified") {
    issues.push({
      code: "RECONCILIATION_UNVERIFIED",
      severity: "Warning",
      count: 1,
      message: "Opening or closing balance is unavailable, so reconciliation cannot be verified.",
      transactionIds: []
    });
  }
  addIssue("INVALID_AMOUNT_DIRECTION", "Critical", invalidAmountRows, "Rows contain negative amounts, both debit and credit, or no monetary movement.");
  addIssue("BALANCE_CONTINUITY", "Warning", balanceIssueRows, "Running balances do not follow the transaction movement within the configured tolerance.");
  addIssue("POSSIBLE_DUPLICATE", "Warning", duplicateRows, "Exact duplicate transaction signatures require review.");
  addIssue("MISSING_DESCRIPTION", "Warning", missingDescriptionRows, "Transaction descriptions are missing.");
  addIssue("INVALID_DATE", "Warning", invalidDateRows, "Transaction dates are missing or use an unsupported format.");
  addIssue("DATE_ORDER_ANOMALY", "Info", outOfOrderRows, "Transaction dates break the statement's dominant sort order.");
  addIssue("SOURCE_EVIDENCE_GAP", "Warning", evidenceGapRows, "Rows lack a source file, row/page locator, or source narration.");
  addIssue("REVIEW_REQUIRED", "Warning", reviewRows, "Rows remain unresolved and require a human decision.");

  const sourceEvidencePercent = percent(total - evidenceGapRows.length, total);
  let score = 100;
  if (reconciliation.status === "Failed") score -= 35;
  if (reconciliation.status === "Unverified") score -= 8;
  score -= Math.min(20, invalidAmountRows.length * 5);
  score -= Math.min(20, balanceIssueRows.length * 2);
  score -= Math.min(12, duplicateRows.length * 2);
  score -= Math.min(10, missingDescriptionRows.length * 2);
  score -= Math.min(8, invalidDateRows.length * 2);
  score -= Math.min(4, outOfOrderRows.length);
  score -= Math.min(20, Math.round((reviewRows.length / total) * 20));
  score -= Math.min(10, Math.round((100 - sourceEvidencePercent) / 10));
  score = Math.max(0, Math.min(100, score));

  const hasCriticalIssue = issues.some(issue => issue.severity === "Critical");
  const hasReviewIssue = issues.some(issue => issue.severity === "Warning");
  const status = hasCriticalIssue ? "Failed" : (hasReviewIssue || reconciliation.status !== "Passed") ? "Review Required" : "Passed";
  const grade = score >= 95 ? "Excellent" : score >= 85 ? "Good" : score >= 65 ? "Needs Review" : "Unreliable";

  return {
    score,
    grade,
    status,
    transactionCount: total,
    classificationCoveragePercent: percent(total - reviewRows.length, total),
    highConfidencePercent: percent(highConfidenceRows.length, total),
    sourceEvidencePercent,
    reviewCount: reviewRows.length,
    duplicateCount: duplicateRows.length,
    missingDescriptionCount: missingDescriptionRows.length,
    invalidDateCount: invalidDateRows.length,
    outOfOrderDateCount: outOfOrderRows.length,
    invalidAmountDirectionCount: invalidAmountRows.length,
    balanceContinuityIssueCount: balanceIssueRows.length,
    issues
  };
}

function counterpartyLabel(transaction: ClassifiedTransaction): string {
  const normalized = normalizeNarration(transaction.description || transaction.rawText || "")
    .replace(/\b[a-z0-9]*\d{5,}[a-z0-9]*\b/g, " ")
    .replace(/\b(?:nip|neft|cob|trf|transfer|payment|paid|from|to|for|ref|reference|txn|transaction|amount|ngn|debit|credit|online|mobile|bank)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return (normalized || normalizeNarration(transaction.description) || "unidentified counterparty")
    .slice(0, 72)
    .toUpperCase();
}

function quantile(values: number[], position: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = (sorted.length - 1) * position;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
}

function evidenceTransaction(transaction: ClassifiedTransaction, direction: "Debit" | "Credit") {
  return {
    id: transaction.id,
    date: transaction.transactionDate || transaction.date,
    description: transaction.description,
    amount: direction === "Debit" ? transaction.debit : transaction.credit,
    direction
  };
}

export function calculateAnalysisInsights(
  transactions: ClassifiedTransaction[],
  qualityReport?: AnalysisQualityReport
): AnalysisInsights {
  const totalDebitMinor = transactions.reduce((sum, row) => sum + toMinorUnits(row.debit), 0);
  const totalCreditMinor = transactions.reduce((sum, row) => sum + toMinorUnits(row.credit), 0);
  const dated = transactions
    .map(row => ({ row, timestamp: parseTransactionDate(row.transactionDate || row.date) }))
    .filter((item): item is { row: ClassifiedTransaction; timestamp: number } => item.timestamp !== null)
    .sort((a, b) => a.timestamp - b.timestamp);

  const monthlyMap = new Map<string, { debitMinor: number; creditMinor: number; count: number }>();
  dated.forEach(({ row, timestamp }) => {
    const date = new Date(timestamp);
    const month = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
    const current = monthlyMap.get(month) || { debitMinor: 0, creditMinor: 0, count: 0 };
    current.debitMinor += toMinorUnits(row.debit);
    current.creditMinor += toMinorUnits(row.credit);
    current.count += 1;
    monthlyMap.set(month, current);
  });
  const monthlyTrends = Array.from(monthlyMap.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([month, value], index, rows) => {
      const netMinor = value.creditMinor - value.debitMinor;
      const previous = index > 0 ? rows[index - 1][1] : null;
      const previousNetMinor = previous ? previous.creditMinor - previous.debitMinor : null;
      return {
        month,
        debitTotal: fromMinorUnits(value.debitMinor),
        creditTotal: fromMinorUnits(value.creditMinor),
        netMovement: fromMinorUnits(netMinor),
        transactionCount: value.count,
        netChangePercent: previousNetMinor === null || previousNetMinor === 0
          ? null
          : Math.round(((netMinor - previousNetMinor) / Math.abs(previousNetMinor)) * 1000) / 10
      };
    });

  let largestDebitRow: ClassifiedTransaction | null = null;
  let largestCreditRow: ClassifiedTransaction | null = null;
  transactions.forEach(row => {
    if (toMinorUnits(row.debit) > toMinorUnits(largestDebitRow?.debit)) largestDebitRow = row;
    if (toMinorUnits(row.credit) > toMinorUnits(largestCreditRow?.credit)) largestCreditRow = row;
  });

  const counterparties = new Map<string, { name: string; direction: "Debit" | "Credit"; totalMinor: number; ids: string[] }>();
  const addCounterparty = (row: ClassifiedTransaction, direction: "Debit" | "Credit", amountMinor: number) => {
    if (amountMinor <= 0) return;
    const name = counterpartyLabel(row);
    const key = `${direction}|${name}`;
    const current = counterparties.get(key) || { name, direction, totalMinor: 0, ids: [] };
    current.totalMinor += amountMinor;
    current.ids.push(row.id);
    counterparties.set(key, current);
  };
  transactions.forEach(row => {
    addCounterparty(row, "Debit", toMinorUnits(row.debit));
    addCounterparty(row, "Credit", toMinorUnits(row.credit));
  });
  const topCounterparties = Array.from(counterparties.values())
    .map(item => {
      const directionTotal = item.direction === "Debit" ? totalDebitMinor : totalCreditMinor;
      return {
        counterparty: item.name,
        direction: item.direction,
        totalAmount: fromMinorUnits(item.totalMinor),
        transactionCount: item.ids.length,
        sharePercent: directionTotal > 0 ? Math.round((item.totalMinor / directionTotal) * 1000) / 10 : 0,
        transactionIds: item.ids.slice(0, 100)
      };
    })
    .sort((a, b) => b.totalAmount - a.totalAmount)
    .slice(0, 12);

  const recurringGroups = new Map<string, { name: string; direction: "Debit" | "Credit"; amountMinor: number; dates: number[]; ids: string[] }>();
  transactions.forEach(row => {
    const timestamp = parseTransactionDate(row.transactionDate || row.date);
    if (timestamp === null) return;
    (["Debit", "Credit"] as const).forEach(direction => {
      const amountMinor = toMinorUnits(direction === "Debit" ? row.debit : row.credit);
      if (amountMinor <= 0) return;
      const name = counterpartyLabel(row);
      const key = `${direction}|${name}|${amountMinor}`;
      const current = recurringGroups.get(key) || { name, direction, amountMinor, dates: [], ids: [] };
      current.dates.push(timestamp);
      current.ids.push(row.id);
      recurringGroups.set(key, current);
    });
  });
  const recurringPatterns = Array.from(recurringGroups.values())
    .filter(group => group.ids.length >= 3 && new Set(group.dates.map(value => new Date(value).toISOString().slice(0, 7))).size >= 2)
    .map(group => {
      const dates = [...group.dates].sort((a, b) => a - b);
      const gaps = dates.slice(1).map((value, index) => (value - dates[index]) / 86_400_000);
      const typicalGap = quantile(gaps, 0.5);
      const cadence = typicalGap >= 6 && typicalGap <= 8 ? "Weekly" : typicalGap >= 25 && typicalGap <= 35 ? "Monthly" : "Recurring";
      return {
        counterparty: group.name,
        direction: group.direction,
        typicalAmount: fromMinorUnits(group.amountMinor),
        transactionCount: group.ids.length,
        cadence: cadence as "Weekly" | "Monthly" | "Recurring",
        transactionIds: group.ids.slice(0, 100)
      };
    })
    .sort((a, b) => b.transactionCount - a.transactionCount)
    .slice(0, 20);

  const anomalies = new Map<string, AnalysisInsights["anomalies"][number]>();
  const detectAmountAnomalies = (direction: "Debit" | "Credit") => {
    const rows = transactions.filter(row => toMinorUnits(direction === "Debit" ? row.debit : row.credit) > 0);
    if (rows.length < 8) return;
    const amounts = rows.map(row => direction === "Debit" ? row.debit : row.credit);
    const median = quantile(amounts, 0.5);
    const firstQuartile = quantile(amounts, 0.25);
    const thirdQuartile = quantile(amounts, 0.75);
    const threshold = Math.max(thirdQuartile + (thirdQuartile - firstQuartile) * 1.5, median * 3);
    rows.filter(row => (direction === "Debit" ? row.debit : row.credit) > threshold).forEach(row => {
      const amount = direction === "Debit" ? row.debit : row.credit;
      anomalies.set(row.id, {
        transactionId: row.id,
        type: "Unusual Amount",
        severity: amount > threshold * 2 ? "High" : "Medium",
        date: row.transactionDate || row.date,
        description: row.description,
        amount,
        direction,
        reason: `Amount exceeds the robust ${direction.toLowerCase()} threshold of ${threshold.toFixed(2)}.`
      });
    });
  };
  detectAmountAnomalies("Debit");
  detectAmountAnomalies("Credit");

  const upperQuartile = quantile(
    transactions.map(row => Math.max(row.debit || 0, row.credit || 0)).filter(value => value > 0),
    0.75
  );
  transactions
    .filter(row => row.reviewRequired && Math.max(row.debit || 0, row.credit || 0) >= upperQuartile && upperQuartile > 0)
    .forEach(row => {
      if (anomalies.has(row.id)) return;
      const direction = row.debit > 0 ? "Debit" : "Credit";
      anomalies.set(row.id, {
        transactionId: row.id,
        type: "High-value Review",
        severity: "High",
        date: row.transactionDate || row.date,
        description: row.description,
        amount: direction === "Debit" ? row.debit : row.credit,
        direction,
        reason: "High-value transaction remains unresolved in the human review queue."
      });
    });

  const balanceIssue = qualityReport?.issues.find(issue => issue.code === "BALANCE_CONTINUITY");
  balanceIssue?.transactionIds.forEach(id => {
    const row = transactions.find(transaction => transaction.id === id);
    if (!row || anomalies.has(id)) return;
    const direction = row.debit > 0 ? "Debit" : "Credit";
    anomalies.set(id, {
      transactionId: id,
      type: "Balance Discontinuity",
      severity: "High",
      date: row.transactionDate || row.date,
      description: row.description,
      amount: direction === "Debit" ? row.debit : row.credit,
      direction,
      reason: "The running balance does not follow the transaction movement."
    });
  });

  return {
    periodStart: dated[0]?.row.transactionDate || dated[0]?.row.date || null,
    periodEnd: dated[dated.length - 1]?.row.transactionDate || dated[dated.length - 1]?.row.date || null,
    activeMonths: monthlyTrends.length,
    netCashFlow: fromMinorUnits(totalCreditMinor - totalDebitMinor),
    averageMonthlyDebit: monthlyTrends.length ? fromMinorUnits(Math.round(totalDebitMinor / monthlyTrends.length)) : 0,
    averageMonthlyCredit: monthlyTrends.length ? fromMinorUnits(Math.round(totalCreditMinor / monthlyTrends.length)) : 0,
    largestDebit: largestDebitRow ? evidenceTransaction(largestDebitRow, "Debit") : null,
    largestCredit: largestCreditRow ? evidenceTransaction(largestCreditRow, "Credit") : null,
    topCounterpartyConcentrationPercent: topCounterparties[0]?.sharePercent || 0,
    monthlyTrends,
    topCounterparties,
    recurringPatterns,
    anomalies: Array.from(anomalies.values()).sort((a, b) => b.amount - a.amount).slice(0, 50)
  };
}

export function buildDeterministicNarrative(
  transactions: ClassifiedTransaction[],
  insights: AnalysisInsights,
  qualityReport: AnalysisQualityReport
): AnalysisNarrative {
  const currency = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const findings: AnalysisNarrative["findings"] = [];
  findings.push({
    title: insights.netCashFlow >= 0 ? "Positive net cash flow" : "Negative net cash flow",
    body: `Net movement for the analyzed period is ${currency.format(insights.netCashFlow)} across ${insights.activeMonths || 0} active month(s).`,
    severity: insights.netCashFlow >= 0 ? "Positive" : "Review",
    evidenceTransactionIds: [insights.largestDebit?.id, insights.largestCredit?.id].filter((id): id is string => Boolean(id))
  });
  if (insights.topCounterparties[0]) {
    const top = insights.topCounterparties[0];
    findings.push({
      title: "Counterparty concentration",
      body: `${top.counterparty} represents ${top.sharePercent}% of analyzed ${top.direction.toLowerCase()} value.`,
      severity: top.sharePercent >= 40 ? "Review" : "Neutral",
      evidenceTransactionIds: top.transactionIds
    });
  }
  if (insights.recurringPatterns.length > 0) {
    const recurring = insights.recurringPatterns[0];
    findings.push({
      title: "Recurring activity detected",
      body: `${recurring.counterparty} appears ${recurring.transactionCount} times with a ${recurring.cadence.toLowerCase()} pattern around ${currency.format(recurring.typicalAmount)}.`,
      severity: "Neutral",
      evidenceTransactionIds: recurring.transactionIds
    });
  }
  if (insights.anomalies.length > 0) {
    findings.push({
      title: "Transactions require attention",
      body: `${insights.anomalies.length} deterministic anomaly signal(s) were detected; these are review prompts, not fraud conclusions.`,
      severity: "Review",
      evidenceTransactionIds: insights.anomalies.slice(0, 10).map(item => item.transactionId)
    });
  }

  const caveats = ["Insights are derived only from transactions extracted from this statement."];
  if (qualityReport.reviewCount > 0) caveats.push(`${qualityReport.reviewCount} transaction(s) still require human classification.`);
  if (qualityReport.status !== "Passed") caveats.push(`The analysis quality gate is ${qualityReport.status.toLowerCase()}; resolve integrity findings before relying on conclusions.`);

  return {
    generatedBy: "DETERMINISTIC",
    summary: `${transactions.length} transactions were analyzed from ${insights.periodStart || "an unknown start date"} to ${insights.periodEnd || "an unknown end date"}.`,
    findings,
    caveats
  };
}
