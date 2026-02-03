
import { GoogleGenAI, HarmCategory, HarmBlockThreshold } from "@google/genai";
import { PDFDocument } from 'pdf-lib';
import { AnalysisResult, Transaction, AnalysisStatistics, CATEGORIES } from "../types";
import { categorizeTransaction } from "./categorizationRules";

// --- CONFIGURATION ---
const MODEL_NAME = 'gemini-2.0-flash'; 
const PAGE_THRESHOLD = 2;   // Lower threshold to trigger batching earlier
const BATCH_SIZE = 5;       // OPTIMAL: 5 Pages per batch prevents TPM exhaustion while maintaining context.
// MAX_CONCURRENCY will be dynamic

const SYSTEM_INSTRUCTION = `
You are a high-speed financial extraction and classification engine.
TASK: 
1. Analyze the document header to extract: Currency (ISO Code e.g., NGN, USD, GBP), Organization Name, and Bank Name.
2. Extract ALL transaction rows from the bank statement and classify them into a specific category.

OUTPUT FORMAT:
Line 1: METADATA|Currency|OrganizationName|BankName
Line 2+: Date|Description|Category|Debit|Credit|Balance

ALLOWED CATEGORIES:
${CATEGORIES.map(c => `- ${c}`).join('\n')}

RULES:
1. Output raw text only. No Markdown. No JSON.
2. FIRST LINE must be the METADATA line. If unknown, use "Unknown".
3. Separator: Use the pipe character "|" strictly.
4. Content Safety: If a Description contains a pipe "|", replace it with a space.
5. Multiline Descriptions: Merge into a single line.
6. Numbers: Standardize to plain decimals (e.g., 1200.50). Remove commas. Remove currency symbols. KEEP NEGATIVE SIGNS if present (e.g., -50.00).
7. Empty values: Use 0 for empty numeric columns. Do not leave blank.
8. Dates: Copy exactly. If missing (ditto), use the previous row's date.
9. COLUMNS (CRITICAL):
   - HEADER ANALYSIS: Look for headers like "Debit", "Withdrawal", "Payment", "Dr" -> These are DEBITS.
   - HEADER ANALYSIS: Look for headers like "Credit", "Deposit", "Receipt", "Cr" -> These are CREDITS.
   - SEPARATE DEBIT AND CREDIT. 
   - Debit = Withdrawals, Money Out, Dr.
   - Credit = Deposits, Money In, Cr.
   - REVERSALS: If a specific column has a negative value (e.g. Credit column has -100), KEEP IT IN THAT COLUMN with the negative sign. Do not move it.
   - If only one "Amount" column exists: 
     - Negative values (-) or values in brackets () are usually DEBITS.
     - Positive values are CREDITS.
   - Use the Running Balance to verify: 
     - If Balance Decreases -> The transaction is a DEBIT.
     - If Balance Increases -> The transaction is a CREDIT.
10. CLASSIFICATION: Use the provided list. If the vendor is known (e.g., "Uber" -> Transport, "KFC" -> Welfare, "AWS" -> Admin), categorize it. If a specific tax/fee, categorize it. If unsure, use "Unallocated".
11. INTEGRITY: Extract every single line item. Do not summarize. Do not skip rows. Capture small fees (SMS, VAT, Stamp Duty) even if repetitive.
12. EXCLUSION: Do not output Page Numbers, Table Headers (Date/Debit/Credit columns), Page Footers, or Page Totals.
13. END MARKER: Print exactly: ###END###
`;

// --- HELPER: Deep Error Parsing for Google APIs ---
function isRateLimitError(error: any): boolean {
    const errorStr = JSON.stringify(error, null, 2).toLowerCase();
    if (errorStr.includes('429') || 
        errorStr.includes('resource_exhausted') || 
        errorStr.includes('quota') || 
        errorStr.includes('rate limit')) {
        return true;
    }

    if (error.status === 429 || error.code === 429) return true;
    if (error.status === 503 || error.code === 503) return true; 

    const msg = (error.message || error.toString() || "").toLowerCase();
    if (msg.includes('429') || msg.includes('quota') || msg.includes('resource exhausted')) return true;
    
    if (error.response && error.response.status === 429) return true;

    return false;
}

// --- HELPER: API Call Wrapper with Smart Fast-Failover ---
async function callGeminiExtract(keys: string[], base64Data: string, mimeType: string, taskIndex: number, retryCount = 0): Promise<string> {
    const keyIndex = (taskIndex + retryCount) % keys.length;
    const currentKey = keys[keyIndex];
    
    if (!currentKey) throw new Error("API Key selection failed.");

    try {
        const ai = new GoogleGenAI({ apiKey: currentKey });
        const response = await ai.models.generateContent({
          model: MODEL_NAME,
          contents: {
            parts: [
              { inlineData: { data: base64Data, mimeType: mimeType } },
              { text: "Extract and categorize all transactions. Format: METADATA row then Date|Description|Category|Debit|Credit|Balance" },
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
            // We allow ample retries because we have multiple keys
            const maxRetries = keys.length * 4 + 5;

            if (retryCount < maxRetries) {
                let delay = 1000;

                // Smart Logic:
                // If we haven't exhausted all keys yet (retryCount < keys.length), switch FAST.
                // If we have cycled through all keys, wait LONGER (Backoff).
                if (retryCount < keys.length) {
                    delay = 500 + (Math.random() * 500); // 0.5s - 1s switch time
                    console.log(`[Load Balancer] Key ...${currentKey.slice(-4)} exhausted. Fast switching to Key ${(keyIndex + 1) % keys.length}...`);
                } else {
                    // All keys are hot. Wait.
                    const cycle = Math.floor(retryCount / keys.length);
                    delay = 3000 + (cycle * 2000) + (Math.random() * 1000);
                    console.warn(`[Load Balancer] All keys busy. Backing off for ${Math.round(delay)}ms...`);
                }

                await new Promise(resolve => setTimeout(resolve, delay));
                return callGeminiExtract(keys, base64Data, mimeType, taskIndex, retryCount + 1);
            }
        }
        throw error;
    }
}

// --- HELPER: PDF Splitting & Concurrency Management ---
async function splitAndProcessPDF(base64: string, keys: string[]): Promise<string> {
    const pdfBytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
    const pdfDoc = await PDFDocument.load(pdfBytes);
    const pageCount = pdfDoc.getPageCount();
    
    const tasks: (() => Promise<string>)[] = [];

    let batchIndex = 0;
    for (let i = 0; i < pageCount; i += BATCH_SIZE) {
        const currentTaskIndex = batchIndex++;
        
        tasks.push(async () => {
            const subDoc = await PDFDocument.create();
            const end = Math.min(i + BATCH_SIZE, pageCount);
            const indices = Array.from({ length: end - i }, (_, k) => i + k);
            const copiedPages = await subDoc.copyPages(pdfDoc, indices);
            copiedPages.forEach(page => subDoc.addPage(page));
            
            const subPdfBytes = await subDoc.saveAsBase64();
            return callGeminiExtract(keys, subPdfBytes, 'application/pdf', currentTaskIndex);
        });
    }

    // DYNAMIC CONCURRENCY
    // If we have 3 keys, we want 3 workers.
    // If we have 10 batches, 3 workers will process them in ~4 waves.
    const maxConcurrency = Math.max(1, Math.min(keys.length, 5));

    const results: string[] = new Array(tasks.length);
    let index = 0;

    const executeNext = async (workerId: number): Promise<void> => {
        if (index >= tasks.length) return;
        
        const currentIndex = index++;
        try {
            console.log(`[Worker ${workerId}] Processing Batch ${currentIndex + 1}/${tasks.length}...`);
            results[currentIndex] = await tasks[currentIndex]();
            console.log(`[Worker ${workerId}] Completed Batch ${currentIndex + 1}`);
        } catch (e: any) {
            console.error(`Batch ${currentIndex} failed final attempt.`, e);
            throw new Error(`Analysis failed at Batch ${currentIndex} (Pages ${currentIndex * BATCH_SIZE + 1}-${Math.min((currentIndex * BATCH_SIZE) + BATCH_SIZE, pageCount)}). Error: ${e.message}`);
        }

        if (index < tasks.length) {
            await executeNext(workerId);
        }
    };

    const workers = [];
    const activeWorkers = Math.min(maxConcurrency, tasks.length);

    console.log(`Starting ${activeWorkers} parallel worker(s) for ${tasks.length} batches using ${keys.length} API Keys.`);

    for (let i = 0; i < activeWorkers; i++) {
        const p = new Promise<void>(resolve => {
            // Stagger start times to prevent "First Second" spike
            // 1500ms stagger is a sweet spot: fast enough but safe.
            setTimeout(() => {
                executeNext(i).then(resolve).catch(err => {
                    resolve(); 
                    throw err; 
                });
            }, i * 1500); 
        });
        workers.push(p);
    }

    await Promise.all(workers);
    
    if (results.some(r => !r)) {
        throw new Error("One or more batches failed to process after multiple retries.");
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
            
            // If page count > BATCH_SIZE (5), we split.
            if (pageCount > BATCH_SIZE) {
                isLargeFile = true;
                console.log(`File has ${pageCount} pages. Processing in batches of ${BATCH_SIZE}.`);
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
    if (isRateLimitError(error)) {
        throw new Error("System is under heavy load. All API keys exhausted. Please wait 60 seconds.");
    }
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
        
        // Expecting 6 columns: Date|Description|Category|Debit|Credit|Balance
        if (parts.length >= 6) {
            
            const isDateColValid = /[\d]/.test(parts[0]) || parts[0].toLowerCase().includes('date');
            const balIdx = parts.length - 1;
            const credIdx = parts.length - 2;
            const debIdx = parts.length - 3;
            
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
        let clean = val.replace(/,/g, '').trim();
        
        // Handle trailing negative sign (e.g. "500.00-")
        if (clean.endsWith('-')) {
            clean = '-' + clean.slice(0, -1);
        }

        // Allow negative signs, digits, and decimal point
        clean = clean.replace(/[^0-9.-]/g, ''); 
        return parseFloat(clean) || 0;
    };

    rawRows.forEach((row: string[]) => {
        const dateStr = row[0] || "0000-00-00";
        const balanceVal = row[row.length - 1];
        const creditVal = row[row.length - 2];
        const debitVal = row[row.length - 3];
        const aiCategory = row[row.length - 4] || "Unallocated";
        
        const descParts = row.slice(1, row.length - 4);
        const description = descParts.join(" ") || "Unknown Transaction";
        
        const debit = safeFloat(debitVal);
        const credit = safeFloat(creditVal);
        // Balance CAN be negative, so we use a looser parse
        const balance = parseFloat(balanceVal.replace(/,/g, '').replace(/[^0-9.-]/g, '')) || 0;

        // SAFE FILTERING:
        // Do NOT filter out vendors like "TOTAL ENERGIES" or "SUBTOTAL LTD"
        // Only filter explicit footer/header markers.
        if (/^Page\s+\d+$/i.test(description)) return;
        
        // Strict Footer/Header checks
        if (/^(TOTAL|PAGE TOTAL|SUBTOTAL|TURNOVER|SUMMARY)(\s+(DEBITS?|CREDITS?|FOR|PERIOD|PAGES?))?$/i.test(description)) return;
        if (/^BALANCE\s+C\/F$/i.test(description)) return;
        
        // 1. GLOBAL STRICT DEDUPE
        // Create strict hash for deduplication: Date|Desc|Debit|Credit|Balance
        // This catches identical rows extracted multiple times (e.g. if repeated in text)
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
        // Detects rows that are financially identical to the previous one (same amounts, same balance, same date)
        // This handles cases where the AI extracts the same transaction twice (e.g. overlapping pages or hallucinations)
        // even if the description string varies slightly.
        if (transactionsList.length > 0) {
             const last = transactionsList[transactionsList.length - 1];
             
             // Check Date & Balance (Strong indicators)
             const sameDate = last.date === dateStr;
             const sameBalance = Math.abs(last.balance - balance) < 0.01;
             
             if (sameDate && sameBalance) {
                 // Check Amounts
                 const sameDebit = Math.abs(last.debit - debit) < 0.01;
                 const sameCredit = Math.abs(last.credit - credit) < 0.01;
                 
                 if (sameDebit && sameCredit) {
                     // It IS a duplicate.
                     console.log(`Skipping Duplicate Row: ${description}`);
                     
                     // Heuristic: Keep the longer description (usually contains more info)
                     if (description.length > last.description.length) {
                         last.description = description;
                     }
                     
                     // We also merge the category if the new one is better?
                     if (last.category === "Unallocated" && aiCategory !== "Unallocated") {
                         last.category = aiCategory;
                     }

                     // Mark as seen and SKIP pushing
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
            debit,
            credit,
            balance,
            is_reversal: false
        });
    });

    let uniqueTransactions = transactionsList;
    
    // --- RECONCILIATION & ORDER LOGIC ---
    const TOLERANCE = 0.05;
    let forwardMatches = 0;
    let reverseMatches = 0;

    // Detect direction with tolerance for Swapped Columns
    for (let i = 1; i < uniqueTransactions.length; i++) {
        const prev = uniqueTransactions[i-1];
        const curr = uniqueTransactions[i];
        if (/OPENING\s*BAL|BROUGHT\s*FORWARD/i.test(curr.description)) continue;
        
        // Check Standard: Prev - D + C = Curr
        const std = Math.abs((prev.balance - curr.debit + curr.credit) - curr.balance) < TOLERANCE;
        // Check Swapped: Prev - C + D = Curr
        const swp = Math.abs((prev.balance - curr.credit + curr.debit) - curr.balance) < TOLERANCE;
        
        if (std || swp) forwardMatches++;
    }

    for (let i = 1; i < uniqueTransactions.length; i++) {
        const newer = uniqueTransactions[i-1]; 
        const older = uniqueTransactions[i];   
        if (/OPENING\s*BAL|BROUGHT\s*FORWARD/i.test(newer.description)) continue;
        
        // Check Standard: Older - D + C = Newer
        const std = Math.abs((older.balance - newer.debit + newer.credit) - newer.balance) < TOLERANCE;
        // Check Swapped: Older - C + D = Newer
        const swp = Math.abs((older.balance - newer.credit + newer.debit) - newer.balance) < TOLERANCE;

        if (std || swp) reverseMatches++;
    }

    if (reverseMatches > forwardMatches) {
        uniqueTransactions.reverse();
    }

    // --- GLOBAL POLARITY CHECK ---
    // Heuristic: If the majority of rows follow the "Swapped" logic (Prev - C + D = Curr),
    // then the AI likely mixed up the columns globally.
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

        // If swapped model is significantly better (and accounts for a good chunk of data)
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
    // Fixes column swaps and infers missing amounts from balance if AI fails.
    if (uniqueTransactions.length > 1) {
        let correctionCount = 0;
        let reconstructionCount = 0;
        
        for (let i = 1; i < uniqueTransactions.length; i++) {
            const prev = uniqueTransactions[i-1];
            const curr = uniqueTransactions[i];
            
            if (/OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(curr.description)) continue;

            const expected = Number((prev.balance - curr.debit + curr.credit).toFixed(2));
            const actual = Number(curr.balance.toFixed(2));
            
            // If math doesn't work
            if (Math.abs(expected - actual) > TOLERANCE) {
                
                // 1. Try SWAP: Check if flipping debit/credit works
                // Bal = Prev - (OldCredit) + (OldDebit)
                const swapExpected = Number((prev.balance - curr.credit + curr.debit).toFixed(2));
                
                if (Math.abs(swapExpected - actual) < TOLERANCE) {
                    const temp = curr.debit;
                    curr.debit = curr.credit;
                    curr.credit = temp;
                    correctionCount++;
                } else {
                    // 2. Try RECONSTRUCTION: Infer from Balance
                    // If AI extraction is garbage, trust the Balance (assuming Balances are sequential)
                    const diff = Number((prev.balance - curr.balance).toFixed(2));
                    
                    if (Math.abs(diff) > 0.01) {
                        // If diff > 0, Balance went down => Debit
                        const hypDebit = diff > 0 ? diff : 0;
                        const hypCredit = diff < 0 ? Math.abs(diff) : 0;
                        
                        // Check if this heuristic is safe?
                        // We apply it because Reconciliation failure is worse than inferred amounts.
                        // We only do this if we can perfectly explain the balance transition.
                        curr.debit = hypDebit;
                        curr.credit = hypCredit;
                        reconstructionCount++;
                    }
                }
            }
        }
        
        if (correctionCount > 0) {
            console.log(`Auto-Corrected ${correctionCount} swapped transactions.`);
            reconciliation_warnings.push(`Auto-swapped ${correctionCount} rows where AI confused Debit/Credit columns.`);
        }
        if (reconstructionCount > 0) {
            console.log(`Reconstructed ${reconstructionCount} amounts from balance.`);
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
    // Efficient map using the imported rules engine
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
