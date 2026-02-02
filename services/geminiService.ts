
import { GoogleGenAI } from "@google/genai";
import { PDFDocument } from 'pdf-lib';
import { AnalysisResult, Transaction, AnalysisStatistics, CATEGORIES } from "../types";
import { categorizeTransaction } from "./categorizationRules";

// --- CONFIGURATION ---
const MODEL_NAME = 'gemini-2.0-flash'; // High speed, good reasoning
const PAGE_THRESHOLD = 15; // Files larger than this use Batch Mode

// OPTIMIZATION: RAW TEXT STREAM MODE WITH CLASSIFICATION
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

// --- HELPER: API Call Wrapper ---
async function callGeminiExtract(ai: GoogleGenAI, base64Data: string, mimeType: string): Promise<string> {
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
        thinkingConfig: { thinkingBudget: 0 } 
      },
    });
    return response.text || "";
}

// --- HELPER: PDF Splitting ---
async function splitAndProcessPDF(base64: string, ai: GoogleGenAI): Promise<string> {
    const pdfBytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
    const pdfDoc = await PDFDocument.load(pdfBytes);
    const pageCount = pdfDoc.getPageCount();
    
    // REDUCED BATCH SIZE: 2 pages per batch to ensure maximum fidelity on dense statements
    const BATCH_SIZE = 2; 

    const promises: Promise<string>[] = [];

    for (let i = 0; i < pageCount; i += BATCH_SIZE) {
        const subDoc = await PDFDocument.create();
        const end = Math.min(i + BATCH_SIZE, pageCount);
        // Copy pages i through end-1
        const indices = Array.from({ length: end - i }, (_, k) => i + k);
        const copiedPages = await subDoc.copyPages(pdfDoc, indices);
        copiedPages.forEach(page => subDoc.addPage(page));
        
        const subPdfBytes = await subDoc.saveAsBase64();
        
        // Add artificial delay to prevent rate limits (simulated queue)
        const delay = i * 250; 
        
        promises.push(
            new Promise(resolve => setTimeout(resolve, delay))
                .then(() => callGeminiExtract(ai, subPdfBytes, 'application/pdf'))
        );
    }

    const results = await Promise.all(promises);
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
        // Safe access to process.env for browser environments
        envKeys = process.env.API_KEY || "";
     } catch (e) {
        console.warn("process.env is not available in this environment");
     }
     return envKeys.split(',').map(k => k.trim()).filter(k => k.length > 0);
  };
  const keys = getKeys();
  if (keys.length === 0) throw new Error("No API Key available. Please configure it in Settings.");
  const key = keys[0];

  try {
    const ai = new GoogleGenAI({ apiKey: key });
    
    // --- ROUTER LOGIC ---
    let rawText = "";
    let isLargeFile = false;

    if (mimeType === 'application/pdf') {
        try {
            // Lightweight check of page count
            const pdfBytes = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
            const pdfDoc = await PDFDocument.load(pdfBytes);
            const pageCount = pdfDoc.getPageCount();
            
            if (pageCount > PAGE_THRESHOLD) {
                isLargeFile = true;
                console.log(`Large File Detected (${pageCount} pages). Switching to Batch Mode.`);
                rawText = await splitAndProcessPDF(base64Data, ai);
                // Approx calculation for stats
                runStats.ai_calls = Math.ceil(pageCount / 2);
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

    return processRawResponse(rawText, runStats);

  } catch (error: any) {
    console.error("Gemini Analysis Error:", error);
    throw new Error(error.message || "Analysis failed.");
  }
};

// --- CORE LOGIC: Parsing, Reconciliation & Categorization ---
// This ensures identical behavior for both Single and Batch modes
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
    
    // Check for truncation
    if (!responseText.includes("###END###") && !responseText.includes("Date|")) {
        reconciliation_warnings.push("WARNING: Output markers missing. Verify completeness.");
    }

    const lines = responseText.split(/\r?\n/);
    let lastValidDate = "0000-00-00"; // State for date fill-down
    
    for (const line of lines) {
        const cleanLine = line.trim();
        if (!cleanLine) continue;
        if (cleanLine === "###END###") continue;
        if (cleanLine.startsWith("Date|")) continue; 
        if (cleanLine.startsWith("```")) continue; 

        // Metadata Parsing (Prioritize first valid occurrence)
        if (cleanLine.startsWith("METADATA|")) {
             if (metadataLocked) continue; 

             const metaParts = cleanLine.split('|');
             // METADATA|Currency|Org|Bank
             if (metaParts.length >= 2 && metaParts[1] && metaParts[1] !== "Unknown") {
                 currency = metaParts[1].trim().toUpperCase();
             }
             if (metaParts.length >= 3 && metaParts[2] && metaParts[2] !== "Unknown") {
                 organizationName = metaParts[2].trim();
             }
             if (metaParts.length >= 4 && metaParts[3] && metaParts[3] !== "Unknown") {
                 bankName = metaParts[3].trim();
             }
             
             // Lock metadata if we found a valid Organization Name
             if (organizationName !== "Extracted Organization") {
                 metadataLocked = true;
             }
             continue;
        }

        // HEURISTIC: Skip Table Headers explicitly
        if (cleanLine.includes("Debit|") && cleanLine.includes("Credit|")) continue;

        const parts = cleanLine.split('|').map(p => p.trim());
        
        // Expecting 6 columns now: Date|Description|Category|Debit|Credit|Balance
        if (parts.length >= 6) {
            
            const isDateColValid = /[\d]/.test(parts[0]) || parts[0].toLowerCase().includes('date');
            
            // Indices: Balance is last, Credit is last-1, Debit is last-2, Category is last-3
            const balIdx = parts.length - 1;
            const credIdx = parts.length - 2;
            const debIdx = parts.length - 3;
            // Category is at debIdx - 1
            
            const hasFinancials = /[\d]/.test(parts[debIdx]) || /[\d]/.test(parts[credIdx]) || /[\d]/.test(parts[balIdx]);

            if (!isDateColValid && !hasFinancials) {
                continue; // It's likely a header or garbage line
            }

            // --- DATE FILL-DOWN LOGIC ---
            if (!isDateColValid && hasFinancials && lastValidDate !== "0000-00-00") {
                parts[0] = lastValidDate;
            } else if (isDateColValid && /[\d]/.test(parts[0])) {
                lastValidDate = parts[0]; 
            }

            rawRows.push(parts);
        }
    }

    // --- CONVERT TO OBJECTS ---
    // REMOVED GLOBAL DEDUPLICATION to ensure 100% record capture (e.g. 1144 rows).
    const transactionsList: Transaction[] = [];

    const safeFloat = (val: string): number => {
        if (!val) return 0;
        const clean = val.replace(/[^0-9.-]/g, '');
        return parseFloat(clean) || 0;
    };

    rawRows.forEach((row: string[]) => {
        const dateStr = row[0] || "0000-00-00";
        // New Column Mapping
        const balanceVal = row[row.length - 1];
        const creditVal = row[row.length - 2];
        const debitVal = row[row.length - 3];
        const aiCategory = row[row.length - 4] || "Unallocated";
        
        // Description is everything between Date and Category
        const descParts = row.slice(1, row.length - 4);
        const description = descParts.join(" ") || "Unknown Transaction";
        
        const debit = safeFloat(debitVal);
        const credit = safeFloat(creditVal);
        const balance = safeFloat(balanceVal);

        if (/^Page \d+/.test(description)) return;
        
        // STRICT TOTALS FILTER: Exclude summary rows that often break reconciliation
        if (/^(TOTAL|PAGE TOTAL|SUBTOTAL|TURNOVER|SUMMARY)/i.test(description)) return;

        // Expanded Balance Row Logic: Include Closing, Total, C/F
        const isBalanceRow = /B\/F|BROUGHT FORWARD|OPENING BAL|CLOSING BAL|CARRIED FORWARD|C\/F|C\/D|TOTAL/i.test(description);
        
        // Filter out zero value rows UNLESS they are structural balance rows
        if (!isBalanceRow && Math.abs(debit) < 0.001 && Math.abs(credit) < 0.001) return;

        // SEQUENTIAL STUTTER CHECK: Only skip if EXACTLY same as previous row (AI hallucination)
        const prev = transactionsList[transactionsList.length - 1];
        if (prev) {
             const isDuplicate = 
                prev.date === dateStr &&
                Math.abs(prev.debit - debit) < 0.001 &&
                Math.abs(prev.credit - credit) < 0.001 &&
                Math.abs(prev.balance - balance) < 0.001 &&
                prev.description === description;
             
             if (isDuplicate) return;
        }

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
    
    // --- ORDER DETECTION & RECONCILIATION ---
    const TOLERANCE = 0.05;
    let forwardMatches = 0;
    let reverseMatches = 0;

    // Test Forward
    for (let i = 1; i < uniqueTransactions.length; i++) {
        const prev = uniqueTransactions[i-1];
        const curr = uniqueTransactions[i];
        if (/OPENING\s*BAL/i.test(curr.description)) continue;
        
        const expected = prev.balance - curr.debit + curr.credit;
        if (Math.abs(expected - curr.balance) < TOLERANCE) forwardMatches++;
    }

    // Test Reverse
    for (let i = 1; i < uniqueTransactions.length; i++) {
        const newer = uniqueTransactions[i-1]; 
        const older = uniqueTransactions[i];   
        
        if (/OPENING\s*BAL/i.test(newer.description)) continue;

        const calc = older.balance - newer.debit + newer.credit;
        if (Math.abs(calc - newer.balance) < TOLERANCE) reverseMatches++;
    }

    if (reverseMatches > forwardMatches) {
        uniqueTransactions.reverse();
    }

    uniqueTransactions.sort((a, b) => {
        const isOpeningA = /OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(a.description);
        const isOpeningB = /OPENING\s*BAL|BROUGHT\s*FORWARD|B\/F/i.test(b.description);
        if (isOpeningA && !isOpeningB) return -1;
        if (!isOpeningA && isOpeningB) return 1;
        return 0;
    });

    // --- PHANTOM ROW ELIMINATION (SELF-HEALING) ---
    // If Row A -> Row B fails, but Row A -> Row C succeeds, Row B is an extraction artifact (phantom).
    if (uniqueTransactions.length > 2) {
        const indexesToRemove = new Set<number>();
        // Iterate checking for "Island" errors
        for (let i = 1; i < uniqueTransactions.length - 1; i++) {
            const prev = uniqueTransactions[i-1];
            const curr = uniqueTransactions[i];
            
            // If current is an Opening Balance, it resets the chain, so don't check prev
            if (/OPENING\s*BAL/i.test(curr.description)) continue;

            const expectedCurr = prev.balance - curr.debit + curr.credit;
            const diffCurr = Math.abs(expectedCurr - curr.balance);
            
            if (diffCurr > TOLERANCE) {
                // Current row fails. Does Next row connect to Prev?
                // Next balance should be Prev Balance - Next Debit + Next Credit (Skipping Curr)
                const next = uniqueTransactions[i+1];
                
                // If next is Opening Balance, we can't skip current to connect to it.
                if (/OPENING\s*BAL/i.test(next.description)) continue;

                const expectedNext = prev.balance - next.debit + next.credit;
                const diffNext = Math.abs(expectedNext - next.balance);
                
                if (diffNext < TOLERANCE) {
                    // YES: Skipping 'curr' restores the chain. 'curr' is a phantom row.
                    indexesToRemove.add(i);
                }
            }
        }
        
        if (indexesToRemove.size > 0) {
            console.log(`Auto-Removed ${indexesToRemove.size} phantom rows to fix reconciliation.`);
            uniqueTransactions = uniqueTransactions.filter((_, idx) => !indexesToRemove.has(idx));
        }
    }

    // --- FINAL RECONCILIATION ENGINE ---
    if (uniqueTransactions.length > 1) {
       for (let i = 1; i < uniqueTransactions.length; i++) {
          const prev = uniqueTransactions[i-1];
          const curr = uniqueTransactions[i];
          
          const expectedBalance = prev.balance - curr.debit + curr.credit;
          const diff = Math.abs(expectedBalance - curr.balance);
          
          if (diff > TOLERANCE) {
             if (!/OPENING\s*BAL/i.test(curr.description)) {
                 reconciliation_failed = true;
                 error_indices.push(i);
                 reconciliation_warnings.push(`Row ${i+1} (${curr.date}): Math Error. Expected ${expectedBalance.toFixed(2)}, Found ${curr.balance.toFixed(2)}`);
             }
          }
       }
    }

    // --- CATEGORIZATION ENGINE ---
    const processedTransactions = uniqueTransactions.map(t => {
      runStats.total_txns++;
      // t now contains 'category' populated by Gemini
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
