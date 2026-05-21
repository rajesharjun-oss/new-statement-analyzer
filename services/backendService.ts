/**
 * Backend Service
 * Handles communication with Python FastAPI backend
 */

// Always use relative URLs — Vite proxy routes /analyze and /download to localhost:8000
// This eliminates cross-origin (CORS) issues in development.
const BACKEND_URL = '';

export interface BackendAnalysisResult {
    summary: {
        accountName: string;
        period: string;
        totalDebit: number;
        totalCredit: number;
        transactionCount: number;
        validationStatus: string;
        totalsMatch?: boolean | null;
        statementTotalDebit?: number | null;
        statementTotalCredit?: number | null;
        extractedTotalDebit?: number | null;
        extractedTotalCredit?: number | null;
        openingBalance?: number | null;
        closingBalance?: number | null;
        bank?: string;
    };
    downloadUrl: string;
    transactions?: any[];
    backend_version?: string;
}

export async function analyzeWithBackend(
    file: File,
    bankId: string = "auto",
    onProgress?: (message: string, progress: number) => void
): Promise<BackendAnalysisResult> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('bank', bankId); // Changed from 'bank_identifier' to 'bank' to match main.py

    if (onProgress) {
        onProgress('Uploading to backend...', 10);
    }

    const cacheBuster = Date.now();
    const response = await fetch(`${BACKEND_URL}/analyze?t=${cacheBuster}`, {
        method: 'POST',
        body: formData
    });

    if (!response.ok) {
        // Backend may return plain text on 500 — safely handle both JSON and text error bodies
        let errorMessage = `Backend error (HTTP ${response.status})`;
        try {
            const errorBody = await response.json();
            errorMessage = errorBody.detail || errorMessage;
        } catch {
            try {
                const textBody = await response.text();
                if (textBody) errorMessage = textBody.slice(0, 200);
            } catch { /* ignore */ }
        }
        throw new Error(errorMessage);
    }

    if (onProgress) {
        onProgress('Processing complete', 100);
    }

    return await response.json();
}

export function getDownloadUrl(fileId: string): string {
    return `${BACKEND_URL}/download/${fileId}`;
}
