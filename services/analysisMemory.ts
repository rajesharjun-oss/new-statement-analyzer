import { AnalysisCategoryMemoryEntry, ClassifiedTransaction } from "../types";
import { normalizeNarration } from "./analysisRules";

const storageKey = "ledger_analysis_category_memory_v1";
const maximumEntries = 5000;

function stableHash(value: string): string {
  let hash = 0xcbf29ce484222325n;
  const prime = 0x100000001b3n;
  for (const character of value) {
    hash ^= BigInt(character.codePointAt(0) || 0);
    hash = BigInt.asUintN(64, hash * prime);
  }
  return hash.toString(16).padStart(16, "0");
}

export function narrationFingerprint(transaction: ClassifiedTransaction): string {
  const direction = transaction.debit > 0 ? "debit" : transaction.credit > 0 ? "credit" : "none";
  const stableNarration = normalizeNarration(transaction.description || transaction.rawText || "")
    .replace(/\b[a-z0-9]*\d{5,}[a-z0-9]*\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return stableHash(`${direction}|${stableNarration}`);
}

export function loadCategoryMemory(): AnalysisCategoryMemoryEntry[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(entry => (
      entry
      && typeof entry.id === "string"
      && typeof entry.templateId === "string"
      && typeof entry.narrationFingerprint === "string"
      && typeof entry.category === "string"
    )).slice(-maximumEntries);
  } catch {
    return [];
  }
}

function saveCategoryMemory(entries: AnalysisCategoryMemoryEntry[]) {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(storageKey, JSON.stringify(entries.slice(-maximumEntries)));
  } catch {
    // Classification continues without memory when browser storage is unavailable.
  }
}

export function rememberCategoryDecision(transaction: ClassifiedTransaction, templateId: string): void {
  const category = String(transaction.category || "").trim();
  if (!category || ["review required", "unallocated", "uncategorized", "unallocated/review required"].includes(category.toLowerCase())) return;

  const entries = loadCategoryMemory();
  const fingerprint = narrationFingerprint(transaction);
  const existingIndex = entries.findIndex(entry => entry.templateId === templateId && entry.narrationFingerprint === fingerprint);
  const now = new Date().toISOString();
  const next: AnalysisCategoryMemoryEntry = {
    id: existingIndex >= 0 ? entries[existingIndex].id : `memory-${templateId}-${fingerprint}`,
    templateId,
    narrationFingerprint: fingerprint,
    category,
    subCategory: transaction.subCategory ?? null,
    taxAuthority: transaction.taxAuthority ?? null,
    useCount: existingIndex >= 0 ? entries[existingIndex].useCount : 0,
    createdAt: existingIndex >= 0 ? entries[existingIndex].createdAt : now,
    updatedAt: now
  };
  if (existingIndex >= 0) entries[existingIndex] = next;
  else entries.push(next);
  saveCategoryMemory(entries);
}

export function applyCategoryMemory(
  transactions: ClassifiedTransaction[],
  templateId: string
): ClassifiedTransaction[] {
  const entries = loadCategoryMemory().filter(entry => entry.templateId === templateId);
  if (entries.length === 0) return transactions;
  const byFingerprint = new Map(entries.map(entry => [entry.narrationFingerprint, entry]));
  const usedIds = new Set<string>();
  const classified = transactions.map(transaction => {
    if (!transaction.reviewRequired && transaction.confidence !== "Low") return transaction;
    const match = byFingerprint.get(narrationFingerprint(transaction));
    if (!match) return transaction;
    usedIds.add(match.id);
    return {
      ...transaction,
      category: match.category,
      subCategory: match.subCategory,
      taxAuthority: match.taxAuthority,
      confidence: "High" as const,
      reason: "Matched a previously reviewed narration decision stored in this browser.",
      decisionSource: "MEMORY" as const,
      reviewRequired: false
    };
  });

  if (usedIds.size > 0) {
    const now = new Date().toISOString();
    saveCategoryMemory(loadCategoryMemory().map(entry => usedIds.has(entry.id)
      ? { ...entry, useCount: entry.useCount + 1, updatedAt: now }
      : entry));
  }
  return classified;
}

export function categoryMemoryCount(templateId?: string): number {
  const entries = loadCategoryMemory();
  return templateId ? entries.filter(entry => entry.templateId === templateId).length : entries.length;
}

export function clearCategoryMemory(templateId?: string): void {
  if (templateId) saveCategoryMemory(loadCategoryMemory().filter(entry => entry.templateId !== templateId));
  else saveCategoryMemory([]);
}
