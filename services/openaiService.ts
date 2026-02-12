import { Transaction } from '../types';

interface OpenAICategoryResponse {
    results: {
        description: string;
        category: string;
        confidence: number;
    }[];
}

const SYSTEM_PROMPT = `You are an expert accounting assistant.
Your task is to categorize bank transactions into standard accounting categories.
Strictly use the following categories:
- Bank Charges
- Operating Income
- Repairs & Maintenance
- Salaries & Wages
- Staff Welfare
- Transport & Logistics
- Office Rent / Lease
- Administrative Expenses
- Inter-Account / Treasury Transfer
- WHT Receivable
- Interest Income
- Capital Expenditure (CWIP)
- Unallocated

Return a JSON object with a "results" array containing the category and confidence for each description provided.`;

export const categorizeWithOpenAI = async (
    transactions: Transaction[],
    apiKey: string,
    onProgress?: (msg: string) => void
): Promise<Transaction[]> => {
    if (!apiKey) throw new Error("OpenAI API Key is missing");

    // optimize: only send unique descriptions to save tokens
    const uniqueDescriptions = Array.from(new Set(transactions.map(t => t.description)));
    const chunks = chunkArray(uniqueDescriptions, 50); // Batch size 50
    const descriptionMap = new Map<string, { category: string, confidence: number }>();

    let processedCount = 0;

    for (const chunk of chunks) {
        if (onProgress) onProgress(`AI Categorizing ${processedCount}/${uniqueDescriptions.length}...`);

        try {
            const response = await fetch('https://api.openai.com/v1/chat/completions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey}`
                },
                body: JSON.stringify({
                    model: "gpt-4o-mini", // Cost effective & fast
                    messages: [
                        { role: "system", content: SYSTEM_PROMPT },
                        { role: "user", content: JSON.stringify(chunk) }
                    ],
                    response_format: { type: "json_object" },
                    temperature: 0.1
                })
            });

            if (!response.ok) {
                const err = await response.json();
                console.error("OpenAI API Error:", err);
                // Continue without crashing, just log
                continue;
            }

            const data = await response.json();
            const content = data.choices[0].message.content;
            if (content) {
                const parsed: OpenAICategoryResponse = JSON.parse(content);
                parsed.results.forEach(r => {
                    descriptionMap.set(r.description, { category: r.category, confidence: r.confidence });
                });
            }

        } catch (e) {
            console.error("Batch failed:", e);
        }
        processedCount += chunk.length;
    }

    // Apply back to transactions
    return transactions.map(t => {
        const aiResult = descriptionMap.get(t.description);
        if (aiResult) {
            return {
                ...t,
                category: aiResult.category,
                confidence: aiResult.confidence
            };
        }
        return t;
    });
};

function chunkArray<T>(array: T[], size: number): T[][] {
    const result = [];
    for (let i = 0; i < array.length; i += size) {
        result.push(array.slice(i, i + size));
    }
    return result;
}
