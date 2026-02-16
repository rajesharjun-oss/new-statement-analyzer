import * as pdfjsLibProxy from 'pdfjs-dist';
import { GoogleGenAI, Type } from "@google/genai";
import { AnalysisResult, Transaction, AnalysisStatistics } from "../types";
import { categorizeTransaction } from "./categorizationRules";

// Handle ESM default export structure if necessary
const pdfjsLib = (pdfjsLibProxy as any).default || pdfjsLibProxy;

// Initialize PDF.js worker
if (pdfjsLib.GlobalWorkerOptions) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}

const DATE_REGEX = /(?:\b\d{1,2}[-/\.\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{1,2})[-/\.\s](?:\d{2,4})\b)|(?:\b\d{4}[-/\.\s]\d{1,2}[-/\.\s]\d{1,2}\b)/i;

// --- TYPE DEFINITIONS FOR PARSING ---
interface TextItem {
    str: string;
    x: number;
    y: number;
    width: number;
    height: number;
}

interface LayoutZones {
    date: { min: number, max: number };
    debit: { min: number, max: number };
    credit: { min: number, max: number };
    balance: { min: number, max: number };
    mode: '3_COL' | '2_COL' | 'UNKNOWN';
}

// --- HELPER: GEMINI AI EXTRACTION (FALLBACK) ---
const extractWithGemini = async (
    base64Data: string,
    mimeType: string,
    apiKey: string
): Promise<Transaction[]> => {
    try {
        const ai = new GoogleGenAI({ apiKey });
        const model = "gemini-2.5-flash";

        const prompt = `
        You are a specialized financial OCR engine. Extract all bank transactions from this bank statement.
        
        CRITICAL RULES:
        1. Ignore "Balance Brought Forward" or "Opening Balance" rows unless they are the very first row.
        2. Ignore page totals, summaries, and headers.
        3. If a row has no date, strictly inherit the date from the previous row.
        4. Return raw numbers (e.g. 1500.00), do not include currency symbols.
        5. Return a JSON array.
        `;

        const response = await ai.models.generateContent({
            model: model,
            contents: {
                parts: [
                    { inlineData: { mimeType, data: base64Data } },
                    { text: prompt }
                ]
            },
            config: {
                responseMimeType: "application/json",
                responseSchema: {
                    type: Type.ARRAY,
                    items: {
                        type: Type.OBJECT,
                        properties: {
                            date: { type: Type.STRING, description: "Format: DD-MMM-YYYY or YYYY-MM-DD" },
                            description: { type: Type.STRING },
                            debit: { type: Type.NUMBER },
                            credit: { type: Type.NUMBER },
                            balance: { type: Type.NUMBER }
                        }
                    }
                }
            }
        });

        const text = response.text || "[]";
        // Clean potential markdown formatting
        const cleanText = text.replace(/```json/g, '').replace(/```/g, '').trim();
        const raw = JSON.parse(cleanText);

        return raw.map((r: any) => ({
            date: r.date,
            description: r.description,
            debit: r.debit || 0,
            credit: r.credit || 0,
            balance: r.balance || 0,
            category: "Unallocated",
            decision_source: "AI",
            confidence: 0.95
        }));
    } catch (e) {
        console.error("Gemini Extraction Failed", e);
        return [];
    }
};

// --- HELPER: GEMINI CATEGORIZATION ---
const enhanceTransactionsWithAI = async (
    transactions: Transaction[],
    apiKey: string
): Promise<Transaction[]> => {
    const unallocated = transactions.filter(t => t.category === "Unallocated" || t.category === "Review Required");

    if (unallocated.length === 0) return transactions;

    const sampleSize = Math.min(unallocated.length, 50);
    const sample = unallocated.slice(0, sampleSize);

    const descriptionsMap = new Map<string, string>();

    try {
        const ai = new GoogleGenAI({ apiKey });
        const model = "gemini-2.5-flash";

        const prompt = `
      Categorize these bank transactions into: [Bank Charges, Operating Income, Office Rent, Transport, Repairs, Staff Welfare, Salaries, Loans, Unallocated].
      Return JSON: [{"d": "substring_of_description", "c": "Category"}]
      
      Transactions:
      ${sample.map(t => `- ${t.description} (${t.debit > 0 ? 'DR ' + t.debit : 'CR ' + t.credit})`).join('\n')}
    `;

        const response = await ai.models.generateContent({
            model: model,
            contents: prompt,
            config: {
                responseMimeType: "application/json",
                responseSchema: {
                    type: Type.ARRAY,
                    items: {
                        type: Type.OBJECT,
                        properties: {
                            d: { type: Type.STRING },
                            c: { type: Type.STRING }
                        }
                    }
                }
            }
        });

        const text = response.text || "[]";
        const cleanText = text.replace(/```json/g, '').replace(/```/g, '').trim();
        const results = JSON.parse(cleanText);

        results.forEach((r: any) => {
            if (r.d && r.c) descriptionsMap.set(r.d, r.c);
        });

    } catch (e) {
        console.warn("AI Categorization failed", e);
    }

    return transactions.map(t => {
        if (t.category === "Unallocated" || t.category === "Review Required") {
            for (const [descKey, catVal] of descriptionsMap.entries()) {
                if (t.description.includes(descKey)) {
                    return { ...t, category: catVal, decision_source: 'AI', confidence: 0.85 };
                }
            }
        }
        return t;
    });
};

// --- CORE: DETERMINISTIC PARSING ---

const getPageTextItems = async (doc: any, pageNum: number): Promise<TextItem[]> => {
    const page = await doc.getPage(pageNum);
    const textContent = await page.getTextContent();

    return textContent.items.map((item: any) => ({
        str: item.str,
        x: item.transform[4],
        y: item.transform[5],
        width: item.width,
        height: item.height
    }));
};

const parseAmount = (str: string): number => {
    if (!str) return 0;
    let clean = str.replace(/\s+/g, '').replace(/,/g, '');
    if (clean.endsWith('-')) clean = '-' + clean.slice(0, -1);
    else if (clean.startsWith('(') && clean.endsWith(')')) clean = '-' + clean.slice(1, -1);
    clean = clean.replace(/dr$|cr$/i, '');
    const dotCount = (clean.match(/\./g) || []).length;
    if (dotCount > 1) clean = clean.replace(/\.(?=.*\.)/g, '');
    const val = parseFloat(clean);
    return isNaN(val) ? 0 : val;
};

const isMoneyString = (str: string): boolean => {
    const clean = str.replace(/[,\s]/g, '');
    return /^-?\(?\d+(:?\.\d+)?\)?(?:[DC]R)?$/i.test(clean) && clean.length > 0;
};

const findClusters = (values: number[], tolerance: number = 20) => {
    if (values.length === 0) return [];
    values.sort((a, b) => a - b);
    const clusters: { center: number, count: number, sum: number }[] = [];
    for (const v of values) {
        let found = false;
        for (const c of clusters) {
            if (Math.abs(c.center - v) <= tolerance) {
                c.sum += v;
                c.count++;
                c.center = c.sum / c.count;
                found = true;
                break;
            }
        }
        if (!found) clusters.push({ center: v, count: 1, sum: v });
    }
    return clusters.sort((a, b) => b.count - a.count);
};

export const analyzeBankStatement = async (
    base64Data: string,
    mimeType: string,
    customApiKey?: string,
    onProgress?: (current: number, total: number) => void
): Promise<AnalysisResult> => {

    const globalStats: AnalysisStatistics = {
        total_txns: 0, rule_hits: 0, memory_hits: 0, ai_txns: 0, ai_calls: 0, human_overrides: 0, ai_rate_percent: 0, auto_rate_percent: 0
    };

    try {
        const binaryString = atob(base64Data);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) bytes[i] = binaryString.charCodeAt(i);

        const pdf = await pdfjsLib.getDocument({ data: bytes }).promise;
        const totalPages = pdf.numPages;

        let allTransactions: Transaction[] = [];
        let metadata = { org: "Detected Organization", bank: "Detected Bank" };
        let layoutFailed = true;

        // --- PHASE 1: DETERMINISTIC LAYOUT DETECTION ---
        const dateXs: number[] = [];
        const moneyXs: number[] = [];
        const scanLimit = Math.min(totalPages, 5);

        for (let i = 1; i <= scanLimit; i++) {
            const items = await getPageTextItems(pdf, i);
            if (i === 1) {
                const fullText = items.map(t => t.str).join(' ');
                const knownBanks = ['GTBank', 'Zenith', 'Access', 'First Bank', 'UBA', 'Fidelity', 'Stanbic', 'Kuda', 'Opay'];
                for (const b of knownBanks) {
                    if (new RegExp(b, 'i').test(fullText)) { metadata.bank = b; break; }
                }
            }
            items.forEach(item => {
                if (DATE_REGEX.test(item.str)) dateXs.push(item.x);
                else if (/[\d,]+\.\d{2}|^\d{4,}$/.test(item.str.trim())) moneyXs.push(item.x);
            });
        }

        const dateClusters = findClusters(dateXs, 40);

        // --- DETERMINISTIC EXECUTION ---
        if (dateClusters.length > 0) {
            const dateX = dateClusters[0].center;
            const dateRange = { min: dateX - 30, max: dateX + 80 };

            const validMoneyXs = moneyXs.filter(x => x > dateRange.max);
            const moneyClusters = findClusters(validMoneyXs, 30);
            const sortedCols = moneyClusters.filter(c => c.count > Math.max(3, scanLimit)).sort((a, b) => a.center - b.center);

            const zones: LayoutZones = {
                date: dateRange,
                debit: { min: 0, max: 0 },
                credit: { min: 0, max: 0 },
                balance: { min: 0, max: 0 },
                mode: 'UNKNOWN'
            };

            const getZone = (center: number) => ({ min: center - 40, max: center + 50 });

            if (sortedCols.length >= 3) {
                zones.mode = '3_COL';
                zones.debit = getZone(sortedCols[sortedCols.length - 3].center);
                zones.credit = getZone(sortedCols[sortedCols.length - 2].center);
                zones.balance = getZone(sortedCols[sortedCols.length - 1].center);
            } else if (sortedCols.length === 2) {
                zones.mode = '2_COL';
                zones.debit = getZone(sortedCols[0].center);
                zones.balance = getZone(sortedCols[1].center);
            }

            // Only proceed with row parsing if we identified a valid layout
            if (zones.mode !== 'UNKNOWN') {
                layoutFailed = false;

                for (let i = 1; i <= totalPages; i++) {
                    if (onProgress) onProgress(i, totalPages);
                    const items = await getPageTextItems(pdf, i);

                    const rows: TextItem[][] = [];
                    let currentRow: TextItem[] = [];
                    const sortedItems = items.sort((a, b) => b.y - a.y);
                    let lastY = -1;

                    for (const item of sortedItems) {
                        if (lastY === -1 || Math.abs(item.y - lastY) < 6) currentRow.push(item);
                        else {
                            rows.push(currentRow.sort((a, b) => a.x - b.x));
                            currentRow = [item];
                        }
                        lastY = item.y;
                    }
                    if (currentRow.length) rows.push(currentRow.sort((a, b) => a.x - b.x));

                    let pendingTransaction: Partial<Transaction> | null = null;
                    let lastDate = "";

                    for (const row of rows) {
                        const rowText = row.map(i => i.str).join(' ');
                        if (/^(DATE|TRANS|VALUE|DETAILS|DESCRIPTION|PARTICULARS|DEBIT|CREDIT|BALANCE)$/i.test(rowText)) continue;
                        if (/PAGE\s+\d+|CONTINUED/i.test(rowText)) continue;
                        if (/TOTAL|TURNOVER|SUMMARY/i.test(rowText) && !/OPENING/i.test(rowText)) continue;
                        if (/BALANCE\s+(BROUGHT|CARRIED)\s+FORWARD|B\/F|C\/F/i.test(rowText) && allTransactions.length > 0) continue;

                        const dateItem = row.find(item => item.x >= zones.date.min && item.x <= zones.date.max && DATE_REGEX.test(item.str));
                        const isInZone = (item: TextItem, zone: { min: number, max: number }) => item.x >= zone.min && item.x <= zone.max;

                        const debitItem = row.find(item => isInZone(item, zones.debit) && isMoneyString(item.str));
                        const creditItem = row.find(item => isInZone(item, zones.credit) && isMoneyString(item.str));
                        const balanceItem = row.find(item => isInZone(item, zones.balance) && isMoneyString(item.str));

                        const descItems = row.filter(item =>
                            item !== dateItem && item !== debitItem && item !== creditItem && item !== balanceItem &&
                            item.x > zones.date.max &&
                            item.x < (zones.debit.min > 0 ? zones.debit.min : zones.balance.min)
                        );
                        const descStr = descItems.map(i => i.str).join(' ').trim();

                        if (dateItem) {
                            if (pendingTransaction) allTransactions.push(pendingTransaction as Transaction);
                            lastDate = dateItem.str;
                            pendingTransaction = {
                                date: dateItem.str,
                                description: descStr,
                                debit: parseAmount(debitItem?.str || ""),
                                credit: parseAmount(creditItem?.str || ""),
                                balance: parseAmount(balanceItem?.str || ""),
                                category: "Unallocated"
                            };
                        } else {
                            const hasActiveFinancials = (debitItem || creditItem);
                            if (hasActiveFinancials && lastDate) {
                                if (pendingTransaction) allTransactions.push(pendingTransaction as Transaction);
                                pendingTransaction = {
                                    date: lastDate,
                                    description: descStr,
                                    debit: parseAmount(debitItem?.str || ""),
                                    credit: parseAmount(creditItem?.str || ""),
                                    balance: parseAmount(balanceItem?.str || ""),
                                    category: "Unallocated"
                                };
                            } else if (pendingTransaction && descStr.length > 0 && !/Page\s+\d+/i.test(descStr)) {
                                pendingTransaction.description += " " + descStr;
                            }
                        }
                    }
                    if (pendingTransaction) allTransactions.push(pendingTransaction as Transaction);
                }
            }
        }

        // --- PHASE 2: FALLBACK TO GEMINI (IF DETERMINISTIC FAILED) ---
        // Trigger if: 0 transactions found OR layout detection explicitly failed.
        if ((allTransactions.length === 0 || layoutFailed) && customApiKey) {
            console.log("Deterministic parsing failed or yielded 0 results. Switching to Gemini 2.5 Flash Fallback.");
            allTransactions = []; // Clear any partial garbage
            allTransactions = await extractWithGemini(base64Data, mimeType, customApiKey);
        }

        // --- POST PROCESSING ---
        let processed = allTransactions.map(t => categorizeTransaction(t));

        if (customApiKey) {
            processed = await enhanceTransactionsWithAI(processed, customApiKey);
        }

        // Reconciliation Validation
        const warnings: string[] = [];
        const errorIndices: number[] = [];
        let failed = false;

        processed.forEach((t, i) => {
            if (i === 0) return;
            const prev = processed[i - 1];
            if (Math.abs(prev.balance) < 0.01 && Math.abs(t.balance) < 0.01) return;

            const expectedBalance = Math.round((prev.balance + t.credit - t.debit) * 100) / 100;
            const actualBalance = Math.round(t.balance * 100) / 100;
            const diff = Math.abs(expectedBalance - actualBalance);

            if (diff > 0.02 && !t.description.toUpperCase().includes("OPENING")) {
                errorIndices.push(i);
                warnings.push(`Row ${i + 1} (${t.date}): Exp ${expectedBalance}, Got ${actualBalance}`);
                failed = true;
            }
        });

        globalStats.total_txns = processed.length;

        return {
            reconciliation_failed: failed,
            reconciliation_warnings: warnings,
            error_indices: errorIndices,
            currency: "NGN",
            transactions: processed,
            organizationName: metadata.org,
            bankName: metadata.bank,
            stats: globalStats
        };

    } catch (e: any) {
        console.error("Analysis Error:", e);
        throw new Error("Analysis Failed: " + e.message);
    }
};