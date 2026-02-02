
import { GoogleGenAI, HarmCategory, HarmBlockThreshold } from "@google/genai";
import { PDFDocument } from 'pdf-lib';
import { AnalysisResult, Transaction, AnalysisStatistics, CATEGORIES } from "../types";
import { categorizeTransaction } from "./categorizationRules";

// --- CONFIGURATION ---
// Upgraded to better handle complex table layouts
const MODEL_NAME = 'gemini-2.0-flash'; 

// SPEED & ACCURACY BALANCED:
const PAGE_THRESHOLD = 3; 
const BATCH_SIZE = 3;     
const MAX_CONCURRENCY = 5; 

const SYSTEM_INSTRUCTION = `
You are a forensic bank statement analyzer. 
Your ONLY job is to extract the transaction ledger table into a structured format.

TASK: Extract [Date] [Description] [Debit] [Credit] [Balance].

CRITICAL RULE: REFERENCE VS DESCRIPTION
- Bank statements often have a "Reference" column (Ref, ChqNo, Slip) AND a "Description" column (Narration, Remarks, Details).
- You must **IGNORE** the Reference column. 
- You must **EXTRACT ONLY** the Description/Remarks column.
- DO NOT merge them. 
- If the row is "01-Jan | REF999 | TRF TO JOE", Output: "01-Jan | TRF TO JOE".

COLUMN MAPPING:
1. RowId: Integer.
2. Date: Transaction Date (NOT Value Date).
3. Description: The "Remarks" or "Narration" text ONLY.
4. Debit: Money Out / Withdrawal / Debit.
5. Credit: Money In / Deposit / Credit.
6. Balance: Running Balance.

OUTPUT FORMAT (Pipe Separated):
RowId | Date | Description | Debit | Credit | Balance

NEGATIVE CONSTRAINTS:
- Do NOT output the Reference number in the Description.
- Do NOT output the Value Date column.
- Do NOT output "Chq No".
- Ensure DEBIT values are in the Debit column, and CREDIT values in the Credit column.

FORMATTING:
- Dates: YYYY-MM-DD.
- Financials: Numbers only (no currency symbols). Use 0 for empty.
- Multi-line descriptions: Merge into single line string.

STRUCTURE:
METADATA|2023-10-30|NGN|ABC Corp|Zenith Bank
RowId|Date|Description|Debit|Credit|Balance
1|2023-01-01|Opening Balance|0|0|1000.00
2|2023-01-02|TRF TO JOHN|500.00|0|500.00
###END###
`;

// --- HELPER: API Call Wrapper ---
async function callGeminiExtract(ai: GoogleGenAI, base64Data: string, mimeType: string, retryCount = 0): Promise<string> {
    try {
        const response = await ai.models.generateContent({
          model: MODEL_NAME,
          contents: {
            parts: [
              { inlineData: { data: base64Data, mimeType: mimeType } },
              { text: "Transcribe table. Output 6 columns: RowId|Date|Description|Debit|Credit|Balance. DROPPING the Reference column is mandatory." },
            ],
          },
          config: {
            systemInstruction: SYSTEM_INSTRUCTION,
            maxOutputTokens: 65536, 
            temperature: 0, 
            safetySettings: [
              { category: HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold: HarmBlockThreshold.BLOCK_NONE },
              { category: HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold: HarmBlockThreshold.BLOCK_NONE },
              { category: HarmCategory.HARM_CATEGORY_HARASSMENT, threshold: HarmBlockThreshold.BLOCK_NONE },
              { category: HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold: HarmBlockThreshold.BLOCK_NONE },
            ]
          },
        });
        return response.text || "";
    } catch (error: any) {
        const isRateLimit = error.status === 429 || error.code === 429 || error.message?.includes('429');
        const isServiceUnavailable = error.status === 503 || error.code === 503;

        if ((isRateLimit || isServiceUnavailable) && retryCount < 5) {
            const delay = Math.pow(2, retryCount) * 1000 + (Math.random() * 500);
            await new Promise(resolve => setTimeout(resolve, delay));
            return callGeminiExtract(ai, base64Data, mimeType, retryCount + 1);
        }
        throw error;
    }
}

// --- HELPER: Parallel PDF Processing ---
async function splitAndProcessPDF(base64: string, ai: GoogleGenAI): Promise<string> {
    const pdfBytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
    const pdfDoc = await PDFDocument.load(pdfBytes);
    const pageCount = pdfDoc.getPageCount();
    
    const tasks: (() => Promise<string>)[] = [];

    for (let i = 0; i < pageCount; i += BATCH_SIZE) {
        tasks.push(async () => {
            const subDoc = await PDFDocument.create();
            const end = Math.min(i + BATCH_SIZE, pageCount);
            const indices = Array.from({ length: end - i }, (_, k) => i + k);
            const copiedPages = await subDoc.copyPages(pdfDoc, indices);
            copiedPages.forEach(page => subDoc.addPage(page));
            
            const subPdfBytes = await subDoc.saveAsBase64();
            return callGeminiExtract(ai, subPdfBytes, 'application/pdf');
        });
    }

    const results: string[] = new Array(tasks.length);
    let executing = 0;
    let index = 0;

    const executeNext = async (): Promise<void> => {
        if (index >= tasks.length) return;
        const currentIndex = index++;
        executing++;
        try {
            results[currentIndex] = await tasks[currentIndex]();
        } catch (e) {
            throw e;
        } finally {
            executing--;
        }
        if (index < tasks.length) {
            await executeNext();
        }
    };

    const initialWorkers = [];
    for (let i = 0; i < Math.min(MAX_CONCURRENCY, tasks.length); i++) {
        initialWorkers.push(executeNext());
    }
    await Promise.all(initialWorkers);

    return results.join("\n");
}

export const analyzeBankStatement = async (base64Data: string, mimeType: string, customApiKey?: string): Promise<AnalysisResult> => {
  const runStats: AnalysisStatistics = {
    total_txns: 0, rule_hits: 0, memory_hits: 0, ai_txns: 0, ai_calls: 0, human_overrides: 0, ai_rate_percent: 0, auto_rate_percent: 0
  };

  const getKeys = () => {
     if (customApiKey) return [customApiKey];
     let envKeys = "";
     try {
        envKeys = process.env.API_KEY || "";
     } catch (e) {
        console.warn("process.env is not available");
     }
     return envKeys.split(',').map(k => k.trim()).filter(k => k.length > 0);
  };
  const keys = getKeys();
  if (keys.length === 0) throw new Error("No API Key available. Please configure it in Settings.");
  const key = keys[0];

  try {
    const ai = new GoogleGenAI({ apiKey: key });
    
    let rawText = "";
    let isLargeFile = false;

    if (mimeType === 'application/pdf') {
        try {
            const pdfBytes = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
            const pdfDoc = await PDFDocument.load(pdfBytes);
            const pageCount = pdfDoc.getPageCount();
            
            if (pageCount > PAGE_THRESHOLD) {
                isLargeFile = true;
                rawText = await splitAndProcessPDF(base64Data, ai);
                runStats.ai_calls = Math.ceil(pageCount / BATCH_SIZE);
            }
        } catch (e) {
            console.warn("Failed to read PDF page count, defaulting to single-shot.", e);
        }
    }

    if (!isLargeFile) {
        runStats.ai_calls = 1;
        rawText = await callGeminiExtract(ai, base64Data, mimeType);
    }

    if (!rawText) throw new Error("AI returned empty response.");

    // Initial Parsing
    const partialResult = parseRawText(rawText);
    
    // Initial Reconciliation (Auto-Detect Logic)
    return reconcileLedger(partialResult.transactions, false, runStats, partialResult.metadata);

  } catch (error: any) {
    if (error.message?.includes('429')) {
        throw new Error("Gemini API Rate Limit Exceeded. Please try again in a minute.");
    }
    throw new Error(error.message || "Analysis failed.");
  }
};

// --- CLIENT-SIDE RECONCILIATION ENGINE ---
export const reconcileLedger = (
    transactions: Transaction[], 
    forceSwap: boolean, 
    stats: AnalysisStatistics = { total_txns: 0, rule_hits: 0, memory_hits: 0, ai_txns: 0, ai_calls: 0, human_overrides: 0, ai_rate_percent: 0, auto_rate_percent: 0 },
    metadata: { currency: string, organizationName: string, bankName: string }
): AnalysisResult => {
    
    // 1. Deep Copy
    let uniqueTransactions: Transaction[] = JSON.parse(JSON.stringify(transactions));
    const reconciliation_warnings: string[] = [];
    const error_indices: number[] = [];
    let reconciliation_failed = false;

    // 2. Apply Forced Swap if requested
    if (forceSwap) {
        reconciliation_warnings.push("NOTICE: Debit/Credit columns manually swapped by user.");
        uniqueTransactions.forEach(t => {
            const temp = t.debit;
            t.debit = t.credit;
            t.credit = temp;
        });
    }

    // 3. Logic Detection (Global Swap Check)
    if (!forceSwap && uniqueTransactions.length > 2) {
        const TOLERANCE = 0.05;
        const scores = { forwardNormal: 0, forwardSwap: 0, reverseNormal: 0, reverseSwap: 0 };
        
        for (let i = 1; i < uniqueTransactions.length; i++) {
            const A = uniqueTransactions[i-1];
            const B = uniqueTransactions[i];
            if (/OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(B.description)) continue;

            // Forward Normal: Prev(A) - Deb(B) + Cred(B) = Curr(B)
            if (Math.abs((A.balance - B.debit + B.credit) - B.balance) < TOLERANCE) scores.forwardNormal++;
            // Forward Swap: Prev(A) - Cred(B) + Deb(B) = Curr(B)
            if (Math.abs((A.balance - B.credit + B.debit) - B.balance) < TOLERANCE) scores.forwardSwap++;
            // Reverse
            if (Math.abs((B.balance - A.debit + A.credit) - A.balance) < TOLERANCE) scores.reverseNormal++;
            if (Math.abs((B.balance - A.credit + A.debit) - A.balance) < TOLERANCE) scores.reverseSwap++;
        }

        const maxScore = Math.max(scores.forwardNormal, scores.forwardSwap, scores.reverseNormal, scores.reverseSwap);
        
        if (maxScore > 0) {
            if (scores.reverseNormal === maxScore || scores.reverseSwap === maxScore) {
                uniqueTransactions.reverse();
            }
            if (scores.forwardSwap === maxScore || scores.reverseSwap === maxScore) {
                reconciliation_warnings.push("NOTICE: Auto-detected swapped columns globally. Correcting...");
                uniqueTransactions.forEach(t => {
                    const temp = t.debit;
                    t.debit = t.credit;
                    t.credit = temp;
                });
            }
        }
    }

    // 4. Ensure Opening Balance is Top
    const hasOpening = uniqueTransactions.findIndex(t => /OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(t.description));
    if (hasOpening > 0) {
        const item = uniqueTransactions.splice(hasOpening, 1)[0];
        uniqueTransactions.unshift(item);
    }

    // 5. Self-Healing Opening Balance
    if (uniqueTransactions.length > 1) {
        const first = uniqueTransactions[0];
        const second = uniqueTransactions[1];
        const isOpening = /OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(first.description);
        
        const theoreticalOpening = second.balance + second.debit - second.credit;
        if (isOpening && Math.abs(first.balance - theoreticalOpening) > 1.0) {
            first.balance = theoreticalOpening;
            first.description += " (Auto-Corrected)";
            reconciliation_warnings.push(`NOTICE: Opening Balance adjusted to match ledger math.`);
        }
    }

    // 6. Final Validation & ROW-LEVEL SELF HEALING
    const FINAL_TOLERANCE = 0.10; 
    if (uniqueTransactions.length > 1) {
       for (let i = 1; i < uniqueTransactions.length; i++) {
          const prev = uniqueTransactions[i-1];
          const curr = uniqueTransactions[i];
          if (/OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(curr.description)) continue;

          // A. Standard Math: Prev - Debit + Credit = Current
          const expectedNormal = prev.balance - curr.debit + curr.credit;
          const diffNormal = Math.abs(expectedNormal - curr.balance);

          if (diffNormal > FINAL_TOLERANCE) {
              // B. Try Swapping Logic: Prev - Credit(as Deb) + Debit(as Cred) = Current
              // We test if swapping the current row's Dr/Cr values fixes the math
              const expectedSwap = prev.balance - curr.credit + curr.debit;
              const diffSwap = Math.abs(expectedSwap - curr.balance);

              if (diffSwap <= FINAL_TOLERANCE) {
                  // FIX FOUND: The values were swapped for this specific row
                  const temp = curr.debit;
                  curr.debit = curr.credit;
                  curr.credit = temp;
                  // We treat this as a warning, not a failure, because we fixed it.
                  reconciliation_warnings.push(`Row ${i+1}: Auto-corrected swapped Debit/Credit values based on balance check.`);
              } else {
                  // C. Still Failing
                  reconciliation_failed = true;
                  error_indices.push(i);
              }
          }
       }
    }

    // 7. Re-Categorize
    stats.rule_hits = 0; stats.memory_hits = 0; stats.ai_txns = 0;
    const processedTransactions = uniqueTransactions.map(t => {
      t.category = ""; 
      const classified = categorizeTransaction(t);
      if (classified.decision_source === 'RULE') stats.rule_hits++;
      else if (classified.decision_source === 'MEMORY') stats.memory_hits++;
      else stats.ai_txns++;
      return classified;
    });

    return {
        reconciliation_failed,
        reconciliation_warnings,
        error_indices,
        currency: metadata.currency,
        transactions: processedTransactions,
        organizationName: metadata.organizationName,
        bankName: metadata.bankName,
        stats
    };
};

// --- RAW PARSER ---
function parseRawText(text: string) {
    let currency = "USD";
    let organizationName = "Extracted Organization";
    let bankName = "Extracted Bank";
    
    const detectCurrency = (str: string): string | null => {
        if (/NIGERIAN\s*NAIRA|NAIRA|NGN|₦/i.test(str)) return "NGN";
        if (/DOLLAR|USD|\$/i.test(str)) return "USD";
        if (/POUND|GBP|£/i.test(str)) return "GBP";
        if (/EURO|EUR|€/i.test(str)) return "EUR";
        return null;
    };

    let rawRows: any[] = [];
    const lines = text.split(/\r?\n/);
    let lastValidDate = "0000-00-00";

    for (const line of lines) {
        const cleanLine = line.trim();
        if (!cleanLine || cleanLine.startsWith("```") || cleanLine === "###END###" || cleanLine === "###PAGE_BREAK###") continue;

        if (cleanLine.startsWith("METADATA|")) {
             const metaParts = cleanLine.split('|');
             if (metaParts.length >= 3) {
                 const detected = detectCurrency(metaParts[2].trim());
                 if (detected) currency = detected;
             }
             if (metaParts.length >= 4) organizationName = metaParts[3].trim();
             if (metaParts.length >= 5) bankName = metaParts[4].trim();
             continue;
        }
        if (cleanLine.startsWith("Row")) continue;

        const parts = cleanLine.split('|').map(p => p.trim());
        if (parts.length >= 5) {
            const dateStr = parts[1];
            const startsWithNumber = /^\d+$/.test(parts[0]);
            const isDateColValid = /[\d]/.test(dateStr) || dateStr.toLowerCase().includes('date');
            const hasFinancials = /[\d]/.test(parts[parts.length-1]);

            if (/^(Date|Value|Desc|Debit|Credit)/i.test(parts[1])) continue;

            if (startsWithNumber && hasFinancials) {
                 // ok
            } else if (!isDateColValid && !hasFinancials) {
                 continue;
            }

            if (!isDateColValid && hasFinancials && lastValidDate !== "0000-00-00") {
                if (!parts[1] || parts[1].length < 5) parts[1] = lastValidDate;
            } else if (isDateColValid && /[\d]/.test(parts[1])) {
                lastValidDate = parts[1];
            }
            rawRows.push(parts);
        }
    }

    const transactions: Transaction[] = [];
    const safeFloat = (val: string) => {
        if (!val) return 0;
        return parseFloat(val.replace(/[^0-9.-]/g, '')) || 0;
    };

    rawRows.forEach((row) => {
        const dateStr = row[1] || "0000-00-00";
        let description = "";
        
        // --- IMPROVED DESCRIPTION PARSING ---
        // Constraint: We want to DROP Reference.
        // If the AI respected the prompt, we have [Row, Date, Desc, Dr, Cr, Bal] (6 cols).
        // If the AI failed and output [Row, Date, Ref, Desc, Dr, Cr, Bal] (7 cols).
        // Or [Row, Date, Ref, ValDate, Desc, Dr, Cr, Bal] (8 cols).
        // STRATEGY: Take the LAST non-financial column as the Description.
        
        if (row.length === 6) {
             description = row[2];
        } else if (row.length > 6) {
             // We assume the numbers are at the end: [ ... , Deb, Cred, Bal ]
             // So Description is likely at index row.length - 4
             // Example: Row(0), Date(1), Ref(2), Desc(3), Deb(4), Cred(5), Bal(6) -> Length 7.
             // We want index 3. 
             // Formula: length (7) - 3 (financials) - 1 (desc position) = 3.
             // Wait, safeFloat uses row.length-1, -2, -3. 
             // So the col *before* Debit is row.length - 4.
             const descIndex = row.length - 4;
             if (descIndex >= 2) {
                 description = row[descIndex];
             } else {
                 // Fallback if structure is weird, join middle but skip 2 (Ref)
                 description = row.slice(3, row.length - 3).join(" ");
             }
        } else {
             // Fallback
             description = row.slice(2, row.length - 3).join(" ");
        }

        // --- SCRUB REFERENCE NUMBERS (Safety Net) ---
        // 1. Remove leading 6+ digits (e.g., "0000213554 NIP...")
        description = description.replace(/^[\d]{6,}\s+/, "");
        // 2. Remove "REF xxx" pattern
        description = description.replace(/^(?:REF|CHQ|SLIP|NO)[:\.\s]+[A-Z0-9]+\s+/i, "");
        // 3. Remove long alphanumeric start (typical of bank refs)
        description = description.replace(/^[A-Z0-9]{12,}\s+/, "");

        const debit = safeFloat(row[row.length - 3]);
        const credit = safeFloat(row[row.length - 2]);
        const balance = safeFloat(row[row.length - 1]);

        // Filter trivial rows
        if (Math.abs(debit) < 0.001 && Math.abs(credit) < 0.001 && !/OPENING|CLOSING|B\/F/i.test(description)) return;

        transactions.push({
            date: dateStr,
            description: description || "Unknown",
            category: "Unallocated",
            debit, credit, balance,
            is_reversal: false
        });
    });

    return { 
        transactions, 
        metadata: { currency, organizationName, bankName } 
    };
}
