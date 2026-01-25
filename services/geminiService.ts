
import { GoogleGenAI, Type, Schema } from "@google/genai";
import { AnalysisResult, Transaction, CATEGORIES, AnalysisStatistics } from "../types";
import { categorizeTransaction } from "./categorizationRules";

const SYSTEM_INSTRUCTION = `
You are a highly specialized bank-statement analysis engine. Your job is to extract data from bank statement PDFs, categorize transactions, and return data in a strict JSON format.

CONTEXT:
You may be processing a SINGLE PAGE or a WHOLE FILE. Treat it as a continuous stream of data.

RECONCILIATION RULES (STRICT):
1. Perform PRIMARY reconciliation on transaction table rows.
   - Validate running balances: previous_balance - debit + credit == current_balance.
   - Allow a tolerance of 0.02.
   - If validation fails, set reconciliation_failed = true.

2. **Column Mapping Rule (CRITICAL)**:
   - "Pay In" / "Deposit" / "Credit" -> **Credit**.
   - "Pay Out" / "Withdrawal" / "Debit" -> **Debit**.
   - "Details" / "Narration" / "Memo" -> **Description**.
   - **NEGATIVE VALUES / REVERSALS (NON-NEGOTIABLE)**:
     - If a value appears in the **Debit** column with parentheses e.g. "(123.45)" or a minus sign "-123.45", extract it as a **NEGATIVE NUMBER** in the **Debit** field (e.g., "debit": -123.45).
     - **DO NOT** move it to the Credit column.
     - **DO NOT** convert it to a positive number.
     - The same applies to negative values in the Credit column: keep them in the Credit field as negative numbers.

RECORD COUNT RULE (NON-NEGOTIABLE):
3. Extract every single dated row that has a debit, credit, or opening balance.
4. Do NOT group/merge transactions.
5. Merge multi-line descriptions into a single "Description" string.

CATEGORIZATION RULES:
6. Analyze each "Description" and assign a "Category" from the provided Chart of Accounts.
   - **Prioritize specific matches**: Travel, Fuel, Utilities, Healthcare, Bank Charges.
   - **Reversal Rule**: If a transaction is a reversal (starts with REV/), assign the ORIGINAL category (e.g. REV/Fuel -> Fuel).
   - **Defaults**: If unsure, use "Review Required".
   - **Categories**: ${CATEGORIES.join(', ')}.

OUTPUT RULES:
7. Standardize dates to YYYY-MM-DD.
8. Standardize amounts to floats.
9. Detect the primary currency (ISO code).
10. Extract 'organizationName' and 'bankName'.
11. Set **is_reversal = true** if description starts with "REV/" or "REVERSAL".
`;

const RESPONSE_SCHEMA: Schema = {
  type: Type.OBJECT,
  properties: {
    reconciliation_failed: { type: Type.BOOLEAN },
    reconciliation_warnings: {
      type: Type.ARRAY,
      items: { type: Type.STRING },
    },
    currency: { type: Type.STRING },
    organizationName: { type: Type.STRING },
    bankName: { type: Type.STRING },
    transactions: {
      type: Type.ARRAY,
      items: {
        type: Type.OBJECT,
        properties: {
          date: { type: Type.STRING },
          description: { type: Type.STRING },
          category: { type: Type.STRING },
          reference: { type: Type.STRING },
          debit: { type: Type.NUMBER },
          credit: { type: Type.NUMBER },
          balance: { type: Type.NUMBER },
          is_reversal: { type: Type.BOOLEAN },
        },
        required: ["date", "description", "category", "debit", "credit", "balance", "is_reversal"],
      },
    },
  },
  required: ["reconciliation_failed", "transactions", "currency"],
};

// Helper: Perform the actual API call
const performGeminiCall = async (apiKey: string, base64Data: string, mimeType: string, model: string) => {
  const ai = new GoogleGenAI({ apiKey });
  const response = await ai.models.generateContent({
    model, 
    contents: {
      parts: [
        {
          inlineData: {
            data: base64Data,
            mimeType: mimeType,
          },
        },
        {
          text: "Analyze this bank statement attachment. Extract all transactions, summaries, and metadata following the System Rules.",
        },
      ],
    },
    config: {
      systemInstruction: SYSTEM_INSTRUCTION,
      responseMimeType: "application/json",
      responseSchema: RESPONSE_SCHEMA,
      temperature: 0,
      // Increase output budget to handle large transaction lists without truncation
      maxOutputTokens: 65536,
      // Reduced thinking budget for speed (Flash models are efficient)
      thinkingConfig: { thinkingBudget: 1024 },
    },
  });

  if (!response.text) throw new Error("No response text received from Gemini.");
  
  // Robust JSON cleaning to prevent parsing errors if markdown is included
  let cleanText = response.text.trim();
  // Remove markdown fences if present (start and end)
  cleanText = cleanText.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');

  try {
    return JSON.parse(cleanText);
  } catch (e) {
    console.error("JSON Parse Error on text length:", cleanText.length);
    console.error("Snippet:", cleanText.slice(-200));
    // If we can't parse, it's likely truncation due to extreme length
    throw new Error("Analysis incomplete or file too large. Please try splitting the document into fewer pages.");
  }
};

export const analyzeBankStatement = async (base64Data: string, mimeType: string, customApiKey?: string): Promise<AnalysisResult> => {
  try {
    // --- RUN STATS INITIALIZATION ---
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

    let rawData: any;
    // Fallback strategy: Prioritize Flash for speed, fall back to Pro
    const models = ['gemini-3-flash-preview', 'gemini-3-pro-preview'];

    const getKeys = () => {
       if (customApiKey) return [customApiKey];
       const envKeys = process.env.API_KEY || "";
       return envKeys.split(',').map(k => k.trim()).filter(k => k.length > 0);
    };

    const keys = getKeys();
    if (keys.length === 0) {
      throw new Error("No API Key available. Please add one in Settings or configure API_KEY in your .env file.");
    }

    let lastError: any;
    let success = false;

    // Outer Loop: Model Fallback
    for (const model of models) {
        if (success) break;
        
        // Inner Loop: Retry Logic
        for (let attempt = 0; attempt < 3; attempt++) {
            try {
                const key = keys[Math.floor(Math.random() * keys.length)];
                
                // Track AI Call (Actual API Hit)
                runStats.ai_calls++;
                
                rawData = await performGeminiCall(key, base64Data, mimeType, model);
                success = true;
                break; // Success, exit retry loop
            } catch (error: any) {
                lastError = error;
                const errMsg = error.message || '';
                const status = error.status || 0;
                
                // Enhanced transient check including RPC/500 errors often caused by network/proxy issues
                const isNetworkError = errMsg.includes('Rpc failed') || errMsg.includes('xhr error') || errMsg.includes('fetch failed');
                const isServerError = status >= 500 || errMsg.includes('500') || errMsg.includes('503');
                const isRateLimit = status === 429 || errMsg.includes('429') || errMsg.includes('Quota');
                
                const isTransient = isNetworkError || isServerError || isRateLimit;

                if (isTransient && attempt < 2) {
                    console.warn(`Attempt ${attempt + 1} with ${model} failed (${errMsg}). Retrying...`);
                    await new Promise(resolve => setTimeout(resolve, 2000 * (attempt + 1))); // Exponential backoff
                    continue; 
                }
                
                // If error is not transient (e.g. 400 Bad Request) or we exhausted retries, break retry loop to try next model
                break; 
            }
        }
    }

    if (!success) {
        throw lastError || new Error("Analysis failed. Please check your internet connection or try a smaller file.");
    }

    // Sanitize, Apply Strict Categorization Rules, and TRACK STATS
    const processedTransactions = (rawData.transactions || []).map((t: Transaction) => {
      runStats.total_txns++;
      
      const classified = categorizeTransaction(t);
      
      // Increment counters based on decision source
      if (classified.decision_source === 'RULE') {
        runStats.rule_hits++;
      } else if (classified.decision_source === 'MEMORY') {
        runStats.memory_hits++;
      } else {
        // Fallback to AI (or if undefined)
        runStats.ai_txns++;
      }
      
      return classified;
    });

    // Compute Rates
    if (runStats.total_txns > 0) {
      runStats.ai_rate_percent = parseFloat(((runStats.ai_txns / runStats.total_txns) * 100).toFixed(2));
      runStats.auto_rate_percent = parseFloat((((runStats.rule_hits + runStats.memory_hits) / runStats.total_txns) * 100).toFixed(2));
    }

    const data: AnalysisResult = {
      reconciliation_failed: rawData.reconciliation_failed || false,
      reconciliation_warnings: rawData.reconciliation_warnings || [],
      currency: rawData.currency || "USD",
      transactions: processedTransactions,
      organizationName: rawData.organizationName || "Unknown Organization",
      bankName: rawData.bankName || "Unknown Bank",
      stats: runStats
    };
    
    return data;
  } catch (error) {
    console.error("Gemini Analysis Error:", error);
    throw error;
  }
};
