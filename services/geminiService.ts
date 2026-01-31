
import { GoogleGenAI } from "@google/genai";
import { AnalysisResult, Transaction, AnalysisStatistics } from "../types";
import { categorizeTransaction } from "./categorizationRules";

// --- CONFIGURATION ---
const MODEL_NAME = 'gemini-3-flash-preview';

// OPTIMIZATION: RAW TEXT STREAM MODE
// We ask for pipe-delimited text. This uses ~30% fewer tokens than JSON,
// allowing the model to fit significantly more rows (handling multi-page PDFs better).
const SYSTEM_INSTRUCTION = `
You are a high-speed financial extraction engine.
TASK: Extract ALL transaction rows from the bank statement. Process every single page from start to finish.

OUTPUT FORMAT:
Date|Description|Debit|Credit|Balance

RULES:
1. Output raw text only. Do not use Markdown code blocks. Do not use JSON.
2. Separator: Use the pipe character "|" strictly.
3. Multiline Descriptions: Merge into a single line.
4. Numbers: Plain numbers (e.g., 1200.50). Remove commas.
5. Empty values: Use 0 for empty numeric columns.
6. Dates: Copy the date exactly as shown. If a date is not visible (ditto), use the date from the previous row.
7. COMPREHENSIVENESS: You must extract data from ALL pages. Do not stop until the document ends.
8. END MARKER: At the very end of the output, after the last row, print exactly: ###END###
`;

export const analyzeBankStatement = async (base64Data: string, mimeType: string, customApiKey?: string): Promise<AnalysisResult> => {
  const runStats: AnalysisStatistics = {
    total_txns: 0,
    rule_hits: 0,
    memory_hits: 0,
    ai_txns: 0,
    ai_calls: 0,
    human_overrides: 0,
    ai_rate_percent: 0,
    auto_rate_percent: 0
  };

  const getKeys = () => {
     if (customApiKey) return [customApiKey];
     const envKeys = process.env.API_KEY || "";
     return envKeys.split(',').map(k => k.trim()).filter(k => k.length > 0);
  };
  const keys = getKeys();
  if (keys.length === 0) throw new Error("No API Key available.");
  const key = keys[0];

  try {
    const ai = new GoogleGenAI({ apiKey: key });
    runStats.ai_calls++;

    // --- RAW TEXT MODE ---
    const response = await ai.models.generateContent({
      model: MODEL_NAME,
      contents: {
        parts: [
          { inlineData: { data: base64Data, mimeType: mimeType } },
          { text: "Extract all transactions. Format: Date|Description|Debit|Credit|Balance" },
        ],
      },
      config: {
        systemInstruction: SYSTEM_INSTRUCTION,
        // responseMimeType: "application/json", // DISABLED: We want raw text stream
        maxOutputTokens: 65536, 
        temperature: 0, // Deterministic
        thinkingConfig: { thinkingBudget: 0 } 
      },
    });

    const responseText = response.text || "";
    const reconciliation_warnings: string[] = [];

    // --- PARSING LOGIC ---
    let rawRows: any[] = [];
    
    // 1. Check for truncation (Did the model finish?)
    if (!responseText.includes("###END###")) {
        reconciliation_warnings.push("WARNING: Analysis may be incomplete. The document is very long, and the AI output was truncated. Please verify the last transaction.");
        console.warn("Output truncated: ###END### marker missing.");
    }

    // 2. Parse Line-by-Line
    const lines = responseText.split(/\r?\n/);
    
    for (const line of lines) {
        const cleanLine = line.trim();
        if (!cleanLine) continue;
        if (cleanLine === "###END###") continue;
        if (cleanLine.startsWith("Date|")) continue; // Skip header if present
        if (cleanLine.startsWith("```")) continue; // Skip markdown fences

        const parts = cleanLine.split('|').map(p => p.trim());
        
        // Validation: Must have at least 5 parts.
        // Format: Date | Desc | Debit | Credit | Balance
        if (parts.length >= 5) {
            // Heuristic: First column should look like a date or contain digits
            if (!/[\d]/.test(parts[0]) && !parts[0].toLowerCase().includes('date')) {
                continue;
            }
            rawRows.push(parts);
        }
    }

    // --- CONVERT TO OBJECTS ---
    const dedupMap = new Map<string, Transaction>();

    const safeFloat = (val: string): number => {
        if (!val) return 0;
        // Remove commas, currency symbols, keep dots and minus
        const clean = val.replace(/[^0-9.-]/g, '');
        return parseFloat(clean) || 0;
    };

    rawRows.forEach((row: string[]) => {
        const dateStr = row[0] || "0000-00-00";
        const description = row[1] || "Unknown Transaction";
        
        // Handle Debit/Credit logic
        // Sometimes models swap them or put 0. We treat them as distinct.
        const debit = safeFloat(row[2]);
        const credit = safeFloat(row[3]);
        const balance = safeFloat(row[4]);

        // Smart Filtering
        if (/^Page \d+/.test(description)) return;
        
        // If row is completely empty/zero (except opening balance), skip
        const isBalanceRow = /B\/F|BROUGHT FORWARD|OPENING BAL/i.test(description);
        if (!isBalanceRow && Math.abs(debit) < 0.001 && Math.abs(credit) < 0.001) return;

        // Dedup: Fingerprint
        const fingerprint = `${dateStr}|${debit}|${credit}|${balance}|${description.substring(0, 50)}`;
        
        if (!dedupMap.has(fingerprint)) {
            dedupMap.set(fingerprint, {
                date: dateStr,
                description: description,
                category: 'Unallocated',
                debit,
                credit,
                balance,
            });
        }
    });

    const uniqueTransactions = Array.from(dedupMap.values());
    
    // SORTING:
    // 1. Force "Opening Balance" to top.
    // 2. Preserve extraction order (Document Order).
    uniqueTransactions.sort((a, b) => {
        const isOpeningA = /OPENING\s*BAL/i.test(a.description);
        const isOpeningB = /OPENING\s*BAL/i.test(b.description);
        if (isOpeningA && !isOpeningB) return -1;
        if (!isOpeningA && isOpeningB) return 1;
        return 0; 
    });

    // --- RECONCILIATION ENGINE (MATH CHECK) ---
    let reconciliation_failed = false;
    
    if (uniqueTransactions.length > 1) {
       for (let i = 1; i < uniqueTransactions.length; i++) {
          const prev = uniqueTransactions[i-1];
          const curr = uniqueTransactions[i];
          
          // Logic: Prev Balance - Debit + Credit = Current Balance
          const expectedBalance = prev.balance - curr.debit + curr.credit;
          const diff = Math.abs(expectedBalance - curr.balance);
          
          if (diff > 0.02) {
             // Only flag if it's not a logical break (like a new section)
             // And ignore if the description implies it's just a carry forward line without value impact
             if (!/OPENING\s*BAL/i.test(curr.description)) {
                 reconciliation_failed = true;
                 reconciliation_warnings.push(`Row ${i+1} (${curr.date}): Math Error. Expected ${expectedBalance.toFixed(2)}, Found ${curr.balance.toFixed(2)}`);
             }
          }
       }
    }

    // --- CATEGORIZATION ENGINE ---
    const processedTransactions = uniqueTransactions.map(t => {
      runStats.total_txns++;
      const classified = categorizeTransaction(t);
      
      if (classified.decision_source === 'RULE') runStats.rule_hits++;
      else if (classified.decision_source === 'MEMORY') runStats.memory_hits++;
      else runStats.ai_txns++;
      
      return classified;
    });

    if (runStats.total_txns > 0) {
      runStats.ai_rate_percent = parseFloat(((runStats.ai_txns / runStats.total_txns) * 100).toFixed(2));
      runStats.auto_rate_percent = parseFloat((((runStats.rule_hits + runStats.memory_hits) / runStats.total_txns) * 100).toFixed(2));
    }

    return {
      reconciliation_failed, 
      reconciliation_warnings,
      currency: "USD", // Defaulting to USD, can be enhanced to extract from header later
      transactions: processedTransactions,
      organizationName: "Extracted Organization",
      bankName: "Extracted Bank",
      stats: runStats
    };

  } catch (error: any) {
    console.error("Gemini Analysis Error:", error);
    throw new Error(error.message || "Analysis failed.");
  }
};
