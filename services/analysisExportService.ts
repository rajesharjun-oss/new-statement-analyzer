import { AnalysisNarrative, AnalysisTemplate, ClassifiedTransaction, ReconciliationCheck } from "../types";
import {
  buildDeterministicNarrative,
  calculateAnalysisInsights,
  calculateAnalysisQuality,
  calculateCategorySummary,
  calculateMonthlySummary,
  calculateReconciliation
} from "./analysisRules";
import { sanitizeSpreadsheetText } from "./spreadsheetSecurity";

export { sanitizeSpreadsheetText } from "./spreadsheetSecurity";

export function buildExportWorkbookData({
  transactions,
  template,
  customInstructions,
  reconciliation,
  narrativeOverride
}: {
  transactions: ClassifiedTransaction[];
  template: AnalysisTemplate;
  customInstructions: string;
  reconciliation: ReconciliationCheck;
  narrativeOverride?: AnalysisNarrative;
}) {
  const pageValue = (t: ClassifiedTransaction) => t.pageNumber ?? t.page_number ?? t._page ?? "";
  const extractedTransactions = transactions.map(t => ({
    "Transaction Date": sanitizeSpreadsheetText(t.transactionDate),
    "Value Date": sanitizeSpreadsheetText(t.valueDate || ""),
    Reference: sanitizeSpreadsheetText(t.reference || ""),
    Description: sanitizeSpreadsheetText(t.description),
    "Raw Source Text": sanitizeSpreadsheetText(t.rawText || t.description),
    Debit: t.debit || 0,
    Credit: t.credit || 0,
    Balance: t.balance || 0,
    "Page Number": pageValue(t),
    "Row Number": t.rowNumber ?? "",
    "Source File": sanitizeSpreadsheetText(t.sourceFileName)
  }));

  const classifiedTransactions = transactions.map(t => ({
    "Transaction Date": sanitizeSpreadsheetText(t.transactionDate),
    "Value Date": sanitizeSpreadsheetText(t.valueDate || ""),
    Reference: sanitizeSpreadsheetText(t.reference || ""),
    Description: sanitizeSpreadsheetText(t.description),
    "Raw Source Text": sanitizeSpreadsheetText(t.rawText || t.description),
    Debit: t.debit || 0,
    Credit: t.credit || 0,
    Balance: t.balance || 0,
    Category: sanitizeSpreadsheetText(t.category),
    "Sub-category": sanitizeSpreadsheetText(t.subCategory || ""),
    "Tax Authority": sanitizeSpreadsheetText(t.taxAuthority || ""),
    Confidence: t.confidence,
    "Decision Source": t.decisionSource,
    Reason: sanitizeSpreadsheetText(t.reason),
    "Review Required": t.reviewRequired ? "Yes" : "No",
    "Page Number": pageValue(t),
    "Row Number": t.rowNumber ?? "",
    "Source File": sanitizeSpreadsheetText(t.sourceFileName)
  }));

  const categorySummary = calculateCategorySummary(transactions).map(row => ({
    Category: sanitizeSpreadsheetText(row.category),
    "Debit Total": row.debitTotal,
    "Credit Total": row.creditTotal,
    "Net Movement": row.netMovement,
    "Transaction Count": row.transactionCount
  }));

  const monthlySummary = calculateMonthlySummary(transactions).map(row => ({
    Month: sanitizeSpreadsheetText(row.month),
    Category: sanitizeSpreadsheetText(row.category),
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

  const qualityReport = calculateAnalysisQuality(transactions, reconciliation);
  const analysisQuality = [{
    "Quality Score": qualityReport.score,
    Grade: qualityReport.grade,
    Status: qualityReport.status,
    Transactions: qualityReport.transactionCount,
    "Classification Coverage %": qualityReport.classificationCoveragePercent,
    "High Confidence %": qualityReport.highConfidencePercent,
    "Source Evidence %": qualityReport.sourceEvidencePercent,
    "Review Required": qualityReport.reviewCount,
    "Possible Duplicates": qualityReport.duplicateCount,
    "Missing Descriptions": qualityReport.missingDescriptionCount,
    "Invalid Dates": qualityReport.invalidDateCount,
    "Date Order Anomalies": qualityReport.outOfOrderDateCount,
    "Invalid Amount Directions": qualityReport.invalidAmountDirectionCount,
    "Balance Continuity Issues": qualityReport.balanceContinuityIssueCount
  }];
  const qualityIssues = qualityReport.issues.map(issue => ({
    Severity: issue.severity,
    Code: issue.code,
    Count: issue.count,
    Message: sanitizeSpreadsheetText(issue.message),
    "Transaction IDs": sanitizeSpreadsheetText(issue.transactionIds.join(", "))
  }));
  const insights = calculateAnalysisInsights(transactions, qualityReport);
  const narrative = narrativeOverride || buildDeterministicNarrative(transactions, insights, qualityReport);
  const cashFlowSummary = [{
    "Period Start": sanitizeSpreadsheetText(insights.periodStart || ""),
    "Period End": sanitizeSpreadsheetText(insights.periodEnd || ""),
    "Active Months": insights.activeMonths,
    "Net Cash Flow": insights.netCashFlow,
    "Average Monthly Debit": insights.averageMonthlyDebit,
    "Average Monthly Credit": insights.averageMonthlyCredit,
    "Largest Debit": insights.largestDebit?.amount || 0,
    "Largest Debit Transaction ID": sanitizeSpreadsheetText(insights.largestDebit?.id || ""),
    "Largest Credit": insights.largestCredit?.amount || 0,
    "Largest Credit Transaction ID": sanitizeSpreadsheetText(insights.largestCredit?.id || ""),
    "Top Counterparty Concentration %": insights.topCounterpartyConcentrationPercent
  }];
  const monthlyTrends = insights.monthlyTrends.map(row => ({
    Month: sanitizeSpreadsheetText(row.month),
    "Debit Total": row.debitTotal,
    "Credit Total": row.creditTotal,
    "Net Movement": row.netMovement,
    "Transaction Count": row.transactionCount,
    "Net Change %": row.netChangePercent ?? ""
  }));
  const topCounterparties = insights.topCounterparties.map(row => ({
    Counterparty: sanitizeSpreadsheetText(row.counterparty),
    Direction: row.direction,
    "Total Amount": row.totalAmount,
    "Transaction Count": row.transactionCount,
    "Share %": row.sharePercent,
    "Transaction IDs": sanitizeSpreadsheetText(row.transactionIds.join(", "))
  }));
  const recurringActivity = insights.recurringPatterns.map(row => ({
    Counterparty: sanitizeSpreadsheetText(row.counterparty),
    Direction: row.direction,
    "Typical Amount": row.typicalAmount,
    Occurrences: row.transactionCount,
    Cadence: row.cadence,
    "Transaction IDs": sanitizeSpreadsheetText(row.transactionIds.join(", "))
  }));
  const anomalyReview = insights.anomalies.map(row => ({
    "Transaction ID": sanitizeSpreadsheetText(row.transactionId),
    Type: row.type,
    Severity: row.severity,
    Date: sanitizeSpreadsheetText(row.date),
    Description: sanitizeSpreadsheetText(row.description),
    Amount: row.amount,
    Direction: row.direction,
    Reason: sanitizeSpreadsheetText(row.reason)
  }));
  const narrativeFindings = narrative.findings.map(row => ({
    "Generated By": narrative.generatedBy,
    Title: sanitizeSpreadsheetText(row.title),
    Severity: row.severity,
    Finding: sanitizeSpreadsheetText(row.body),
    "Evidence Transaction IDs": sanitizeSpreadsheetText(row.evidenceTransactionIds.join(", ")),
    Caveats: sanitizeSpreadsheetText(narrative.caveats.join(" "))
  }));

  const rulesUsed = template.categories.map(rule => ({
    "Template Name": sanitizeSpreadsheetText(template.name),
    Scope: template.scope,
    "Custom Instructions": sanitizeSpreadsheetText(customInstructions || template.aiInstructions),
    Category: sanitizeSpreadsheetText(rule.name),
    "Output Label": sanitizeSpreadsheetText(rule.outputLabel),
    "Applies To": rule.appliesTo,
    "Include Keywords": sanitizeSpreadsheetText(rule.includeKeywords.join(", ")),
    "Exclude Keywords": sanitizeSpreadsheetText(rule.excludeKeywords.join(", ")),
    Priority: rule.priority,
    "Date/Time Exported": new Date().toISOString()
  }));

  return {
    extractedTransactions,
    classifiedTransactions,
    categorySummary,
    monthlySummary,
    reviewRequired,
    reconciliationCheck,
    analysisQuality,
    qualityIssues,
    qualityReport,
    cashFlowSummary,
    monthlyTrends,
    topCounterparties,
    recurringActivity,
    anomalyReview,
    narrativeFindings,
    rulesUsed
  };
}

function addSheet(XLSX: typeof import("xlsx"), wb: import("xlsx").WorkBook, name: string, rows: any[]) {
  const ws = XLSX.utils.json_to_sheet(rows.length ? rows : [{}]);
  const width = Object.keys(rows[0] || {}).map(key => ({ wch: Math.min(Math.max(key.length + 4, 14), 55) }));
  ws["!cols"] = width;
  XLSX.utils.book_append_sheet(wb, ws, name);
}

export async function exportAnalysisWorkbook({
  transactions,
  template,
  customInstructions,
  fileName,
  openingBalance,
  closingBalance,
  narrative
}: {
  transactions: ClassifiedTransaction[];
  template: AnalysisTemplate;
  customInstructions: string;
  fileName: string;
  openingBalance?: number | null;
  closingBalance?: number | null;
  narrative?: AnalysisNarrative;
}) {
  const XLSX = await import("xlsx");
  const reconciliation = calculateReconciliation(transactions, openingBalance, closingBalance);
  const data = buildExportWorkbookData({ transactions, template, customInstructions, reconciliation, narrativeOverride: narrative });
  const wb = XLSX.utils.book_new();
  addSheet(XLSX, wb, "Extracted Transactions", data.extractedTransactions);
  addSheet(XLSX, wb, "Classified Transactions", data.classifiedTransactions);
  addSheet(XLSX, wb, "Category Summary", data.categorySummary);
  addSheet(XLSX, wb, "Monthly Summary", data.monthlySummary);
  addSheet(XLSX, wb, "Review Required", data.reviewRequired);
  addSheet(XLSX, wb, "Reconciliation Check", data.reconciliationCheck);
  addSheet(XLSX, wb, "Analysis Quality", data.analysisQuality);
  addSheet(XLSX, wb, "Quality Issues", data.qualityIssues);
  addSheet(XLSX, wb, "Cash Flow Summary", data.cashFlowSummary);
  addSheet(XLSX, wb, "Monthly Trends", data.monthlyTrends);
  addSheet(XLSX, wb, "Top Counterparties", data.topCounterparties);
  addSheet(XLSX, wb, "Recurring Activity", data.recurringActivity);
  addSheet(XLSX, wb, "Anomaly Review", data.anomalyReview);
  addSheet(XLSX, wb, "Analysis Narrative", data.narrativeFindings);
  addSheet(XLSX, wb, "Rules Used", data.rulesUsed);
  XLSX.writeFile(wb, fileName.endsWith(".xlsx") ? fileName : `${fileName}.xlsx`);
}
