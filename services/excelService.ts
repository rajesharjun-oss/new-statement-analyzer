
import * as XLSX_PKG from 'xlsx';
import { Transaction } from '../types';

// Handle ESM/CJS interop
const XLSX = (XLSX_PKG as any).utils ? XLSX_PKG : (XLSX_PKG as any).default;

export const generateExcel = (
  transactions: Transaction[],
  warnings: string[],
  reconciliationFailed: boolean,
  currency: string,
  organizationName: string,
  bankName: string,
  fileNameOverride?: string
) => {
  const wb = XLSX.utils.book_new();

  // Define Border Style
  const borderStyle = {
    top: { style: "thin" },
    bottom: { style: "thin" },
    left: { style: "thin" },
    right: { style: "thin" }
  };

  const applyBorders = (ws: any) => {
    if (!ws['!ref']) return;
    const range = XLSX.utils.decode_range(ws['!ref']);
    for (let R = range.s.r; R <= range.e.r; ++R) {
      for (let C = range.s.c; C <= range.e.c; ++C) {
        const cell_address = XLSX.utils.encode_cell({ r: R, c: C });
        if (!ws[cell_address]) continue;
        if (!ws[cell_address].s) ws[cell_address].s = {};
        ws[cell_address].s.border = borderStyle;
      }
    }
  };

  // 1. Transactions Sheet
  const tableData = transactions.map(t => {
    let notes = t.decision_source || "";
    if (t.ruleId) notes += ` (${t.ruleId})`;
    if (t.is_reversal) notes = `[REVERSAL] ${notes}`;

    return {
      Date: t.date,
      Description: t.description,
      Category: t.category,
      Debit: t.debit || 0,
      Credit: t.credit || 0,
      Balance: t.balance || 0,
      Notes: notes
    };
  });

  const wsTransactions = XLSX.utils.json_to_sheet(tableData);

  // Set column widths for better readability
  wsTransactions['!cols'] = [
    { wch: 12 }, // Date
    { wch: 50 }, // Description
    { wch: 25 }, // Category
    { wch: 12 }, // Debit
    { wch: 12 }, // Credit
    { wch: 15 }, // Balance
    { wch: 25 }  // Notes
  ];

  applyBorders(wsTransactions);
  XLSX.utils.book_append_sheet(wb, wsTransactions, "Transactions");

  // 2. Summary Sheet
  const totalDebit = transactions.reduce((sum, t) => sum + (t.debit || 0), 0);
  const totalCredit = transactions.reduce((sum, t) => sum + (t.credit || 0), 0);
  const openingBalance = transactions.length > 0 ? (transactions[0].balance + (transactions[0].debit || 0) - (transactions[0].credit || 0)) : 0;
  const closingBalance = transactions.length > 0 ? transactions[transactions.length - 1].balance : 0;

  // Pivot Category Data
  const expenseSummary: Record<string, number> = {};
  const incomeSummary: Record<string, number> = {};

  transactions.forEach(t => {
    if ((t.debit || 0) !== 0) {
      expenseSummary[t.category] = (expenseSummary[t.category] || 0) + t.debit;
    }
    if ((t.credit || 0) !== 0) {
      incomeSummary[t.category] = (incomeSummary[t.category] || 0) + t.credit;
    }
  });

  const summaryData = [
    ["Report Metadata", ""],
    ["Organization", organizationName],
    ["Bank", bankName],
    ["Analysis Date", new Date().toISOString().split('T')[0]],
    [""],
    ["Reconciliation Status", reconciliationFailed ? "FAILED" : "PASSED"],
    ["Warnings", (warnings || []).join("; ") || "None"],
    ["Currency", currency],
    [""],
    ["Metric", "Value"],
    ["Opening Balance (Calc)", openingBalance],
    ["Closing Balance", closingBalance],
    ["Total Debits", totalDebit],
    ["Total Credits", totalCredit],
    [""],
    ["Income by Category", "Amount"],
    ...Object.entries(incomeSummary).map(([cat, val]) => [cat, val]),
    [""],
    ["Expenses by Category", "Amount"],
    ...Object.entries(expenseSummary).map(([cat, val]) => [cat, val])
  ];

  const wsSummary = XLSX.utils.aoa_to_sheet(summaryData);
  applyBorders(wsSummary);
  XLSX.utils.book_append_sheet(wb, wsSummary, "Summary");

  // Generate Filename
  const sanitize = (str: string) => str.replace(/[^a-z0-9]/gi, '_').replace(/_+/g, '_');
  const defaultFilename = `${sanitize(organizationName)}_${sanitize(bankName)}_Statement.xlsx`;
  let filename = (fileNameOverride || "").trim() || defaultFilename;
  if (!filename.toLowerCase().endsWith(".xlsx")) {
    filename = `${filename}.xlsx`;
  }

  // Write file
  XLSX.writeFile(wb, filename);
};
