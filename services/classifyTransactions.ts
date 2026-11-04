import { AnalysisTemplate, ClassifiedTransaction, Transaction } from "../types";
import { classifyTransactionsWithAI } from "./aiClassifierService";
import { classifyByTemplateRules, normalizeTransactions } from "./analysisRules";
import { applyCategoryMemory } from "./analysisMemory";

export async function classifyTransactions({
  transactions,
  template,
  customInstructions,
  sourceFileName,
  useAI,
  onProgress
}: {
  transactions: Transaction[];
  template: AnalysisTemplate;
  customInstructions: string;
  sourceFileName: string;
  useAI: boolean;
  onProgress?: (message: string) => void;
}): Promise<ClassifiedTransaction[]> {
  onProgress?.("Applying deterministic rules");
  const normalized = normalizeTransactions(transactions, sourceFileName);
  const ruleClassified = classifyByTemplateRules(normalized, template);
  const memoryClassified = applyCategoryMemory(ruleClassified, template.id);

  if (!useAI) return memoryClassified;

  const unresolved = memoryClassified.filter(t => t.reviewRequired || t.confidence === "Low").length;
  if (unresolved === 0) return memoryClassified;

  try {
    return await classifyTransactionsWithAI({
      transactions: memoryClassified,
      template,
      customInstructions,
      onProgress
    });
  } catch {
    return memoryClassified.map(t => (
      t.reviewRequired || t.confidence === "Low"
        ? { ...t, reason: `${t.reason} AI fallback unavailable.` }
        : t
    ));
  }
}
