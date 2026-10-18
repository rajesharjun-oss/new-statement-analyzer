/**
 * Backend Service
 * Handles communication with Python FastAPI backend
 */

// Always use relative URLs — Vite proxy routes /analyze and /download to localhost:8000
// This eliminates cross-origin (CORS) issues in development.
const BACKEND_URL = '';
const HEALTH_ATTEMPT_TIMEOUT_MS = 20_000;
const BACKEND_READY_TIMEOUT_MS = 120_000;
const ANALYSIS_TIMEOUT_MS = 5 * 60_000;

const sleep = (milliseconds: number) => new Promise<void>((resolve) => {
    window.setTimeout(resolve, milliseconds);
});

async function backendIsReady(): Promise<boolean> {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), HEALTH_ATTEMPT_TIMEOUT_MS);

    try {
        const response = await fetch(`${BACKEND_URL}/health?t=${Date.now()}`, {
            method: 'GET',
            cache: 'no-store',
            signal: controller.signal,
        });
        return response.ok;
    } catch {
        return false;
    } finally {
        window.clearTimeout(timeoutId);
    }
}

async function waitForBackend(
    onProgress?: (message: string, progress: number) => void
): Promise<void> {
    const deadline = Date.now() + BACKEND_READY_TIMEOUT_MS;
    let attempt = 0;

    while (Date.now() < deadline) {
        onProgress?.(
            attempt === 0 ? 'Checking analysis service...' : 'Starting analysis service...',
            5
        );
        if (await backendIsReady()) return;

        attempt += 1;
        await sleep(Math.min(1_000 * attempt, 5_000));
    }

    throw new Error('The analysis service did not become ready. Please retry in a moment.');
}

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
    await waitForBackend(onProgress);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('bank', bankId); // Changed from 'bank_identifier' to 'bank' to match main.py

    onProgress?.('Uploading statement...', 15);

    const cacheBuster = Date.now();
    const controller = new AbortController();
    const requestTimeoutId = window.setTimeout(() => controller.abort(), ANALYSIS_TIMEOUT_MS);
    const extractionStatusId = window.setTimeout(
        () => onProgress?.('Extracting and reconciling transactions...', 45),
        3_000
    );
    const reportStatusId = window.setTimeout(
        () => onProgress?.('Categorizing transactions and preparing the report...', 80),
        30_000
    );

    let response: Response;
    try {
        response = await fetch(`${BACKEND_URL}/analyze?t=${cacheBuster}`, {
            method: 'POST',
            body: formData,
            signal: controller.signal,
        });
    } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
            throw new Error('Analysis timed out after five minutes. Please retry or choose the bank explicitly.');
        }
        throw new Error('Could not reach the analysis service. Please check your connection and retry.');
    } finally {
        window.clearTimeout(requestTimeoutId);
        window.clearTimeout(extractionStatusId);
        window.clearTimeout(reportStatusId);
    }

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

    onProgress?.('Processing complete', 100);

    return await response.json();
}

export function getDownloadUrl(fileId: string): string {
    return `${BACKEND_URL}/download/${fileId}`;
}
