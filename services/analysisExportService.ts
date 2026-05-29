import * as XLSX_PKG from "xlsx";
import { AnalysisTemplate, ClassifiedTransaction, ReconciliationCheck } from "../types";
import { calculateCategorySummary, calculateMonthlySummary, calculateReconciliation } from "./analysisRules";

const XLSX = XLSX_PKG;

export function buildExportWorkbookData({
  transactions,
  template,
  customInstructions,
  reconciliation
}: {
  transactions: ClassifiedTransaction[];
  template: AnalysisTemplate;
  customInstructions: string;
  reconciliation: ReconciliationCheck;
}) {
  const pageValue = (t: ClassifiedTransaction) => t.pageNumber ?? t.page_number ?? t._page ?? "";
  const extractedTransactions = transactions.map(t => ({
    "Transaction Date": t.transactionDate,
    "Value Date": t.valueDate || "",
    Reference: t.reference || "",
    Description: t.description,
    Debit: t.debit || 0,
    Credit: t.credit || 0,
    Balance: t.balance || 0,
    "Page Number": pageValue(t),
    "Source File": t.sourceFileName
  }));

  const classifiedTransactions = transactions.map(t => ({
    "Transaction Date": t.transactionDate,
    "Value Date": t.valueDate || "",
    Reference: t.reference || "",
    Description: t.description,
    Debit: t.debit || 0,
    Credit: t.credit || 0,
    Balance: t.balance || 0,
    Category: t.category,
    "Sub-category": t.subCategory || "",
    "Tax Authority": t.taxAuthority || "",
    Confidence: t.confidence,
    "Decision Source": t.decisionSource,
    Reason: t.reason,
    "Review Required": t.reviewRequired ? "Yes" : "No",
    "Page Number": pageValue(t),
    "Source File": t.sourceFileName
  }));

  const categorySummary = calculateCategorySummary(transactions).map(row => ({
    Category: row.category,
    "Debit Total": row.debitTotal,
    "Credit Total": row.creditTotal,
    "Net Movement": row.netMovement,
    "Transaction Count": row.transactionCount
  }));

  const monthlySummary = calculateMonthlySummary(transactions).map(row => ({
    Month: row.month,
    Category: row.category,
    "Debit Total": row.debitTotal,
    "Credit Total": row.creditTotal,
    "Net Movement": row.netMovement,
    "Transaction Count": row.transactionCount
  }));

  const reviewRequired = classifiedTransactions.filter((_, idx) => {
    const t = transactions[idx];
    return t.reviewRequired || t.confidence === "Low";
  });

  const reconciliationCheck = [{
    "Opening Balance": reconciliation.openingBalance ?? "",
    "Total Debit": reconciliation.totalDebit,
    "Total Credit": reconciliation.totalCredit,
    "Expected Closing Balance": reconciliation.expectedClosingBalance ?? "",
    "Actual Closing Balance": reconciliation.actualClosingBalance ?? "",
    Difference: reconciliation.difference ?? "",
    Status: reconciliation.status
  }];

  const rulesUsed = template.categories.map(rule => ({
    "Template Name": template.name,
    Scope: template.scope,
    "Custom Instructions": customInstructions || template.aiInstructions,
    Category: rule.name,
    "Output Label": rule.outputLabel,
    "Applies To": rule.appliesTo,
    "Include Keywords": rule.includeKeywords.join(", "),
    "Exclude Keywords": rule.excludeKeywords.join(", "),
    Priority: rule.priority,
    "Date/Time Exported": new Date().toISOString()
  }));

  return { extractedTransactions, classifiedTransactions, categorySummary, monthlySummary, reviewRequired, reconciliationCheck, rulesUsed };
}

function addSheet(wb: XLSX_PKG.WorkBook, name: string, rows: any[]) {
  const ws = XLSX.utils.json_to_sheet(rows.length ? rows : [{}]);
  const width = Object.keys(rows[0] || {}).map(key => ({ wch: Math.min(Math.max(key.length + 4, 14), 55) }));
  ws["!cols"] = width;
  XLSX.utils.book_append_sheet(wb, ws, name);
}

export function exportAnalysisWorkbook({
  transactions,
  template,
  customInstructions,
  fileName,
  openingBalance,
  closingBalance
}: {
  transactions: ClassifiedTransaction[];
  template: AnalysisTemplate;
  customInstructions: string;
  fileName: string;
  openingBalance?: number | null;
  closingBalance?: number | null;
}) {
  const reconciliation = calculateReconciliation(transactions, openingBalance, closingBalance);
  const data = buildExportWorkbookData({ transactions, template, customInstructions, reconciliation });
  const wb = XLSX.utils.book_new();
  addSheet(wb, "Extracted Transactions", data.extractedTransactions);
  addSheet(wb, "Classified Transactions", data.classifiedTransactions);
  addSheet(wb, "Category Summary", data.categorySummary);
  addSheet(wb, "Monthly Summary", data.monthlySummary);
  addSheet(wb, "Review Required", data.reviewRequired);
  addSheet(wb, "Reconciliation Check", data.reconciliationCheck);
  addSheet(wb, "Rules Used", data.rulesUsed);
  XLSX.writeFile(wb, fileName.endsWith(".xlsx") ? fileName : `${fileName}.xlsx`);
}
