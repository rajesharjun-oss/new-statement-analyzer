import { GoogleGenAI } from "@google/genai";
import { AnalysisResult, Transaction, AnalysisStatistics } from "../types";
import { categorizeTransaction } from "./categorizationRules";
import { extractTransactionsFromPdf } from "./pdfService";

const MODEL_NAME = "gemini-2.0-flash";

const base64ToArrayBuffer = (base64: string) => {
    const binaryString = window.atob(base64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
};

// --- CORE: Bank Analysis Service ---
export const analyzeBankStatement = async (base64Data: string, mimeType: string, customApiKey?: string): Promise<AnalysisResult> => {
    const runStats: AnalysisStatistics = {
        total_txns: 0, rule_hits: 0, memory_hits: 0, ai_txns: 0, ai_calls: 0, human_overrides: 0, ai_rate_percent: 0, auto_rate_percent: 0
    };

    try {
        let transactions: Transaction[] = [];
        let orgName = "Detected Organization";
        let bankName = "Detected Bank";
        let currency = "NGN"; // Default
        let aiReportedCount = 0;

        // 1. DETERMINISTIC PDF EXTRACTION (Hybrid Approach)
        let pdfExtractionSuccess = false;

        if (mimeType === 'application/pdf') {
            try {
                console.log("[GeminiService] Attempting Deterministic PDF Extraction...");
                const buffer = base64ToArrayBuffer(base64Data);
                const pdfTxns = await extractTransactionsFromPdf(buffer);

                if (pdfTxns.length > 0) {
                    console.log(`[GeminiService] specialized PDF parser found ${pdfTxns.length} transactions.`);
                    transactions = pdfTxns;
                    aiReportedCount = pdfTxns.length; // Trusted count
                    pdfExtractionSuccess = true;
                    orgName = "PDF Extracted"; // Placeholder
                }
            } catch (pdfErr) {
                console.warn("[GeminiService] PDF Extraction failed, falling back to AI:", pdfErr);
            }
        }

        // 2. AI GENERATION (Fallback or Non-PDF)
        if (!pdfExtractionSuccess) {
            console.log(`[GeminiService] Uploading ${mimeType} to Gemini 2.0 Flash...`);

            const getKeys = () => {
                if (customApiKey) return [customApiKey];
                let envKeys = "";
                try {
                    // Check process.env (injected by Vite define)
                    if (typeof process !== 'undefined' && process.env && process.env.API_KEY) {
                        envKeys = process.env.API_KEY;
                    }
                    // Check import.meta.env (Vite native)
                    else if (import.meta.env && import.meta.env.VITE_API_KEY) {
                        envKeys = import.meta.env.VITE_API_KEY;
                    }
                } catch (e) { }
                return envKeys.split(',').map(k => k.trim()).filter(k => k.length > 0);
            };
            const keys = getKeys();

            if (keys.length === 0) {
                throw new Error("No API Key available. Please configure it in the settings menu.");
            }

            // SWITCH TO PIPE-SEPARATED VALUES (PSV) FOR MAXIMUM TOKEN EFFICIENCY
            // JSON structure overhead causes truncation on long statements.
            // PSV format: Date|Description|Category|Debit|Credit|Balance
            const systemPrompt = `
                You are an expert financial analyst. Extract all bank transactions from the document into a structured text format.
                To ensure all data fits within the output limit, use a strict pipe-separated value (PSV) format.
    
                OUTPUT STRUCTURE:
                Line 1: ORG: <Organization Name>
                Line 2: BANK: <Bank Name>
                Line 3: CURR: <Currency Code e.g. NGN, USD>
                Line 4: HEADER: Date|Description|Category|Debit|Credit|Balance
                Line 5+: <Data Rows>
                Last Line: COUNT: <Total Number of Transaction Rows Extracted>
    
                RULES:
                1. Extract ALL transaction rows. Do not skip any.
                2. Separator is | (pipe). Do not use pipes in descriptions (replace with space).
                3. Date Format: DD-MMM-YYYY (e.g. 14-Jun-2025).
                4. Money Format: 1234.56 (No commas). Use 0 for empty/zero fields.
                5. Merge multi-line descriptions into one line.
                6. Category: Choose the best fit based on the description/context (e.g., "Bank Charges", "Transfer", "Salary", "Utility"). If unsure, use "Unallocated".
                7. Do not use Markdown code blocks. Just raw text.
                8. SPECIAL RULE: If a line indicates "Balance Brought Forward", "B/F", or "Opening Balance" for a new page, extract it! 
                   Set Description as "Opening Balance", and put the value in the Balance column. Set Debit/Credit to 0.
            `;

            let response;
            let lastError;

            console.log(`[GeminiService] Found ${keys.length} API keys. Starting rotation...`);

            for (let i = 0; i < keys.length; i++) {
                const key = keys[i];
                try {
                    console.log(`[GeminiService] Attempting with Key #${i + 1} (ends in ...${key.slice(-4)})`);
                    const ai = new GoogleGenAI({ apiKey: key });

                    response = await ai.models.generateContent({
                        model: MODEL_NAME,
                        contents: {
                            parts: [
                                { inlineData: { mimeType: mimeType, data: base64Data } },
                                { text: systemPrompt }
                            ]
                        },
                        config: {
                            // Removing responseSchema to allow raw text generation
                            // Removing maxOutputTokens to let model use full capacity
                        }
                    });

                    // If we get here, it succeeded!
                    break;

                } catch (error: any) {
                    console.warn(`[GeminiService] Key #${i + 1} failed: ${error.message || error}`);
                    lastError = error;
                    // Continue to next key
                }
            }

            if (!response) {
                throw new Error(`All ${keys.length} API keys failed. Last error: ${lastError?.message || "Unknown error"}`);
            }

            runStats.ai_calls++;

            const rawText = response.text || "";
            console.log("[GeminiService] Raw response length:", rawText.length);

            // Parse PSV Text
            const lines = rawText.split('\n').map(l => l.trim()).filter(l => l.length > 0);

            for (const line of lines) {
                // Metadata parsing
                if (line.startsWith("ORG:")) {
                    orgName = line.replace("ORG:", "").trim();
                }
                else if (line.startsWith("BANK:")) {
                    bankName = line.replace("BANK:", "").trim();
                }
                else if (line.startsWith("CURR:")) {
                    currency = line.replace("CURR:", "").trim();
                }
                else if (line.startsWith("COUNT:")) {
                    const countStr = line.replace("COUNT:", "").trim();
                    aiReportedCount = parseInt(countStr, 10) || 0;
                }
                else if (line.startsWith("HEADER:") || line.startsWith("Date|")) {
                    continue;
                }
                else if (line.includes("|")) {
                    // Transaction Row
                    const parts = line.split('|').map(p => p.trim());

                    if (parts.length >= 6) {
                        const date = parts[0];
                        if (date.toLowerCase() === 'date') continue;

                        const desc = parts[1];
                        const category = parts[2];
                        const drStr = parts[3].replace(/,/g, '');
                        const crStr = parts[4].replace(/,/g, '');
                        const balStr = parts[5].replace(/,/g, '');

                        const debit = parseFloat(drStr) || 0;
                        const credit = parseFloat(crStr) || 0;
                        const balance = parseFloat(balStr) || 0;

                        transactions.push({
                            date,
                            description: desc,
                            category: category || "Unallocated",
                            debit,
                            credit,
                            balance,
                            is_reversal: false
                        });
                    }
                }
            }

            console.log(`[GeminiService] Extracted ${transactions.length} transactions via AI (CSV Mode). AI Reported Count: ${aiReportedCount}`);

            if (transactions.length === 0) {
                console.warn("No transactions found. Raw text dump:", rawText);
                throw new Error("AI could not find any transaction rows in the expected format.");
            }
        }


        // 2. POST-PROCESS: Categorization & Validation
        const warnings: string[] = [];
        const errorIndices: number[] = [];
        let failed = false;
        const TOLERANCE = 0.05;

        // COUNT VALIDATION
        if (aiReportedCount > 0 && transactions.length !== aiReportedCount) {
            warnings.push(`AI reported ${aiReportedCount} transactions, but extracted ${transactions.length}. Check for missing rows.`);
            // We don't fail reconciliation just for this, but we warn the user.
        }

        const processedTransactions = transactions.map((t, index) => {
            runStats.total_txns++;

            // Normalize values
            const safeTxn: Transaction = {
                date: t.date || "",
                description: (t.description || "Unknown").replace(/\s+/g, ' ').trim(),
                category: t.category || "Unallocated",
                debit: Number(t.debit) || 0,
                credit: Number(t.credit) || 0,
                balance: Number(t.balance) || 0,
                is_reversal: false
            };

            // Categorize
            let categorized = categorizeTransaction(safeTxn);
            if (categorized.decision_source === 'RULE') runStats.rule_hits++;
            else runStats.ai_txns++;

            // Reconciliation Math Check
            if (index > 0) {
                const prev = transactions[index - 1];
                const prevBal = Number(prev.balance) || 0;
                const currBal = safeTxn.balance;

                // Logic: PrevBal + Credit - Debit = CurrBal
                const expected = prevBal + safeTxn.credit - safeTxn.debit;
                const diff = Math.abs(expected - currBal);

                if (diff > TOLERANCE) {
                    // Ignore Opening Balance rows for math check as they reset the chain
                    if (!categorized.category.includes("Opening Balance")) {
                        errorIndices.push(index);
                        warnings.push(`Row ${index + 1} (${safeTxn.date}): Math Mismatch. Exp ${expected.toFixed(2)}, Found ${currBal.toFixed(2)}`);
                        failed = true;
                    }
                }
            }

            return categorized;
        });

        return {
            reconciliation_failed: failed,
            reconciliation_warnings: warnings,
            error_indices: errorIndices,
            currency: currency,
            transactions: processedTransactions,
            organizationName: orgName,
            bankName: bankName,
            stats: runStats
        };

    } catch (error: any) {
        console.error("Analysis Error:", error);
        throw new Error("Analysis Failed: " + (error.message || "Unknown error"));
    }
};