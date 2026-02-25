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
    };
    downloadUrl: string;
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

    const response = await fetch(`${BACKEND_URL}/analyze`, {
        method: 'POST',
        body: formData
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Backend analysis failed');
    }

    if (onProgress) {
        onProgress('Processing complete', 100);
    }

    return await response.json();
}

export function getDownloadUrl(fileId: string): string {
    return `${BACKEND_URL}/download/${fileId}`;
}
