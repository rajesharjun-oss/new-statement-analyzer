import { analyzeWithBackend } from './backendService';
import { AnalysisResult } from '../types';

export const analyzeDocument = async (
    file: File,
    bankId: string = "auto",
    onProgress: (msg: string, progress: number) => void
): Promise<AnalysisResult> => {

    onProgress("Uploading to backend...", 10);

    // Call the Python Backend
    const backendResult = await analyzeWithBackend(file, bankId, onProgress);

    // The backend result is ALREADY in the AnalysisResult format (or close to it)
    // We expect the backend to return the exact shape we need.
    // If backend returns extra fields, they will be preserved.

    // Expected Backend Response: { file_id, summary, downloadUrl, transactions }

    const transactions = backendResult.transactions || [];
    const summary = backendResult.summary || {};
    const validationStatus = String(summary.validationStatus || '').toLowerCase();
    const totalsMatch = summary.totalsMatch;
    const noTransactions = transactions.length === 0;

    const reconciliationFailed =
        noTransactions ||
        totalsMatch === false ||
        validationStatus.includes("mismatch") ||
        validationStatus.includes("no transactions extracted");

    const reconciliationWarnings: string[] = [];
    if (reconciliationFailed) {
        if (summary.validationStatus) {
            reconciliationWarnings.push(String(summary.validationStatus));
        } else if (noTransactions) {
            reconciliationWarnings.push("No transactions extracted");
        }
    }

    return {
        transactions: transactions,
        reconciliation_failed: reconciliationFailed,
        reconciliation_warnings: reconciliationWarnings,
        error_indices: [],
        currency: "NGN",
        organizationName: summary.accountName || "Unknown Org",
        bankName: summary.bank || bankId,
        statement_summary: {
            total_debit: summary.statementTotalDebit ?? summary.totalDebit ?? 0,
            total_credit: summary.statementTotalCredit ?? summary.totalCredit ?? 0,
            opening_balance: summary.openingBalance ?? null,
            closing_balance: summary.closingBalance ?? null,
            extracted_total_debit: summary.extractedTotalDebit ?? summary.totalDebit ?? 0,
            extracted_total_credit: summary.extractedTotalCredit ?? summary.totalCredit ?? 0,
        },
        downloadUrl: backendResult.downloadUrl,
        backend_version: backendResult.backend_version,
        stats: {
            total_txns: transactions.length,
            rule_hits: 0,
            memory_hits: 0,
            ai_txns: 0,
            ai_calls: 0,
            human_overrides: 0,
            ai_rate_percent: 0,
            auto_rate_percent: 0
        }
    };
};
