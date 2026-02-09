import { Transaction } from '../types';
import * as pdfjsLib from 'pdfjs-dist';

// Configure worker for Vite usage
// We'll rely on the user having copied the worker or Vite handling it.
// Alternatively, we can use a CDN for the worker in dev mode.
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;

interface TextItem {
    str: string;
    x: number;
    y: number; // PDF usually has (0,0) at bottom-left
    h: number; // height
    w: number; // width
}

interface Row {
    y: number;
    items: TextItem[];
}

interface ColumnMap {
    debitX: { min: number, max: number } | null;
    creditX: { min: number, max: number } | null;
    balanceX: { min: number, max: number } | null;
}

const Y_TOLERANCE = 5; // pixels
const X_TOLERANCE = 10; // pixels for column alignment

export const extractTransactionsFromPdf = async (arrayBuffer: ArrayBuffer): Promise<Transaction[]> => {
    const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
    const pdf = await loadingTask.promise;
    const allTransactions: Transaction[] = [];

    let currentTransaction: Transaction | null = null;
    // let columnMap: ColumnMap = { debitX: null, creditX: null, balanceX: null }; 
    // We might need to detect mapping per page or globally? Usually global.
    // Let's detect on first page and reuse? Or detect per page.

    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
        const page = await pdf.getPage(pageNum);
        const content = await page.getTextContent();

        // 1. EXTRACT & NORMALIZE ITEMS
        const items: TextItem[] = content.items.map((item: any) => ({
            str: item.str,
            x: item.transform[4],
            y: item.transform[5],
            h: item.height,
            w: item.width
        }));

        // 2. GROUP INTO ROWS
        // Sort: Top to Bottom (Y desc), Left to Right (X asc)
        items.sort((a, b) => {
            if (Math.abs(a.y - b.y) < Y_TOLERANCE) return a.x - b.x;
            return b.y - a.y;
        });

        const rows: Row[] = [];
        if (items.length > 0) {
            let currentRow: Row = { y: items[0].y, items: [items[0]] };
            for (let i = 1; i < items.length; i++) {
                const item = items[i];
                if (Math.abs(item.y - currentRow.y) < Y_TOLERANCE) {
                    currentRow.items.push(item);
                } else {
                    rows.push(currentRow);
                    currentRow = { y: item.y, items: [item] };
                }
            }
            rows.push(currentRow);
        }

        // 3. DETECT COLUMN HEADERS (Per Page)
        // We look for a row containing "Date", "Debit", "Credit", "Balance"
        const pageColMap = detectColumnMap(rows);

        const dateRegex = /^(\d{1,2}[-/\s]*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|[0-1]?\d)[-/\s]*\d{2,4})/i;

        // 4. PROCESS ROWS
        for (const row of rows) {
            const rowText = row.items.map(i => i.str).join(' ').trim();

            // Filter Headers/Footers
            if (isHeaderOrFooter(rowText)) continue;

            // Check for Date (Start of Transaction)
            const match = rowText.match(dateRegex);

            if (match) {
                // New Transaction
                if (currentTransaction) {
                    allTransactions.push(currentTransaction);
                }

                const dateStr = match[1];

                // Text Extraction Logic
                // We need to parse amounts based on X columns if available, or fall back to heuristics
                const parsed = parseRowContent(row, dateStr.length, pageColMap);

                currentTransaction = {
                    date: normalizeDate(dateStr),
                    description: parsed.description,
                    category: "Unallocated",
                    debit: parsed.debit,
                    credit: parsed.credit,
                    balance: parsed.balance,
                    is_reversal: false
                };
            } else {
                // Continuation Line
                if (currentTransaction) {
                    // Avoid merging page numbers
                    if (!isLikelyPageNumber(rowText)) {
                        // Start of description logic:
                        // If the text starts far to the right, it might be a value we missed?
                        // We assume it's description text.
                        currentTransaction.description += " " + rowText;
                    }
                }
            }
        }
    }

    // Push final transaction
    if (currentTransaction) {
        allTransactions.push(currentTransaction);
    }

    return allTransactions;
};

// --- HELPERS ---

const isHeaderOrFooter = (text: string): boolean => {
    const t = text.toUpperCase();
    return (
        t.includes("TRANS. DATE") ||
        t === "DATE" ||
        t === "VALUE DATE" ||
        t.includes("STATEMENT PERIOD") ||
        t.includes("OPENING BALANCE") && !t.includes("|") || // Simple check
        t === "B/F" || t === "C/F" ||
        (t.includes("DEBIT") && t.includes("CREDIT") && t.includes("BALANCE"))
    );
};

const isLikelyPageNumber = (text: string): boolean => {
    return /^Page\s+\d+\s+of\s+\d+$/i.test(text.trim()) || /^\d+\s*\/\s*\d+$/.test(text.trim());
};

const normalizeDate = (raw: string): string => {
    return raw.replace(/\//g, '-').toUpperCase();
};

const detectColumnMap = (rows: Row[]): ColumnMap => {
    const map: ColumnMap = { debitX: null, creditX: null, balanceX: null };

    // Scan first 10 rows for header keywords
    for (let i = 0; i < Math.min(rows.length, 20); i++) {
        const row = rows[i];
        const text = row.items.map(it => it.str).join(' ').toUpperCase();

        if (text.includes("DEBIT") || text.includes("CREDIT") || text.includes("WITHDRAWAL") || text.includes("DEPOSIT")) {
            // This is likely a header row. Let's find specific items.
            row.items.forEach(item => {
                const val = item.str.toUpperCase();
                if (val.includes("DEBIT") || val.includes("WITHDRAWAL")) {
                    map.debitX = { min: item.x - 20, max: item.x + item.w + 20 };
                }
                else if (val.includes("CREDIT") || val.includes("DEPOSIT")) {
                    map.creditX = { min: item.x - 20, max: item.x + item.w + 20 };
                }
                else if (val.includes("BALANCE")) {
                    map.balanceX = { min: item.x - 20, max: item.x + item.w + 20 };
                }
            });
        }
    }
    return map;
};

const parseRowContent = (row: Row, dateLen: number, colMap: ColumnMap) => {
    let descriptionParts: string[] = [];
    let debit = 0;
    let credit = 0;
    let balance = 0;

    // Helper: Clean number string
    const cleanNum = (s: string) => parseFloat(s.replace(/,/g, ''));
    const isNum = (s: string) => !isNaN(cleanNum(s)) && /[\d\.]+/.test(s.replace(/,/g, ''));

    // 1. COLUMN-BASED PARSING (Preferred)
    // If we have detected headers, use them to snap items to columns.
    const hasColumns = colMap.debitX || colMap.creditX || colMap.balanceX;

    if (hasColumns) {
        for (let i = 0; i < row.items.length; i++) {
            const item = row.items[i];
            const valStr = item.str.trim();
            if (!valStr) continue;

            // Skip Date (Item 0 usually, or by regex match if we want to be safe)
            if (i === 0 && /^[\d\w\-\/]+$/.test(valStr)) continue;

            // Check match
            const x = item.x; // Left edge
            // Use mid-point for better alignment check?
            const mid = x + (item.w / 2);

            let assigned = false;

            if (isNum(valStr)) {
                const val = cleanNum(valStr);

                if (colMap.debitX && mid >= colMap.debitX.min && mid <= colMap.debitX.max) {
                    debit = val; assigned = true;
                } else if (colMap.creditX && mid >= colMap.creditX.min && mid <= colMap.creditX.max) {
                    credit = val; assigned = true;
                } else if (colMap.balanceX && mid >= colMap.balanceX.min && mid <= colMap.balanceX.max) {
                    balance = val; assigned = true;
                }
            }

            if (!assigned) {
                // If it's not a number in a value column, it's description
                // But avoid adding the date again if we skipped it
                descriptionParts.push(valStr);
            }
        }
    }
    // 2. HEURISTIC PARSING (Fallback)
    // If no columns detected, assume standard format: Date | Description | ... | Value | Balance
    else {
        // Collect all items except the first (Date)
        const items = row.items.slice(1);
        const numberTokens: number[] = [];

        // Scan from right to left to find numbers (Balance, Amount)
        // This relies on the fact that Description is usuall on the left, Numbers on the right.
        let rightIndex = items.length - 1;
        while (rightIndex >= 0) {
            const txt = items[rightIndex].str.trim();
            if (isNum(txt)) {
                numberTokens.unshift(cleanNum(txt));
                rightIndex--;
            } else {
                // Hit non-number (Description), stop scanning for numbers
                break;
            }
        }

        // Everything to the left of rightIndex is Description
        for (let i = 0; i <= rightIndex; i++) {
            descriptionParts.push(items[i].str.trim());
        }

        // Assign numbers
        if (numberTokens.length >= 2) {
            // [Amount, Balance]
            balance = numberTokens[numberTokens.length - 1]; // Last is Balance
            const amount = numberTokens[numberTokens.length - 2];
            // Guess Debit/Credit? 
            // Default to Debit if we can't tell? Or checks signs?
            // User requested deterministic. 
            // Without headers, we can't deterministically know Dr/Cr.
            // Let's assume Debit for now as it's common for expenses.
            debit = amount;
        } else if (numberTokens.length === 1) {
            balance = numberTokens[0];
        }
    }

    return {
        description: descriptionParts.join(' '),
        debit,
        credit,
        balance
    };
};
