import { AnalysisTemplate, ClassifiedTransaction } from "../types";
import { applyDeterministicRules, cleanupTransactionDescription, normalizeNarration } from "../services/analysisRules";
import { analysisTemplates, cloneTemplate, createCustomAnalysisTemplate } from "../services/analysisTemplates";
import { classifyTransactionsWithAI } from "../services/aiClassifierService";
import { buildExportWorkbookData } from "../services/analysisExportService";

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

  const cleaningCharge = applyDeterministicRules(txn("COB TRF TO PALMACEDAR **7638 CLEANING SERVICES", 26.88), firsTemplate);
  assert(cleaningCharge.category === "Not Applicable", "Cleaning services transfer charge must be Not Applicable");

  const medicalCharge = applyDeterministicRules(txn("COB TRF TO MARY UGO O **2832 MEDICAL SERVICES", 26.88), firsTemplate);
  assert(medicalCharge.category === "Not Applicable", "Medical services transfer charge must be Not Applicable");

  const internetServicesCharge = applyDeterministicRules(txn("COB TRF TO SWIFT NETW **4891 INTERNET SERVICES", 53.75), firsTemplate);
  assert(internetServicesCharge.category === "Not Applicable", "Internet services transfer charge must be Not Applicable");

  const tenSeventyFiveCharge = applyDeterministicRules(txn("COB TRF TO ADESHOLA H **5089 To purchase Facemasks", 10.75), firsTemplate);
  assert(tenSeventyFiveCharge.category === "Not Applicable", "10.75 COB transfer charge must be Not Applicable");

  const counterCheque = applyDeterministicRules(txn("Counter Cheque Issue Charge", 50), firsTemplate);
  assert(counterCheque.category === "Not Applicable", "Counter cheque issue charge must be Not Applicable");

  const vatCounterCheque = applyDeterministicRules(txn("VAT- Counter Chq Issue Charge", 3.75), firsTemplate);
  assert(vatCounterCheque.category === "Not Applicable", "VAT counter cheque issue charge must be Not Applicable");

  const largerServicePayment = applyDeterministicRules(txn("COB TRF TO PALMACEDAR **7638 CLEANING SERVICES", 75250), firsTemplate);
  assert(largerServicePayment.category !== "Not Applicable", "Large service payment must not be treated as a common transfer charge");
  assert(largerServicePayment.category === "Review Required", "Large unregistered service/trade payee must default to Review Required");

  for (const tradeName of ["COB TRF TO DAMAC OIL", "COB TRF TO PRINT HAVE", "COB TRF TO CAKES BIRE"]) {
    const result = applyDeterministicRules(txn(tradeName, 10000), firsTemplate);
    assert(result.category === "Review Required", `${tradeName} must default to Review Required`);
  }

  assert(normalizeNarration("OFFICE LAND L TD").includes("ltd"), "Broken L TD suffix must normalize to LTD");
  assert(!cleanupTransactionDescription("07/04/2024 Details COB TRF TO ABC").includes("07/04/2024 Details"), "Header/footer Details contamination must be cleaned");
  assert(cleanupTransactionDescription("STAMP DUTY CHARGE - 04-01-2022 07/04/2024") === "STAMP DUTY CHARGE - 04-01-2022", "Trailing report/footer date must be removed from description");

  const exportData = buildExportWorkbookData({
    transactions: [{ ...txn("OFFICE LAND L TD", 1000), pageNumber: 4, category: "FIRS", taxAuthority: "FIRS", confidence: "High", reviewRequired: false }],
    template: firsTemplate,
    customInstructions: "",
    reconciliation: {
      openingBalance: 0,
      totalDebit: 1000,
      totalCredit: 0,
      expectedClosingBalance: -1000,
      actualClosingBalance: -1000,
      difference: 0,
      status: "Passed"
    }
  });
  assert(exportData.classifiedTransactions[0]["Page Number"] === 4, "Exported classified rows must include Page Number");

  const pos = applyDeterministicRules(txn("POS PURCHASE @2057HM54-FOODIES HOT AND SPIC LA", 5000), firsTemplate);
  assert(pos.category !== "SIRS", "POS purchase merchant must not default to SIRS");

  const creditOnly = applyDeterministicRules(txn("Transfer from OKOJIE OPEYEMI", 0, 5000), firsTemplate);
  assert(creditOnly.category === "Out of Scope", "Credit row must be Out of Scope for debit-only FIRS template");

  const customTemplate = createCustomAnalysisTemplate();
  customTemplate.name = "Pension Review";
  customTemplate.scope = "credit";
  customTemplate.categories = [{
    id: "pension-income",
    name: "Pension Income",
    outputLabel: "Pension Income",
    description: "Retirement and pension inflows.",
    appliesTo: "credit",
    includeKeywords: ["pension", "ptad", "pfa", "retirement benefit"],
    excludeKeywords: [],
    priority: 90
  }];
  const customPension = applyDeterministicRules(txn("PTAD pension payment retirement benefit", 0, 250000), customTemplate);
  assert(customPension.category === "Pension Income", "Custom template category rules must classify matching credit rows");
  const customOutOfScope = applyDeterministicRules(txn("Office rent payment", 50000, 0), customTemplate);
  assert(customOutOfScope.category === "Out of Scope", "Custom credit-only templates must mark debit rows out of scope");

  const customExportData = buildExportWorkbookData({
    transactions: [customPension],
    template: customTemplate,
    customInstructions: "Separate pension income from operating income.",
    reconciliation: {
      openingBalance: 0,
      totalDebit: 0,
      totalCredit: 250000,
      expectedClosingBalance: 250000,
      actualClosingBalance: 250000,
      difference: 0,
      status: "Passed"
    }
  });
  assert(customExportData.rulesUsed[0]["Template Name"] === "Pension Review", "Custom template name must be exported");
  assert(customExportData.rulesUsed[0]["Custom Instructions"] === "Separate pension income from operating income.", "Custom instructions must be exported");

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
