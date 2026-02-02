
import { GoogleGenAI, HarmCategory, HarmBlockThreshold } from "@google/genai";
import { PDFDocument } from 'pdf-lib';
import { AnalysisResult, Transaction, AnalysisStatistics, CATEGORIES } from "../types";
import { categorizeTransaction } from "./categorizationRules";

// --- CONFIGURATION ---
const MODEL_NAME = 'gemini-2.0-flash'; 
const PAGE_THRESHOLD = 3;   // Lowered to 3 to trigger batching sooner for reliability
const BATCH_SIZE = 6;       // Reduced batch size to ~6 pages to ensure no rows are skipped by AI
const MAX_CONCURRENCY = 3;  // Maps 1:1 with standard 3-key rotation for max speed

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
6. Numbers: Plain numbers (e.g., 1200.50). Remove commas.
7. Empty values: Use 0 for empty numeric columns.
8. Dates: Copy exactly. If missing (ditto), use the previous row's date.
9. CLASSIFICATION: Use the provided list. If the vendor is known (e.g., "Uber" -> Transport, "KFC" -> Welfare, "AWS" -> Admin), categorize it. If a specific tax/fee, categorize it. If unsure, use "Unallocated".
10. INTEGRITY: Extract every single line item. Do not summarize. Do not skip rows. Capture small fees (SMS, VAT, Stamp Duty) even if repetitive.
11. EXCLUSION: Do not output Page Numbers, Table Headers (Date/Debit/Credit columns), Page Footers, or Page Totals.
12. END MARKER: Print exactly: ###END###
`;

// --- HELPER: API Call Wrapper with Load Balancing ---
async function callGeminiExtract(keys: string[], base64Data: string, mimeType: string, taskIndex: number, retryCount = 0): Promise<string> {
    // LOAD BALANCING STRATEGY:
    // 1. Initial Distribution: taskIndex ensures parallel workers start on different keys.
    // 2. Failover Rotation: retryCount shifts the index to the next key if the current one fails.
    const keyIndex = (taskIndex + retryCount) % keys.length;
    const currentKey = keys[keyIndex];
    
    // Safety check for empty keys
    if (!currentKey) throw new Error("API Key selection failed during load balancing.");

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
        if (!text) {
             console.warn(`[Key ${keyIndex}] Gemini returned empty text. Candidates:`, response.candidates);
             throw new Error("AI returned empty response (Content might be blocked or model failed).");
        }
        return text;

    } catch (error: any) {
        // Robust Error Detection
        const isRateLimit = 
            error.status === 429 || 
            error.code === 429 || 
            error.message?.includes('429') ||
            error.message?.includes('Quota') ||
            error.message?.includes('Resource exhausted') ||
            error.toString().includes('429');
            
        const isServiceUnavailable = error.status === 503 || error.code === 503;
        
        // If we have multiple keys, we can be more aggressive with retries (switch key)
        const maxRetries = keys.length > 1 ? 12 : 5;

        if ((isRateLimit || isServiceUnavailable) && retryCount < maxRetries) {
            let delay = 0;
            
            if (keys.length > 1) {
                // LOAD BALANCER ACTIVE: Quick switch to next key (500ms + jitter)
                delay = 500 + (Math.random() * 500);
                console.warn(`[Load Balancer] Key ending ...${currentKey.slice(-4)} limited. Switching to next key in ${Math.round(delay)}ms...`);
            } else {
                // SINGLE KEY MODE: Standard exponential backoff
                delay = Math.pow(2, retryCount) * 2000 + (Math.random() * 1000);
                console.warn(`Gemini Rate Limit. Retrying in ${Math.round(delay)}ms (Attempt ${retryCount + 1}/${maxRetries})`);
            }

            await new Promise(resolve => setTimeout(resolve, delay));
            // Recurse with incremented retryCount, which automatically selects the next key
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
    
    const tasks: (() => Promise<string>)[] = [];

    let batchIndex = 0;
    for (let i = 0; i < pageCount; i += BATCH_SIZE) {
        // Capture specific index for this batch to ensure consistent key mapping
        const currentTaskIndex = batchIndex++;
        
        tasks.push(async () => {
            const subDoc = await PDFDocument.create();
            const end = Math.min(i + BATCH_SIZE, pageCount);
            const indices = Array.from({ length: end - i }, (_, k) => i + k);
            const copiedPages = await subDoc.copyPages(pdfDoc, indices);
            copiedPages.forEach(page => subDoc.addPage(page));
            
            const subPdfBytes = await subDoc.saveAsBase64();
            // Pass keys and the task index to enable load balancing
            return callGeminiExtract(keys, subPdfBytes, 'application/pdf', currentTaskIndex);
        });
    }

    // CONCURRENCY QUEUE
    const results: string[] = new Array(tasks.length);
    let index = 0;

    const executeNext = async (workerId: number): Promise<void> => {
        if (index >= tasks.length) return;
        const currentIndex = index++;
        try {
            results[currentIndex] = await tasks[currentIndex]();
        } catch (e) {
            console.error(`Batch ${currentIndex} failed`, e);
            results[currentIndex] = ""; // Fail gracefully for that batch
        }
        if (index < tasks.length) {
            await executeNext(workerId);
        }
    };

    const workers = [];
    const activeWorkers = Math.min(MAX_CONCURRENCY, tasks.length);

    for (let i = 0; i < activeWorkers; i++) {
        // Stagger start slightly to prevent burst trigger
        const p = new Promise<void>(resolve => {
            setTimeout(() => {
                executeNext(i).then(resolve);
            }, i * 300); // Reduced stagger time significantly because we are load balancing
        });
        workers.push(p);
    }

    await Promise.all(workers);
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
     
     // Split by comma to support multiple keys for load balancing
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
            
            if (pageCount > PAGE_THRESHOLD) {
                isLargeFile = true;
                console.log(`Large File Detected (${pageCount} pages). Switching to Load Balanced Batch Mode.`);
                rawText = await splitAndProcessPDF(base64Data, keys);
                runStats.ai_calls = Math.ceil(pageCount / BATCH_SIZE);
            }
        } catch (e) {
            console.warn("Failed to read PDF page count, defaulting to single-shot.", e);
        }
    }

    if (!isLargeFile) {
        runStats.ai_calls = 1;
        // Random start index for single files to distribute load if processing multiple single files
        const randomStart = Math.floor(Math.random() * keys.length);
        rawText = await callGeminiExtract(keys, base64Data, mimeType, randomStart);
    }

    if (!rawText) throw new Error("AI returned empty response.");

    return processRawResponse(rawText, runStats);

  } catch (error: any) {
    if (error.message?.includes('429') || error.message?.includes('Resource exhausted') || error.message?.includes('Quota')) {
         throw new Error("System is experiencing heavy load. Automatic failover attempted but all keys are busy. Please try again in 1 minute.");
    }
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
        const clean = val.replace(/[^0-9.-]/g, '');
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
        const balance = safeFloat(balanceVal);

        if (/^Page \d+/.test(description)) return;
        if (/^(TOTAL|PAGE TOTAL|SUBTOTAL|TURNOVER|SUMMARY)/i.test(description)) return;
        
        // Create strict hash for deduplication: Date|Desc|Debit|Credit|Balance
        // Using toFixed(2) to normalize float variations
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
            // If it HAS movement, treat it as a valid adjustment/transaction
        } else {
             // Standard row: skip if empty (0 debit, 0 credit)
             if (Math.abs(debit) < 0.001 && Math.abs(credit) < 0.001) return;
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
    
    // --- RECONCILIATION LOGIC ---
    const TOLERANCE = 0.05;
    let forwardMatches = 0;
    let reverseMatches = 0;

    for (let i = 1; i < uniqueTransactions.length; i++) {
        const prev = uniqueTransactions[i-1];
        const curr = uniqueTransactions[i];
        if (/OPENING\s*BAL|BROUGHT\s*FORWARD/i.test(curr.description)) continue;
        if (Math.abs((prev.balance - curr.debit + curr.credit) - curr.balance) < TOLERANCE) forwardMatches++;
    }

    for (let i = 1; i < uniqueTransactions.length; i++) {
        const newer = uniqueTransactions[i-1]; 
        const older = uniqueTransactions[i];   
        if (/OPENING\s*BAL|BROUGHT\s*FORWARD/i.test(newer.description)) continue;
        if (Math.abs((older.balance - newer.debit + newer.credit) - newer.balance) < TOLERANCE) reverseMatches++;
    }

    if (reverseMatches > forwardMatches) {
        uniqueTransactions.reverse();
    }

    // Phantom Row Elimination
    if (uniqueTransactions.length > 2) {
        const indexesToRemove = new Set<number>();
        for (let i = 1; i < uniqueTransactions.length - 1; i++) {
            const prev = uniqueTransactions[i-1];
            const curr = uniqueTransactions[i];
            
            if (/OPENING\s*BAL|BROUGHT\s*FORWARD/i.test(curr.description)) continue;

            const expectedCurr = prev.balance - curr.debit + curr.credit;
            const diffCurr = Math.abs(expectedCurr - curr.balance);
            
            if (diffCurr > TOLERANCE) {
                const next = uniqueTransactions[i+1];
                if (/OPENING\s*BAL|BROUGHT\s*FORWARD/i.test(next.description)) continue;
                const expectedNext = prev.balance - next.debit + next.credit;
                const diffNext = Math.abs(expectedNext - next.balance);
                if (diffNext < TOLERANCE) indexesToRemove.add(i);
            }
        }
        if (indexesToRemove.size > 0) {
            uniqueTransactions = uniqueTransactions.filter((_, idx) => !indexesToRemove.has(idx));
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
