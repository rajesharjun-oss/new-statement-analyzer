import * as XLSX_PKG from 'xlsx';
import { Transaction } from '../types';

// Handle ESM/CJS interop: checks if 'utils' is available on the namespace, otherwise falls back to default export
// This fixes "Cannot read properties of undefined (reading 'book_new')"
const XLSX = (XLSX_PKG as any).utils ? XLSX_PKG : (XLSX_PKG as any).default;

export const generateExcel = (
  transactions: Transaction[], 
  warnings: string[], 
  reconciliationFailed: boolean, 
  currency: string,
  organizationName: string,
  bankName: string
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
        const cell_address = XLSX.utils.encode_cell({r: R, c: C});
        if (!ws[cell_address]) continue;
        
        // Add style property if it doesn't exist
        if (!ws[cell_address].s) ws[cell_address].s = {};
        
        ws[cell_address].s.border = borderStyle;
      }
    }
  };

  // 1. Transactions Sheet
  const tableData = transactions.map(t => ({
    Date: t.date,
    Description: t.description,
    Category: t.category,
    Reference: t.reference || '',
    Debit: t.debit || 0,
    Credit: t.credit || 0,
    Balance: t.balance || 0
  }));

  const wsTransactions = XLSX.utils.json_to_sheet(tableData);
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
    if (t.debit > 0) {
      expenseSummary[t.category] = (expenseSummary[t.category] || 0) + t.debit;
    }
    if (t.credit > 0) {
      incomeSummary[t.category] = (incomeSummary[t.category] || 0) + t.credit;
    }
  });

  const summaryData = [
    ["Report Metadata", ""],
    ["Organization", organizationName],
    ["Bank", bankName],
    ["Analysis Date", new Date().toISOString().split('T')[0]],
    [""], // Spacer
    ["Reconciliation Status", reconciliationFailed ? "FAILED" : "PASSED"],
    ["Warnings", (warnings || []).join("; ") || "None"],
    ["Currency", currency],
    [""], // Spacer
    ["Metric", "Value"],
    ["Opening Balance (Calc)", openingBalance],
    ["Closing Balance", closingBalance],
    ["Total Debits", totalDebit],
    ["Total Credits", totalCredit],
    [""], // Spacer
    ["Income by Category", "Amount"],
    ...Object.entries(incomeSummary).map(([cat, val]) => [cat, val]),
    [""], // Spacer
    ["Expenses by Category", "Amount"],
    ...Object.entries(expenseSummary).map(([cat, val]) => [cat, val])
  ];

  const wsSummary = XLSX.utils.aoa_to_sheet(summaryData);
  applyBorders(wsSummary);
  XLSX.utils.book_append_sheet(wb, wsSummary, "Summary");

  // Generate Filename
  const sanitize = (str: string) => str.replace(/[^a-z0-9]/gi, '_').replace(/_+/g, '_');
  const filename = `${sanitize(organizationName)}_${sanitize(bankName)}_Statement.xlsx`;

  // Write file
  XLSX.writeFile(wb, filename);
};