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

    return {
        transactions: transactions,
        reconciliation_failed: summary.totalsMatch === false,
        reconciliation_warnings: summary.totalsMatch === false ? [summary.validationStatus || "Totals mismatch"] : [],
        error_indices: [],
        currency: "NGN",
        organizationName: summary.accountName || "Unknown Org",
        bankName: summary.bank || bankId,
        downloadUrl: backendResult.downloadUrl,
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
