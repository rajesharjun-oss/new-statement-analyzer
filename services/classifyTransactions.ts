import { AnalysisTemplate, ClassifiedTransaction, Transaction } from "../types";
import { classifyTransactionsWithAI } from "./aiClassifierService";
import { classifyByTemplateRules, normalizeTransactions } from "./analysisRules";

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

  if (!useAI) return ruleClassified;

  const unresolved = ruleClassified.filter(t => t.reviewRequired || t.confidence === "Low").length;
  if (unresolved === 0) return ruleClassified;

  try {
    return await classifyTransactionsWithAI({
      transactions: ruleClassified,
      template,
      customInstructions,
      onProgress
    });
  } catch {
    return ruleClassified.map(t => (
      t.reviewRequired || t.confidence === "Low"
        ? { ...t, reason: `${t.reason} AI fallback unavailable.` }
        : t
    ));
  }
}
