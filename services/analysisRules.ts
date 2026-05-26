import { AnalysisTemplate, ClassifiedTransaction, ConfidenceLabel, ReconciliationCheck, Transaction } from "../types";

const reviewCategory = "Review Required";
const highNoise = ["opening balance", "closing balance", "balance brought forward", "stamp duty", "sms", "vat on bank", "account maintenance", "charge", "reversal", "reversed"];

function money(value: unknown): number {
  const n = typeof value === "number" ? value : Number(String(value ?? "0").replace(/,/g, ""));
  return Number.isFinite(n) ? n : 0;
}

function tokenizeKeywords(value: string): string[] {
  return value.split(",").map(k => k.trim()).filter(Boolean);
}

export function normalizeTransactions(transactions: Transaction[], sourceFileName: string): ClassifiedTransaction[] {
  return transactions.map((t, index) => ({
    ...t,
    id: t.id || `txn-${index + 1}`,
    sourceFileName,
    rowNumber: t.rowNumber ?? index + 1,
    transactionDate: t.transactionDate || t.date,
    valueDate: t.valueDate,
    reference: t.reference || "",
    description: t.description || "",
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
  }));
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

function includesAny(text: string, keywords: string[]) {
  return keywords.some(keyword => {
    const k = keyword.toLowerCase().trim();
    if (!k) return false;
    return text.includes(k);
  });
}

function inferIndividualName(text: string) {
  if (includesAny(text, ["ltd", "limited", "plc", "company", "enterprise", "ventures", "services"])) return false;
  const tokens = text.replace(/[^a-z\s]/g, " ").split(/\s+/).filter(Boolean);
  return tokens.length >= 2 && tokens.some(t => t.length > 3) && !includesAny(text, highNoise);
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

  const text = `${transaction.description} ${transaction.reference || ""}`.toLowerCase();
  const rules = [...template.categories].sort((a, b) => b.priority - a.priority);

  for (const rule of rules) {
    if (!appliesToScope(transaction, rule.appliesTo)) continue;
    const include = rule.includeKeywords.length === 0 || includesAny(text, rule.includeKeywords);
    const exclude = rule.excludeKeywords.length > 0 && includesAny(text, rule.excludeKeywords);
    if (include && !exclude && rule.includeKeywords.length > 0) {
      const taxAuthority = template.id === "firs-sirs-na"
        ? (rule.outputLabel === "FIRS" || rule.outputLabel === "SIRS" || rule.outputLabel === "Not Applicable" ? rule.outputLabel : null)
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

  if (template.id === "firs-sirs-na" && inferIndividualName(text) && transaction.debit > 0) {
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
