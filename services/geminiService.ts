
import { GoogleGenAI, HarmCategory, HarmBlockThreshold } from "@google/genai";
import { PDFDocument } from 'pdf-lib';
import { AnalysisResult, Transaction, AnalysisStatistics, CATEGORIES } from "../types";
import { categorizeTransaction } from "./categorizationRules";

// --- CONFIGURATION ---
const MODEL_NAME = 'gemini-2.0-flash'; 
const BATCH_SIZE = 15;       // MAX SPEED: Larger batches reduce HTTP overhead. 15 is safe for output token limits.
const MAX_CONCURRENCY_PER_KEY = 3; // AGGRESSIVE: Flash 2.0 is fast. Run 3 streams per key.
const MIN_REQUEST_INTERVAL_MS = 50; // TURBO: Negligible delay between tasks.

// SHARED STATE: Global coordination for shared-quota keys (Same Project ID)
let globalRateLimitResetTime = 0;

const SYSTEM_INSTRUCTION = `
You are a high-speed financial extraction engine.
TASK: Extract transaction rows from the bank statement.

OUTPUT FORMAT:
Line 1: METADATA|Currency|OrganizationName|BankName
Line 2+: Date|Description|Category|Debit|Credit|Balance

RULES:
1. SEPARATOR: "|" (Pipe).
2. COLUMNS: ALWAYS Provide 6 columns.
   - If Category is unknown, write "Unallocated".
   - If Debit/Credit is empty, write "0.00".
3. NUMBERS: No thousands separators (e.g. 1000.00 not 1,000.00). Keep negative signs.
4. DATES: Copy exactly. Fill down if empty.
5. CONTINUITY: Extract every single row. Do not merge multi-line descriptions if they have distinct amounts.
6. METADATA: If unknown, use "Unknown".
7. END MARKER: ###END###
`;

// --- HELPER: Deep Error Parsing for Google APIs ---
function isRateLimitError(error: any): boolean {
    if (error.error) {
        if (error.error.code === 429) return true;
        if (error.error.status === 'RESOURCE_EXHAUSTED') return true;
    }
    
    const errorStr = JSON.stringify(error, null, 2).toLowerCase();
    
    if (errorStr.includes('429') || 
        errorStr.includes('resource_exhausted') || 
        errorStr.includes('quota') || 
        errorStr.includes('rate limit')) {
        return true;
    }

    if (errorStr.includes('internal server error') || errorStr.includes('500') || errorStr.includes('overloaded')) {
        return true; 
    }

    if (error.status === 429 || error.code === 429) return true;
    if (error.status === 503 || error.code === 503) return true; 
    if (error.status === 500 || error.code === 500) return true;

    const msg = (error.message || error.toString() || "").toLowerCase();
    if (msg.includes('429') || msg.includes('quota') || msg.includes('resource exhausted')) return true;
    if (msg.includes('internal server error') || msg.includes('500')) return true;
    
    return false;
}

// --- HELPER: API Call Wrapper with Global Backoff Awareness ---
async function callGeminiExtract(keys: string[], base64Data: string, mimeType: string, taskIndex: number, retryCount = 0): Promise<string> {
    const keyIndex = (taskIndex + retryCount) % keys.length;
    const currentKey = keys[keyIndex];
    
    if (!currentKey) throw new Error("API Key selection failed.");

    // 1. GLOBAL BACKOFF CHECK
    const now = Date.now();
    if (now < globalRateLimitResetTime) {
        const waitTime = (globalRateLimitResetTime - now) + (Math.random() * 500); 
        await new Promise(resolve => setTimeout(resolve, waitTime));
    }

    try {
        const ai = new GoogleGenAI({ apiKey: currentKey });
        const response = await ai.models.generateContent({
          model: MODEL_NAME,
          contents: {
            parts: [
              { inlineData: { data: base64Data, mimeType: mimeType } },
              { text: "Extract all transactions. Format: METADATA then Date|Description|Category|Debit|Credit|Balance. Ensure every single transaction line is captured." },
            ],
          },
          config: {
            systemInstruction: SYSTEM_INSTRUCTION,
            maxOutputTokens: 65536, 
            temperature: 0,
            safetySettings: [
                { category: HarmCategory.HARM_CATEGORY_HARASSMENT, threshold: HarmBlockThreshold.BLOCK_NONE },
                { category: HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold: HarmBlockThreshold.BLOCK_NONE },
                { category: HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold: HarmBlockThreshold.BLOCK_NONE },
                { category: HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold: HarmBlockThreshold.BLOCK_NONE },
            ]
          },
        });
        
        const text = response.text;
        if (!text) throw new Error("AI returned empty response.");
        return text;

    } catch (error: any) {
        if (isRateLimitError(error)) {
            // 2. SET GLOBAL PENALTY
            const penaltyMs = 2000 + (retryCount * 1000); 
            const newResetTime = Date.now() + penaltyMs;
            
            if (newResetTime > globalRateLimitResetTime) {
                globalRateLimitResetTime = newResetTime;
                console.warn(`[Speed Mode] Rate Limit Hit. Pausing momentarily (${penaltyMs}ms).`);
            }

            const baseDelay = 1000;
            const exponentialDelay = baseDelay * Math.pow(1.5, Math.min(retryCount, 5)); 
            const jitter = Math.random() * 500;
            const delay = exponentialDelay + jitter;

            await new Promise(resolve => setTimeout(resolve, delay));
            return callGeminiExtract(keys, base64Data, mimeType, taskIndex, retryCount + 1);
        }
        throw error;
    }
}

// --- HELPER: PDF Splitting & Concurrency Management ---
async function splitAndProcessPDF(base64: string, keys: string[]): Promise<string> {
    const pdfBytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
    const pdfDoc = await PDFDocument.load(pdfBytes);
    const pageCount = pdfDoc.getPageCount();
    
    // Prepare Tasks
    const chunks: { index: number, pdfBase64: string }[] = [];
    
    // Split PDF into chunks
    for (let i = 0; i < pageCount; i += BATCH_SIZE) {
        if (i % (BATCH_SIZE * 5) === 0) await new Promise(r => setTimeout(r, 0));

        const subDoc = await PDFDocument.create();
        const end = Math.min(i + BATCH_SIZE, pageCount);
        const indices = Array.from({ length: end - i }, (_, k) => i + k);
        const copiedPages = await subDoc.copyPages(pdfDoc, indices);
        copiedPages.forEach(page => subDoc.addPage(page));
        
        const subPdfBytes = await subDoc.saveAsBase64();
        chunks.push({ index: i / BATCH_SIZE, pdfBase64: subPdfBytes });
    }

    // WORKER QUEUE LOGIC
    const maxConcurrency = Math.min(keys.length * MAX_CONCURRENCY_PER_KEY, 16);
    
    const results: string[] = new Array(chunks.length);
    let taskCursor = 0;

    const worker = async (workerId: number) => {
        await new Promise(r => setTimeout(r, workerId * 50));

        while (true) {
            if (taskCursor >= chunks.length) break;
            const currentTask = chunks[taskCursor];
            const taskIndex = taskCursor; 
            taskCursor++;

            try {
                if (taskIndex > 0) await new Promise(r => setTimeout(r, MIN_REQUEST_INTERVAL_MS));
                
                const result = await callGeminiExtract(keys, currentTask.pdfBase64, 'application/pdf', taskIndex);
                results[taskIndex] = result;
            } catch (e: any) {
                console.error(`Batch ${taskIndex} failed.`, e);
                throw new Error(`Analysis failed at Batch ${taskIndex + 1}. Error: ${e.message}`);
            }
        }
    };

    console.log(`[Speed Mode] Launching ${maxConcurrency} workers for ${chunks.length} batches.`);
    
    const workers = Array.from({ length: maxConcurrency }, (_, i) => worker(i));
    await Promise.all(workers);
    
    if (results.some(r => !r)) {
        throw new Error("One or more batches failed to process.");
    }
    
    return results.join("\n");
}

export const analyzeBankStatement = async (base64Data: string, mimeType: string, customApiKey?: string): Promise<AnalysisResult> => {
  const runStats: AnalysisStatistics = {
    total_txns: 0, rule_hits: 0, memory_hits: 0, ai_txns: 0, ai_calls: 0, human_overrides: 0, ai_rate_percent: 0, auto_rate_percent: 0
  };

  const getKeys = (): string[] => {
     let keySource = "";
     if (customApiKey && customApiKey.trim().length > 0) {
         keySource = customApiKey;
     } else {
         try {
            keySource = process.env.API_KEY || "";
         } catch (e) {
            console.warn("process.env is not available");
         }
     }
     return keySource.split(',').map(k => k.trim()).filter(k => k.length > 0);
  };

  const keys = getKeys();
  if (keys.length === 0) throw new Error("No API Key available. Please configure it in Settings.");

  try {
    let rawText = "";
    let isLargeFile = false;

    if (mimeType === 'application/pdf') {
        try {
            const pdfBytes = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
            const pdfDoc = await PDFDocument.load(pdfBytes);
            const pageCount = pdfDoc.getPageCount();
            
            if (pageCount > BATCH_SIZE) {
                isLargeFile = true;
                console.log(`Large File: ${pageCount} pages. Speed Mode Active.`);
                rawText = await splitAndProcessPDF(base64Data, keys);
                runStats.ai_calls = Math.ceil(pageCount / BATCH_SIZE);
            }
        } catch (e: any) {
             console.warn("PDF Processing Check:", e);
             if (e.message && e.message.includes('Analysis failed at Batch')) throw e;
        }
    }

    if (!isLargeFile) {
        runStats.ai_calls = 1;
        const randomStart = Math.floor(Math.random() * keys.length);
        rawText = await callGeminiExtract(keys, base64Data, mimeType, randomStart);
    }

    if (!rawText) throw new Error("AI returned empty response.");

    return processRawResponse(rawText, runStats);

  } catch (error: any) {
    console.error("Gemini Analysis Error:", error);
    throw new Error(error.message || "Analysis failed.");
  }
};

// --- CORE LOGIC: Parsing, Reconciliation & Categorization ---
function processRawResponse(responseText: string, runStats: AnalysisStatistics): AnalysisResult {
    const reconciliation_warnings: string[] = [];
    const error_indices: number[] = [];
    let reconciliation_failed = false;
    
    // Metadata State
    let currency = "USD";
    let organizationName = "Extracted Organization";
    let bankName = "Extracted Bank";
    let metadataLocked = false;

    // --- PARSING LOGIC ---
    let rawRows: any[] = [];
    
    if (!responseText.includes("###END###") && !responseText.includes("Date|")) {
        reconciliation_warnings.push("WARNING: Output markers missing. Verify completeness.");
    }

    const lines = responseText.split(/\r?\n/);
    let lastValidDate = "0000-00-00"; 
    
    for (const line of lines) {
        const cleanLine = line.trim();
        if (!cleanLine) continue;
        if (cleanLine === "###END###") continue;
        if (cleanLine.startsWith("Date|")) continue; 
        if (cleanLine.startsWith("```")) continue; 

        // Metadata Parsing
        if (cleanLine.startsWith("METADATA|")) {
             if (metadataLocked) continue; 

             const metaParts = cleanLine.split('|');
             if (metaParts.length >= 2 && metaParts[1] && metaParts[1] !== "Unknown") {
                 currency = metaParts[1].trim().toUpperCase();
             }
             if (metaParts.length >= 3 && metaParts[2] && metaParts[2] !== "Unknown") {
                 organizationName = metaParts[2].trim();
             }
             if (metaParts.length >= 4 && metaParts[3] && metaParts[3] !== "Unknown") {
                 bankName = metaParts[3].trim();
             }
             
             if (organizationName !== "Extracted Organization") {
                 metadataLocked = true;
             }
             continue;
        }

        // Heuristic Header Skip
        if (cleanLine.includes("Debit|") && cleanLine.includes("Credit|")) continue;

        const parts = cleanLine.split('|').map(p => p.trim());
        
        // RESILIENT PARSING: Allow 5 columns (Date|Desc|Debit|Credit|Balance) by assuming missing category
        if (parts.length >= 5) {
            
            // Check if column 0 looks like a date or part of a date
            // The regex checks for at least one digit, which is typical for dates (DD/MM or YYYY)
            const isDateColValid = /[\d]/.test(parts[0]) || parts[0].toLowerCase().includes('date');
            
            // Indices from the END are safer because description/category are variable length
            const balIdx = parts.length - 1;
            const credIdx = parts.length - 2;
            const debIdx = parts.length - 3;
            
            // Quick check if the last 3 columns contain numbers
            const hasFinancials = /[\d]/.test(parts[debIdx]) || /[\d]/.test(parts[credIdx]) || /[\d]/.test(parts[balIdx]);

            if (!isDateColValid && !hasFinancials) continue;

            // Date Fill-down
            if (!isDateColValid && hasFinancials && lastValidDate !== "0000-00-00") {
                parts[0] = lastValidDate;
            } else if (isDateColValid && /[\d]/.test(parts[0])) {
                lastValidDate = parts[0]; 
            }

            rawRows.push(parts);
        }
    }

    // --- CONVERT TO OBJECTS ---
    const transactionsList: Transaction[] = [];
    const seenHashes = new Set<string>();

    const safeFloat = (val: string): number => {
        if (!val) return 0;
        // Normalize: remove commas, trim, uppercase
        let clean = val.replace(/,/g, '').trim().toUpperCase();
        
        // Strip common textual suffixes/prefixes from OCR/LLM
        clean = clean.replace(/[^0-9.\-()]/g, '');

        // Check for (Value) format
        if (/^\(.*\)$/.test(clean)) {
            // Remove brackets and prepend -
            clean = '-' + clean.replace(/[()]/g, '').trim();
        }
        
        // Check for Value- format
        if (clean.endsWith('-')) {
            clean = '-' + clean.slice(0, -1).trim();
        }

        // Standardize: Remove all non-numeric chars except . and -
        const isNegative = clean.includes('-');
        const numbers = clean.replace(/[^0-9.]/g, '');
        
        const floatVal = parseFloat(numbers) || 0;
        return isNegative ? -floatVal : floatVal;
    };

    rawRows.forEach((row: string[]) => {
        const dateStr = row[0] || "0000-00-00";
        const balanceVal = row[row.length - 1];
        const creditVal = row[row.length - 2];
        const debitVal = row[row.length - 3];
        
        // Category Handling: If only 5 cols, category is missing, so default to Unallocated
        let aiCategory = "Unallocated";
        let descEndIndex = row.length - 3;
        
        if (row.length >= 6) {
             aiCategory = row[row.length - 4];
             descEndIndex = row.length - 4;
        }

        const descParts = row.slice(1, descEndIndex);
        const description = descParts.join(" ") || "Unknown Transaction";
        
        const debit = safeFloat(debitVal);
        const credit = safeFloat(creditVal);
        const balance = safeFloat(balanceVal);

        // 1.5. REVERSAL DETECTION
        let is_reversal = false;
        // Check text
        if (/REVERSAL|REV\b|RET\b|ERR\b/i.test(description)) is_reversal = true;
        // Check negative values in columns
        if (debit < 0 || credit < 0) is_reversal = true;

        // SAFE FILTERING:
        if (/^Page\s+\d+$/i.test(description)) return;
        
        // Strict Footer/Header checks
        if (/^(TOTAL|PAGE TOTAL|SUBTOTAL|TURNOVER|SUMMARY)(\s+(DEBITS?|CREDITS?|FOR|PERIOD|PAGES?))?$/i.test(description)) return;
        if (/^BALANCE\s+C\/F$/i.test(description)) return;
        
        // 1. GLOBAL STRICT DEDUPE
        const hash = `${dateStr}|${description.replace(/\s/g, '').toUpperCase()}|${debit.toFixed(2)}|${credit.toFixed(2)}|${balance.toFixed(2)}`;
        
        if (seenHashes.has(hash)) return;

        // Smart Opening Balance / Brought Forward Logic
        const isOpeningOrBF = /OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F|BAL\s*B\/FWD|PREVIOUS\s*BAL|C\/F|CARRIED\s*FORWARD/i.test(description);
        
        if (isOpeningOrBF) {
            // If it's purely a balance carrier (no debit/credit movement)
            if (Math.abs(debit) < 0.001 && Math.abs(credit) < 0.001) {
                // If it's NOT the first transaction, skip it (it's likely a page break artifact)
                if (transactionsList.length > 0) return;
            }
        } else {
             // Standard row: skip if empty (0 debit, 0 credit)
             if (Math.abs(debit) < 0.001 && Math.abs(credit) < 0.001) return;
        }

        // 2. ADJACENT FINANCIAL DEDUPLICATION
        if (transactionsList.length > 0) {
             const last = transactionsList[transactionsList.length - 1];
             
             const sameDate = last.date === dateStr;
             const sameBalance = Math.abs(last.balance - balance) < 0.01;
             
             if (sameDate && sameBalance) {
                 const sameDebit = Math.abs(last.debit - debit) < 0.01;
                 const sameCredit = Math.abs(last.credit - credit) < 0.01;
                 
                 if (sameDebit && sameCredit) {
                     if (description.length > last.description.length) {
                         last.description = description;
                     }
                     if (last.category === "Unallocated" && aiCategory !== "Unallocated") {
                         last.category = aiCategory;
                     }
                     seenHashes.add(hash);
                     return;
                 }
             }
        }

        seenHashes.add(hash);
        transactionsList.push({
            date: dateStr,
            description: description, 
            category: aiCategory,
            debit: Math.abs(debit),   // Store absolute values
            credit: Math.abs(credit), // Store absolute values
            balance,
            is_reversal
        });
    });

    let uniqueTransactions = transactionsList;

    // --- DIRECTION SANITY CHECK ---
    if (uniqueTransactions.length > 1) {
        for (let i = 1; i < uniqueTransactions.length; i++) {
            const prev = uniqueTransactions[i-1];
            const curr = uniqueTransactions[i];
            
            if (/OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(curr.description)) continue;

            const balDiff = Number((curr.balance - prev.balance).toFixed(2));
            
            // Detection: If Balance Increased, but value is in Debit column -> SWAP
            if (balDiff > 0.01) {
                if (curr.debit > 0 && curr.credit === 0) {
                    if (Math.abs(prev.balance + curr.debit - curr.balance) < 0.1) {
                        curr.credit = curr.debit;
                        curr.debit = 0;
                    }
                }
            }
            // Detection: If Balance Decreased, but value is in Credit column -> SWAP
            if (balDiff < -0.01) {
                if (curr.credit > 0 && curr.debit === 0) {
                    if (Math.abs(prev.balance - curr.credit - curr.balance) < 0.1) {
                        curr.debit = curr.credit;
                        curr.credit = 0;
                    }
                }
            }
        }
    }
    
    // --- RECONCILIATION & ORDER LOGIC ---
    const TOLERANCE = 0.15;
    let forwardMatches = 0;
    let reverseMatches = 0;

    for (let i = 1; i < uniqueTransactions.length; i++) {
        const prev = uniqueTransactions[i-1];
        const curr = uniqueTransactions[i];
        if (/OPENING\s*BAL|BROUGHT\s*FORWARD/i.test(curr.description)) continue;
        
        const std = Math.abs((prev.balance - curr.debit + curr.credit) - curr.balance) < TOLERANCE;
        const swp = Math.abs((prev.balance - curr.credit + curr.debit) - curr.balance) < TOLERANCE;
        
        if (std || swp) forwardMatches++;
    }

    for (let i = 1; i < uniqueTransactions.length; i++) {
        const newer = uniqueTransactions[i-1]; 
        const older = uniqueTransactions[i];   
        if (/OPENING\s*BAL|BROUGHT\s*FORWARD/i.test(newer.description)) continue;
        
        const std = Math.abs((older.balance - newer.debit + newer.credit) - newer.balance) < TOLERANCE;
        const swp = Math.abs((older.balance - newer.credit + newer.debit) - newer.balance) < TOLERANCE;

        if (std || swp) reverseMatches++;
    }

    if (reverseMatches > forwardMatches) {
        uniqueTransactions.reverse();
    }

    // --- GLOBAL POLARITY CHECK ---
    if (uniqueTransactions.length > 2) {
        let scoreStandard = 0;
        let scoreSwapped = 0;

        for (let i = 1; i < uniqueTransactions.length; i++) {
            const prev = uniqueTransactions[i-1];
            const curr = uniqueTransactions[i];
            if (/OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(curr.description)) continue;

            if (Math.abs((prev.balance - curr.debit + curr.credit) - curr.balance) < TOLERANCE) scoreStandard++;
            if (Math.abs((prev.balance - curr.credit + curr.debit) - curr.balance) < TOLERANCE) scoreSwapped++;
        }

        if (scoreSwapped > scoreStandard && scoreSwapped > (uniqueTransactions.length * 0.3)) {
            console.log("Detected Global Column Swap. Automatically fixing...");
            reconciliation_warnings.push("Global Fix: Detected Debit/Credit columns were mixed up. Automatically swapped them.");
            uniqueTransactions.forEach(t => {
                const temp = t.debit;
                t.debit = t.credit;
                t.credit = temp;
            });
        }
    }

    // --- SELF-HEALING: SWAP & RECONSTRUCTION ---
    if (uniqueTransactions.length > 1) {
        let correctionCount = 0;
        let reconstructionCount = 0;
        
        for (let i = 1; i < uniqueTransactions.length; i++) {
            const prev = uniqueTransactions[i-1];
            const curr = uniqueTransactions[i];
            
            if (/OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(curr.description)) continue;

            const expected = Number((prev.balance - curr.debit + curr.credit).toFixed(2));
            const actual = Number(curr.balance.toFixed(2));
            
            if (Math.abs(expected - actual) > TOLERANCE) {
                const swapExpected = Number((prev.balance - curr.credit + curr.debit).toFixed(2));
                
                if (Math.abs(swapExpected - actual) < TOLERANCE) {
                    const temp = curr.debit;
                    curr.debit = curr.credit;
                    curr.credit = temp;
                    correctionCount++;
                } else {
                    const diff = Number((prev.balance - curr.balance).toFixed(2));
                    
                    if (Math.abs(diff) > 0.01) {
                        const hypDebit = diff > 0 ? diff : 0;
                        const hypCredit = diff < 0 ? Math.abs(diff) : 0;
                        curr.debit = hypDebit;
                        curr.credit = hypCredit;
                        reconstructionCount++;
                    }
                }
            }
        }
        
        if (correctionCount > 0) {
            reconciliation_warnings.push(`Auto-swapped ${correctionCount} rows where AI confused Debit/Credit columns.`);
        }
        if (reconstructionCount > 0) {
            reconciliation_warnings.push(`Reconstructed ${reconstructionCount} amounts using running balance data (AI extraction was imprecise).`);
        }
    }

    // Final Check
    if (uniqueTransactions.length > 1) {
       for (let i = 1; i < uniqueTransactions.length; i++) {
          const prev = uniqueTransactions[i-1];
          const curr = uniqueTransactions[i];
          const expectedBalance = prev.balance - curr.debit + curr.credit;
          const diff = Math.abs(expectedBalance - curr.balance);
          
          if (diff > TOLERANCE) {
             if (!/OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(curr.description)) {
                 reconciliation_failed = true;
                 error_indices.push(i);
                 reconciliation_warnings.push(`Row ${i+1} (${curr.date}): Math Error. Expected ${expectedBalance.toFixed(2)}, Found ${curr.balance.toFixed(2)}`);
             }
          }
       }
    }

    // --- CATEGORIZATION ---
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
      error_indices,
      currency: currency,
      transactions: processedTransactions,
      organizationName: organizationName,
      bankName: bankName,
      stats: runStats
    };
}
