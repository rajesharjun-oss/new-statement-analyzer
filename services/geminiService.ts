
import { GoogleGenAI, Type, Schema } from "@google/genai";
import { AnalysisResult, Transaction, CATEGORIES } from "../types";
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
2. **Column Mapping Rule**:
   - "Pay In" / "Deposit" / "Credit" -> **Credit**.
   - "Pay Out" / "Withdrawal" / "Debit" -> **Debit**.
   - "Details" / "Narration" / "Memo" -> **Description**.

RECORD COUNT RULE (NON-NEGOTIABLE):
3. Extract every single dated row that has a debit, credit, or opening balance.
4. Do NOT group/merge transactions.
5. Merge multi-line descriptions into a single "Description" string.

CATEGORIZATION RULES:
6. Analyze each "Description" and assign a "Category" from the provided Chart of Accounts.
   - **Prioritize specific matches**: Travel, Fuel, Utilities, Healthcare, Bank Charges.
   - **Reversal Rule**: If a transaction is a reversal (starts with REV/), assign the ORIGINAL category (e.g. REV/Fuel -> Fuel).
   - **Defaults**: If unsure, use "Unallocated".
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
const performGeminiCall = async (apiKey: string, base64Data: string, mimeType: string) => {
  const ai = new GoogleGenAI({ apiKey });
  const response = await ai.models.generateContent({
    model: 'gemini-3-flash-preview',
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
    },
  });

  if (!response.text) throw new Error("No response text received from Gemini.");
  
  // Robust JSON cleaning to prevent parsing errors if markdown is included
  let cleanText = response.text.trim();
  if (cleanText.startsWith('```json')) {
    cleanText = cleanText.replace(/^```json/, '').replace(/```$/, '');
  } else if (cleanText.startsWith('```')) {
     cleanText = cleanText.replace(/^```/, '').replace(/```$/, '');
  }

  try {
    return JSON.parse(cleanText);
  } catch (e) {
    console.error("JSON Parse Error on text:", cleanText);
    throw new Error("Failed to parse AI response. Please try again.");
  }
};

export const analyzeBankStatement = async (base64Data: string, mimeType: string, customApiKey?: string): Promise<AnalysisResult> => {
  try {
    let rawData: any;

    if (customApiKey) {
      rawData = await performGeminiCall(customApiKey, base64Data, mimeType);
    } 
    else {
      const envKeys = process.env.API_KEY || "";
      const systemKeys = envKeys.split(',').map(k => k.trim()).filter(k => k.length > 0);

      if (systemKeys.length === 0) {
        throw new Error("No API Key available. Please add one in Settings or configure API_KEY in your .env file.");
      }

      let lastError: any;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const key = systemKeys[Math.floor(Math.random() * systemKeys.length)];
          rawData = await performGeminiCall(key, base64Data, mimeType);
          break;
        } catch (error: any) {
          lastError = error;
          // Handle Rate Limits (429) and Service Unavailable (503)
          const isTransient = error.message?.includes('429') || error.status === 429 || error.message?.includes('Quota') || error.status === 503;
          if (isTransient && attempt < 2) {
            console.warn(`Attempt ${attempt + 1} failed (Transient Error). Retrying...`);
            await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
            continue; 
          }
          throw error;
        }
      }
      if (!rawData && lastError) throw lastError;
    }

    // Sanitize and Apply Strict Categorization Rules
    const processedTransactions = (rawData.transactions || []).map((t: Transaction) => categorizeTransaction(t));

    const data: AnalysisResult = {
      reconciliation_failed: rawData.reconciliation_failed || false,
      reconciliation_warnings: rawData.reconciliation_warnings || [],
      currency: rawData.currency || "USD",
      transactions: processedTransactions,
      organizationName: rawData.organizationName || "Unknown Organization",
      bankName: rawData.bankName || "Unknown Bank"
    };
    
    return data;
  } catch (error) {
    console.error("Gemini Analysis Error:", error);
    throw error;
  }
};
