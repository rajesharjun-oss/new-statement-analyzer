
import { GoogleGenAI, Type, Schema } from "@google/genai";
import { AnalysisResult, Transaction, CATEGORIES, AnalysisStatistics } from "../types";
import { categorizeTransaction } from "./categorizationRules";

// --- CONFIGURATION ---
const PRIMARY_MODEL = 'gemini-3-flash-preview';
const FALLBACK_MODEL = 'gemini-3-pro-preview';

// OPTIMIZATION: 
// BATCH_SIZE_PAGES: 1 page per request for maximum granularity.
// MAX_CONCURRENCY: 10 requests in parallel to maintain high throughput.
const BATCH_SIZE_PAGES = 1; 
const MAX_CONCURRENCY = 10;

const BASE_RULES = `
RECONCILIATION RULES (STRICT):
1. **TRANSCRIPTION MODE ONLY**:
   - Your job is to **TRANSCRIBE** the table exactly as it looks visually.
   - Do NOT interpret meanings. Do NOT categorize. 
   - **Visual Fidelity**: Map columns 1:1 based on visual position.

2. **Visual Grid Mapping (8 Columns)**:
   - **Col 1: RowIndex** (Sequential number 1, 2, 3...)
   - **Col 2: Date** (The leftmost date)
   - **Col 3: Description** (The main text block)
   - **Col 4: Reference** (Cheque numbers, transaction codes)
   - **Col 5: Value Date** (Date appearing between Description/Ref and Amounts. If empty, output "EMPTY")
   - **Col 6: Debit** (Withdrawal amount. If empty, output "0.00")
   - **Col 7: Credit** (Deposit amount. If empty, output "0.00")
   - **Col 8: Balance** (The rightmost running total)

3. **ANCHORING STRATEGY (PREVENT COLUMN SHIFT)**:
   - **RIGHT-TO-LEFT SCAN**: 
     1. Identify the **Balance** (Last number on the right).
     2. Move Left -> Check for **Credit**. If there is a large visual gap or whitespace, it is "0.00".
     3. Move Left -> Check for **Debit**.
   - **MUTUAL EXCLUSIVITY**: In 99% of bank statements, a row has EITHER a Debit OR a Credit. It rarely has both.
     - If you find a number in the Debit column, the Credit column MUST be "0.00".
     - If you find a number in the Credit column, the Debit column MUST be "0.00".
   - **EMPTY CELL HANDLING**: Explicitly look for the visual gap. If a column is blank, output "0.00" or "EMPTY".

4. **Record Integrity**:
   - Extract **EVERY** row that contains a date and an amount.
   - **INCLUDE** Opening Balance / Closing Balance rows if they have a date and a balance.
   - Do not merge multi-line descriptions if the second line has a date or amount.
   - Do not skip rows with "0.00" amounts if they carry a running balance.
`;

// 1. METADATA PROMPT
const METADATA_SYSTEM_INSTRUCTION = `
You are a bank statement analyzer.
Task: Analyze the document structure and return metadata.
Return JSON: { "page_count": number, "organizationName": string, "bankName": string, "currency": string }.
`;

const METADATA_SCHEMA: Schema = {
  type: Type.OBJECT,
  properties: {
    page_count: { type: Type.INTEGER },
    organizationName: { type: Type.STRING },
    bankName: { type: Type.STRING },
    currency: { type: Type.STRING },
  },
  required: ["page_count", "organizationName", "bankName", "currency"],
};

// 2. EXTRACTION PROMPT
const getExtractionInstruction = (startPage: number, endPage: number) => `
${BASE_RULES}

TASK:
Extract transactions from **PAGE ${startPage} to PAGE ${endPage}**.

OUTPUT FORMAT:
Return **Pure Pipe-Delimited Text** (CSV style with '|').
NO JSON. NO Markdown code blocks.

**Header**:
RowIndex|Date|Description|Reference|ValueDate|Debit|Credit|Balance

**Example**:
1|2025-01-01|TRANSFER FROM JOHN|REF123|01-Jan|0.00|5000.00|15000.00
2|2025-01-02|ATM WITHDRAWAL|N/A|EMPTY|200.00|0.00|14800.00

INSTRUCTIONS:
- **Date**: Format as YYYY-MM-DD if possible, otherwise keep original.
- **Amounts**: Remove commas. (e.g., 10,000.00 -> 10000.00).
- **Description**: Keep on one line.
`;

// --- HELPER: API CALL WITH FALLBACK & BUDGET ---

async function callGemini(apiKey: string, base64Data: string, mimeType: string, promptText: string, config: any = {}) {
  const ai = new GoogleGenAI({ apiKey });

  // 1. Attempt Primary Model (Flash)
  try {
    const primaryConfig = {
      ...config,
      // Increased thinking budget slightly to handle complex layouts better while staying fast
      thinkingConfig: { thinkingBudget: 2048 }, 
      maxOutputTokens: 65536, 
    };

    const response = await ai.models.generateContent({
      model: PRIMARY_MODEL,
      contents: {
        parts: [
          { inlineData: { data: base64Data, mimeType: mimeType } },
          { text: promptText },
        ],
      },
      config: primaryConfig,
    });
    return response.text || "";
  } catch (primaryError: any) {
    console.warn(`Primary model (${PRIMARY_MODEL}) failed. Switching to fallback (${FALLBACK_MODEL}).`, primaryError);

    // 2. Attempt Fallback Model (Pro)
    try {
      const fallbackConfig = {
        ...config,
        maxOutputTokens: 65536,
      };

      const response = await ai.models.generateContent({
        model: FALLBACK_MODEL,
        contents: {
          parts: [
            { inlineData: { data: base64Data, mimeType: mimeType } },
            { text: promptText },
          ],
        },
        config: fallbackConfig,
      });
      return response.text || "";
    } catch (fallbackError: any) {
       console.error("Fallback model also failed.", fallbackError);
       throw new Error(`Analysis failed: ${primaryError.message} (Primary) / ${fallbackError.message} (Fallback)`);
    }
  }
}

// --- MAIN SERVICE ---

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
    // STEP 1: GET METADATA
    runStats.ai_calls++;
    
    const metaResponseText = await callGemini(key, base64Data, mimeType, "Analyze the file metadata.", {
      systemInstruction: METADATA_SYSTEM_INSTRUCTION,
      responseMimeType: "application/json",
      responseSchema: METADATA_SCHEMA,
      temperature: 0,
    });

    let metadata;
    try {
        metadata = JSON.parse(metaResponseText.replace(/^```json\s*/, '').replace(/\s*```$/, ''));
    } catch (e) {
        console.warn("JSON parse error on metadata, using defaults.");
        metadata = { page_count: 1, currency: "USD", organizationName: "Unknown", bankName: "Unknown" };
    }
    const totalPages = metadata.page_count || 1;

    // STEP 2: PARALLEL BATCH EXTRACTION
    const batches = [];
    for (let i = 1; i <= totalPages; i += BATCH_SIZE_PAGES) {
      batches.push({
        start: i,
        end: Math.min(i + BATCH_SIZE_PAGES - 1, totalPages)
      });
    }

    const allRawTransactions: any[] = [];
    const failedBatches: string[] = [];

    for (let i = 0; i < batches.length; i += MAX_CONCURRENCY) {
        const currentBatchGroup = batches.slice(i, i + MAX_CONCURRENCY);
        
        const promises = currentBatchGroup.map(async (batch) => {
            runStats.ai_calls++;
            try {
                const batchText = await callGemini(key, base64Data, mimeType, `Extract transactions for pages ${batch.start} to ${batch.end}.`, {
                    systemInstruction: getExtractionInstruction(batch.start, batch.end),
                    temperature: 0,
                });
                return parseCsvTransactions(batchText);
            } catch (err) {
                console.error(`Batch ${batch.start}-${batch.end} failed:`, err);
                failedBatches.push(`${batch.start}-${batch.end}`);
                return [];
            }
        });

        const results = await Promise.all(promises);
        results.forEach(txns => allRawTransactions.push(...txns));
    }

    // STEP 3: DEDUPLICATION & CLEANUP
    const dedupMap = new Map<string, Transaction>();

    allRawTransactions.forEach(t => {
        // Robust Fingerprint: Date + Amounts + Balance + Partial Description
        const cleanDesc = (t.description || "").replace(/[^a-zA-Z0-9]/g, '').toUpperCase().substring(0, 15);
        // Using toFixed(2) handles floating point jitter
        const fingerprint = `${t.date}|${t.debit.toFixed(2)}|${t.credit.toFixed(2)}|${t.balance.toFixed(2)}|${cleanDesc}`;
        
        const existing = dedupMap.get(fingerprint);
        if (!existing) {
            dedupMap.set(fingerprint, t);
        } else {
            // Keep the one with more information (longer description)
            if (t.description.length > existing.description.length) {
                dedupMap.set(fingerprint, t);
            }
        }
    });

    const uniqueTransactions = Array.from(dedupMap.values());
    uniqueTransactions.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

    // STEP 4: CATEGORIZATION
    const processedTransactions = uniqueTransactions.map(t => {
      runStats.total_txns++;
      const classified = categorizeTransaction(t);
      
      if (classified.decision_source === 'RULE') runStats.rule_hits++;
      else if (classified.decision_source === 'MEMORY') runStats.memory_hits++;
      else runStats.ai_txns++;
      
      return classified;
    });

    // Compute Rates
    if (runStats.total_txns > 0) {
      runStats.ai_rate_percent = parseFloat(((runStats.ai_txns / runStats.total_txns) * 100).toFixed(2));
      runStats.auto_rate_percent = parseFloat((((runStats.rule_hits + runStats.memory_hits) / runStats.total_txns) * 100).toFixed(2));
    }

    const warnings: string[] = [];
    if (metadata.page_count > 1 && processedTransactions.length < 5) {
       warnings.push("Transaction count seems low for the number of pages detected.");
    }
    if (failedBatches.length > 0) {
        warnings.push(`Extraction failed for page ranges: ${failedBatches.join(', ')}.`);
    }

    return {
      reconciliation_failed: failedBatches.length > 0,
      reconciliation_warnings: warnings,
      currency: metadata.currency || "USD",
      transactions: processedTransactions,
      organizationName: metadata.organizationName || "Unknown Org",
      bankName: metadata.bankName || "Unknown Bank",
      stats: runStats
    };

  } catch (error: any) {
    console.error("Gemini Analysis Error:", error);
    throw new Error(error.message || "Analysis failed during batch processing.");
  }
};

// --- INTERNAL PARSER ---

function parseCsvTransactions(text: string): Transaction[] {
  const transactions: Transaction[] = [];
  const lines = text.trim().split('\n');
  
  lines.forEach(line => {
    const cleanLine = line.trim();
    if (!cleanLine || cleanLine.startsWith('RowIndex|') || cleanLine.startsWith('Header|') || cleanLine.startsWith('---')) return;
    
    const parts = cleanLine.split('|');
    // We expect 8 cols: RowIndex|Date|Desc|Ref|ValDate|Debit|Credit|Balance
    // But sometimes pipe might be missing at the end. We need at least up to Credit (col 7).
    if (parts.length < 6) return; 

    const dateStr = parts[1]?.trim() || '';
    const description = parts[2]?.trim() || '';
    
    // FILTER 1: Admin Rows
    // Modified to ALLOW "Opening Balance" and "Closing Balance" and "B/F" rows as per user requirement.
    // Only exclude pure summation lines that duplicate data like "Total Turnover".
    const strictAdminRegex = /^(Total\s+(Turnover|Debits?|Credits?)|Page\s*Total)/i;
    
    if (strictAdminRegex.test(description)) return;
    
    // FILTER 2: Page numbers
    if (/^Page \d+ of \d+$/i.test(description)) return;

    const parseNum = (str: string) => {
      if (!str || str === 'EMPTY') return 0;
      // aggressively remove internal spaces often found in OCR numbers e.g. "1 000.00"
      // But we must be careful not to merge unrelated numbers if the AI hallucinated. 
      // Assuming pipe delimiter works, `str` is one cell.
      const clean = str.replace(/\s+/g, '').replace(/[^\d.\-()]/g, '');
      
      const digitsOnly = clean.replace(/[.\-()]/g, '');
      if (digitsOnly.length > 15) return 0; // Guard against reference numbers being parsed as amounts
      
      if (clean.startsWith('(') && clean.endsWith(')')) {
         return -1 * parseFloat(clean.replace(/[()]/g, ''));
      }
      return parseFloat(clean) || 0;
    };

    // Index 5 is Debit, 6 is Credit, 7 is Balance
    const debit = parseNum(parts[5]);
    const credit = parseNum(parts[6]);
    const balance = parseNum(parts[7]);

    // FILTER 3: Drop rows ONLY if both amounts are strictly 0
    // This removes spacer rows but keeps rows that might have one side 0.00
    // However, if it's an Opening Balance, it might have 0 debit/credit but a valid balance.
    const isBalanceRow = /Balance/i.test(description) || /B\/F/i.test(description);
    if (!isBalanceRow && Math.abs(debit) < 0.001 && Math.abs(credit) < 0.001) return;

    // FILTER 4: Date Validation (Relaxed)
    // If the date is totally invalid, check if we have a valid Description + Balance + Amount.
    // If so, use the original string or a placeholder.
    // This prevents dropping valid rows just because the date format is weird (e.g. "JAN 01").
    let finalDate = dateStr;
    const hasValidDate = /[\d]{1,4}[-/\.][\w\d]{1,3}[-/\.][\d]{1,4}/.test(dateStr);
    
    if (!hasValidDate) {
        // If it's a balance row, we can be lenient with the date
        if (!isBalanceRow && (Math.abs(debit) < 0.001 && Math.abs(credit) < 0.001)) return; 
        // Keep the original string if regex fails but row looks valid otherwise
    }

    const txn: Transaction = {
        date: finalDate,
        description: description,
        category: 'Unallocated', 
        reference: parts[3]?.trim() || '',
        debit,
        credit,
        balance,
        is_reversal: false, 
    };
    
    transactions.push(txn);
  });
  return transactions;
}
