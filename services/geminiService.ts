import { GoogleGenAI, Type, Schema } from "@google/genai";
import { AnalysisResult } from "../types";

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
6. Analyze each "Description" and assign a "Category" from this specific Chart of Accounts:
   - **Income**: Operating Income (Service 1, Service 2), Other Income (Interest Income, Exchange Gain, Parking, Printing, Miscellaneous).
   - **Cost of Sales**: COS 1, COS 2.
   - **Operating Expenses**: Salaries & Wages, Staff Welfare, Staff Meals/Canteen, Staff Uniforms/Laundry, Staff Training, Staff Incentives, Telephone Expense, Utilities (Electricity & Water), Cable & Internet, Repairs & Maintenance (Hotel, Building, Electrical, Mechanical, Furniture, Equipment), Cleaning, Diesel, Security, Depreciation, Travel Expense, Insurance, Licenses & Permits, Software Subscriptions, IT Maintenance & Repairs.
   - **Marketing & Promotion**: Advertising & Promotions.
   - **Professional Fees**: Legal Fees, Audit Fees, Consultancy Fees.
   - **Finance Costs**: Bank POS / Merchant Transaction Fees, Bank Charges, Interest Expense, Exchange Rate Loss.
   - **Taxes & Levies**: Company Income Tax, Education Tax, Hotel Occupancy & Restaurant Consumption Tax, Fines & Penalties.
   - **Transfers**: Transfer In, Transfer Out. (Use only if no specific expense/income category matches).
   - **Rule**: Credit = Income/Transfer In. Debit = Expense/Liability/Transfer Out.
   - **Semantic Matching Rule**: do NOT just look for exact keywords. You must **understand** the description.
     - Example: "Eko Disco" or "Ikeja Electric" -> **Utilities**.
     - Example: "Chicken Republic" or "KFC" -> **Staff Meals/Canteen**.
     - Example: "NNPC Station" -> **Diesel** (if fuel) or **Transport** (if travel).
     - Example: "EMTL" or "Electronic Money Transfer Levy" -> **Bank Charges**.
   - **Inference Rule**: If you see a **NEW description**, measure its "semantic distance" to known business types.
     - Example: "Joy's Buka" (unknown) -> sounds like "Restaurant/Food" -> **Staff Meals/Canteen**.
     - Example: "ABC Logistics" (unknown) -> sounds like "Transport" -> **Transport**.
   - **Specificity**: ALWAYS prefer a specific expense (e.g. "Diesel Supply" -> "Diesel") over "Transfer Out".
   - **Default**: "Unallocated" if unsure.

OUTPUT RULES:
7. Standardize dates to YYYY-MM-DD.
8. Standardize amounts to floats (negative for reversals).
9. Detect the primary currency of the statement (e.g. USD, EUR, GBP, JPY) and return it as a standard 3-letter ISO code. Default to "USD" if not found.
10. Extract the 'organizationName' (the account holder) and 'bankName' from the statement. If not explicitly found, try to infer from header logo text or metadata. Default to 'Unknown Organization' and 'Unknown Bank' if absolutely missing.
11. Ensure strict JSON compliance.
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
        },
        required: ["date", "description", "category", "debit", "credit", "balance"],
      },
    },
  },
  required: ["reconciliation_failed", "transactions", "currency"],
};

// Helper: Perform the actual API call
const performGeminiCall = async (apiKey: string, base64Data: string, mimeType: string) => {
  const ai = new GoogleGenAI({ apiKey });
  const response = await ai.models.generateContent({
    model: 'gemini-3-pro-preview',
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
  return JSON.parse(response.text);
};

export const analyzeBankStatement = async (base64Data: string, mimeType: string, customApiKey?: string): Promise<AnalysisResult> => {
  try {
    let rawData: any;

    // SCENARIO 1: User provided a Custom Key via Settings
    // We try this key once. We do not rotate it with system keys.
    if (customApiKey) {
      rawData = await performGeminiCall(customApiKey, base64Data, mimeType);
    } 
    // SCENARIO 2: Use System Environment Keys (with Rotation & Retry)
    else {
      const envKeys = process.env.API_KEY || "";
      // Split by comma to support multiple keys: "KEY_1, KEY_2"
      const systemKeys = envKeys.split(',').map(k => k.trim()).filter(k => k.length > 0);

      if (systemKeys.length === 0) {
        throw new Error("No API Key available. Please add one in Settings.");
      }

      // Retry Logic: Try up to 3 times
      let lastError: any;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          // Load Balancing: Pick a random key from the pool
          const key = systemKeys[Math.floor(Math.random() * systemKeys.length)];
          rawData = await performGeminiCall(key, base64Data, mimeType);
          
          // If successful, break the loop
          break;
        } catch (error: any) {
          lastError = error;
          
          // Check for Rate Limit (429) or Service Unavailable (503)
          // The error object might differ, so we check status or message
          const isRateLimit = error.message?.includes('429') || error.status === 429 || error.message?.includes('Quota');
          
          if (isRateLimit && attempt < 2) {
            console.warn(`Attempt ${attempt + 1} failed (Rate Limit). Retrying with a different key...`);
            // Wait slightly before retrying (Exponential backoff could be added here)
            await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
            continue; 
          }
          
          // If it's not a rate limit error, or we've run out of retries, throw
          throw error;
        }
      }
    }

    // Sanitize and ensure defaults
    const data: AnalysisResult = {
      reconciliation_failed: rawData.reconciliation_failed || false,
      reconciliation_warnings: rawData.reconciliation_warnings || [],
      currency: rawData.currency || "USD",
      transactions: rawData.transactions || [],
      organizationName: rawData.organizationName || "Unknown Organization",
      bankName: rawData.bankName || "Unknown Bank"
    };
    
    return data;
  } catch (error) {
    console.error("Gemini Analysis Error:", error);
    throw error;
  }
};