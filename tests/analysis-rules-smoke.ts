import { AnalysisTemplate, ClassifiedTransaction } from "../types";
import { applyDeterministicRules } from "../services/analysisRules";
import { analysisTemplates, cloneTemplate } from "../services/analysisTemplates";
import { classifyTransactionsWithAI } from "../services/aiClassifierService";

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message);
}

const firsTemplate = cloneTemplate(analysisTemplates.find(t => t.id === "firs-sirs-na")!) as AnalysisTemplate;

function txn(description: string, debit = 100, credit = 0): ClassifiedTransaction {
  return {
    id: description.slice(0, 20) || "txn",
    sourceFileName: "fixture.pdf",
    transactionDate: "2024-01-01",
    date: "2024-01-01",
    valueDate: "",
    reference: "",
    description,
    category: "Review Required",
    debit,
    credit,
    balance: 0,
    confidence: "Low",
    reason: "",
    decisionSource: "SYSTEM",
    reviewRequired: true
  };
}

async function main() {
  const cobVendor = applyDeterministicRules(txn("COB TRF TO OLAPEJU O **7572 To pay Vendors on beh"), firsTemplate);
  assert(cobVendor.category !== "FIRS", "COB transfer text must not match FIRS");

  const stampDuty = applyDeterministicRules(txn("STAMP  DUTY  CHARGE  - 25-01-2021", 50), firsTemplate);
  assert(stampDuty.category === "Not Applicable", "Double-spaced stamp duty must be Not Applicable");

  const sms = applyDeterministicRules(txn("SMS ALERT CHARGES 15JAN 21", 10), firsTemplate);
  assert(sms.category === "Not Applicable", "SMS alert charges must be Not Applicable");

  const nipCharge = applyDeterministicRules(txn("COB TRF TO SWIFT NETW **4891 Internet Subscription", 53.75), firsTemplate);
  assert(nipCharge.category === "Not Applicable", "Common NIP/transfer charge must be Not Applicable across banks");

  const pos = applyDeterministicRules(txn("POS PURCHASE @2057HM54-FOODIES HOT AND SPIC LA", 5000), firsTemplate);
  assert(pos.category !== "SIRS", "POS purchase merchant must not default to SIRS");

  const creditOnly = applyDeterministicRules(txn("Transfer from OKOJIE OPEYEMI", 0, 5000), firsTemplate);
  assert(creditOnly.category === "Out of Scope", "Credit row must be Out of Scope for debit-only FIRS template");

  const originalFetch = globalThis.fetch;
  (globalThis as any).fetch = async () => ({ ok: false, status: 503, json: async () => ({}) });
  try {
    const [unresolved] = await classifyTransactionsWithAI({
      transactions: [txn("Ambiguous debit row", 7000)],
      template: firsTemplate,
      customInstructions: "",
      onProgress: undefined
    });
    assert(unresolved.decisionSource === "SYSTEM", "AI-unavailable fallback must use SYSTEM decision source");
    assert(unresolved.reason === "No deterministic rule matched and AI provider is unavailable.", "AI-unavailable reason must be explicit");
  } finally {
    globalThis.fetch = originalFetch;
  }
}

main().then(() => {
  console.log("analysis-rules-smoke: ok");
}).catch(error => {
  console.error(error);
  process.exit(1);
});
