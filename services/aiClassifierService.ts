import { AnalysisTemplate, ClassifiedTransaction } from "../types";

export interface AIClassificationResult {
  id: string;
  category: string;
  subCategory?: string | null;
  taxAuthority?: "FIRS" | "SIRS" | "Not Applicable" | "Review Required" | null;
  confidence: "High" | "Medium" | "Low";
  reason: string;
  reviewRequired: boolean;
}

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

async function classifyBatch(
  transactions: ClassifiedTransaction[],
  template: AnalysisTemplate,
  customInstructions: string
): Promise<AIClassificationResult[]> {
  const response = await fetch(`/classify-analysis?t=${Date.now()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      template,
      customInstructions,
      transactions: transactions.map(t => ({
        id: t.id,
        date: t.transactionDate,
        description: t.description,
        debit: t.debit,
        credit: t.credit,
        reference: t.reference
      }))
    })
  });

  if (!response.ok) {
    throw new Error(`AI classifier unavailable (${response.status})`);
  }

  const data = await response.json();
  if (!Array.isArray(data.results)) {
    throw new Error("AI classifier returned invalid JSON");
  }
  return data.results;
}

export async function classifyTransactionsWithAI({
  transactions,
  template,
  customInstructions,
  onProgress
}: {
  transactions: ClassifiedTransaction[];
  template: AnalysisTemplate;
  customInstructions: string;
  onProgress?: (message: string) => void;
}): Promise<ClassifiedTransaction[]> {
  const pending = transactions.filter(t => t.reviewRequired || t.confidence === "Low");
  if (pending.length === 0) return transactions;

  const resultMap = new Map<string, AIClassificationResult>();
  const batches = chunk(pending, 35);

  for (let i = 0; i < batches.length; i++) {
    onProgress?.(`AI classifying unclear rows ${i + 1}/${batches.length}`);
    try {
      const results = await classifyBatch(batches[i], template, customInstructions);
      results.forEach(r => resultMap.set(r.id, r));
    } catch (firstError) {
      try {
        const results = await classifyBatch(batches[i], template, `${customInstructions}\nReturn strict JSON only. No prose.`);
        results.forEach(r => resultMap.set(r.id, r));
      } catch {
        batches[i].forEach(t => resultMap.set(t.id, {
          id: t.id,
          category: "Review Required",
          taxAuthority: template.id === "firs-sirs-na" ? "Review Required" : null,
          confidence: "Low",
          reason: "AI classification unavailable or invalid; manual review required.",
          reviewRequired: true
        }));
      }
    }
  }

  return transactions.map(t => {
    const ai = resultMap.get(t.id);
    if (!ai) return t;
    return {
      ...t,
      category: ai.category || "Review Required",
      subCategory: ai.subCategory ?? null,
      taxAuthority: ai.taxAuthority ?? t.taxAuthority ?? null,
      confidence: ai.confidence || "Low",
      reason: ai.reason || "Classified by AI fallback.",
      decisionSource: "AI",
      reviewRequired: Boolean(ai.reviewRequired || ai.confidence === "Low")
    };
  });
}
