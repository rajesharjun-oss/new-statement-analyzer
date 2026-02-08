import { GoogleGenAI } from "@google/genai";
import { AnalysisResult, Transaction, AnalysisStatistics } from "../types";
import { categorizeTransaction } from "./categorizationRules";

const MODEL_NAME = "gemini-2.0-flash";

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
        
        console.log(`[GeminiService] Uploading ${mimeType} to Gemini 2.0 Flash...`);
        
        const getKeys = () => {
            if (customApiKey) return [customApiKey];
            let envKeys = "";
            try { 
                if (typeof process !== 'undefined' && process.env) {
                    envKeys = process.env.API_KEY || ""; 
                }
            } catch (e) {}
            return envKeys.split(',').map(k => k.trim()).filter(k => k.length > 0);
        };
        const keys = getKeys();
        
        if (keys.length === 0) {
            throw new Error("No API Key available. Please configure it in the settings menu.");
        }
        
        const ai = new GoogleGenAI({ apiKey: keys[0] });

        // SWITCH TO PIPE-SEPARATED VALUES (PSV) FOR MAXIMUM TOKEN EFFICIENCY
        // JSON structure overhead causes truncation on long statements.
        // PSV format: Date|Description|Debit|Credit|Balance
        const systemPrompt = `
            You are an expert financial analyst. Extract all bank transactions from the document into a structured text format.
            To ensure all data fits within the output limit, use a strict pipe-separated value (PSV) format.

            OUTPUT STRUCTURE:
            Line 1: ORG: <Organization Name>
            Line 2: BANK: <Bank Name>
            Line 3: CURR: <Currency Code e.g. NGN, USD>
            Line 4: HEADER: Date|Description|Debit|Credit|Balance
            Line 5+: <Data Rows>

            RULES:
            1. Extract ALL transaction rows. Do not skip any.
            2. Separator is | (pipe). Do not use pipes in descriptions (replace with space).
            3. Date Format: DD-MMM-YYYY (e.g. 14-Jun-2025).
            4. Money Format: 1234.56 (No commas). Use 0 for empty/zero fields.
            5. Merge multi-line descriptions into one line.
            6. Do not use Markdown code blocks. Just raw text.
            7. SPECIAL RULE: If a line indicates "Balance Brought Forward", "B/F", or "Opening Balance" for a new page, extract it! 
               Set Description as "Opening Balance", and put the value in the Balance column. Set Debit/Credit to 0.
        `;

        const response = await ai.models.generateContent({
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
            else if (line.startsWith("HEADER:") || line.startsWith("Date|")) {
                continue;
            }
            else if (line.includes("|")) {
                // Transaction Row
                // Format: Date|Description|Debit|Credit|Balance
                const parts = line.split('|').map(p => p.trim());
                
                if (parts.length >= 5) {
                    const date = parts[0];
                    // Skip repeated headers if model hallucinates them
                    if (date.toLowerCase() === 'date') continue;

                    const desc = parts[1];
                    // Remove commas for safety in parsing
                    const drStr = parts[2].replace(/,/g, '');
                    const crStr = parts[3].replace(/,/g, '');
                    const balStr = parts[4].replace(/,/g, '');

                    // Safe float parsing
                    const debit = parseFloat(drStr) || 0;
                    const credit = parseFloat(crStr) || 0;
                    const balance = parseFloat(balStr) || 0;

                    transactions.push({
                        date,
                        description: desc,
                        category: "Unallocated",
                        debit,
                        credit,
                        balance,
                        is_reversal: false
                    });
                }
            }
        }

        console.log(`[GeminiService] Extracted ${transactions.length} transactions via AI (CSV Mode).`);

        if (transactions.length === 0) {
             console.warn("No transactions found. Raw text dump:", rawText);
             throw new Error("AI could not find any transaction rows in the expected format.");
        }

        // 2. POST-PROCESS: Categorization & Validation
        const warnings: string[] = [];
        const errorIndices: number[] = [];
        let failed = false;
        const TOLERANCE = 0.05;

        const processedTransactions = transactions.map((t, index) => {
            runStats.total_txns++;
            
            // Normalize values
            const safeTxn: Transaction = {
                date: t.date || "",
                description: (t.description || "Unknown").replace(/\s+/g, ' ').trim(),
                category: "Unallocated",
                debit: Number(t.debit) || 0,
                credit: Number(t.credit) || 0,
                balance: Number(t.balance) || 0,
                is_reversal: false
            };

            // Categorize
            const categorized = categorizeTransaction(safeTxn);
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
                        warnings.push(`Row ${index+1} (${safeTxn.date}): Math Mismatch. Exp ${expected.toFixed(2)}, Found ${currBal.toFixed(2)}`);
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