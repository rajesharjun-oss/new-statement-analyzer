import { AnalysisTemplate } from "../types";

const bankNoise = [
  "stamp duty", "sms alert", "account maintenance", "acct maint", "vat on bank charge",
  "value added tax on charge", "card charge", "transfer charge", "commission", "nip charge",
  "pos stamp duty", "reversal", "reversed", "failed", "opening balance", "closing balance",
  "internal transfer", "own account transfer", "bank charge", "charges", "vat on bank",
  "sms", "pos charge", "own account", "loan disbursement"
];

export const analysisTemplates: AnalysisTemplate[] = [
  {
    id: "firs-sirs-na",
    name: "FIRS / SIRS / Not Applicable",
    description: "Classify debit transactions as company/entity payments, individual payments, or non-applicable bank items.",
    scope: "debit",
    markUncertainAsReview: true,
    treatSalaryAsSirs: false,
    salaryTreatment: "review",
    tradeNameTreatment: "review",
    aiInstructions: "Classify all debit transactions into FIRS, SIRS, or Not Applicable. Put payments to companies under FIRS, payments to individuals under SIRS, and bank charges/internal transfers/reversals under Not Applicable. If unsure, mark Review Required.",
    categories: [
      {
        id: "firs",
        name: "FIRS",
        outputLabel: "FIRS",
        description: "Company, incorporated entity, tax authority, or formal business payment.",
        appliesTo: "debit",
        includeKeywords: ["ltd", "limited", "plc", "enterprise", "enterprises", "ventures", "company", "incorporated", "nigeria limited", "firs", "federal inland revenue", "wht", "cit", "tax payment"],
        excludeKeywords: bankNoise,
        priority: 90
      },
      {
        id: "not-applicable",
        name: "Not Applicable",
        outputLabel: "Not Applicable",
        description: "Bank charges, reversals, internal transfers, balances, loan movements, and non-taxable bank items.",
        appliesTo: "debit",
        includeKeywords: bankNoise,
        excludeKeywords: [],
        priority: 100
      },
      {
        id: "sirs",
        name: "SIRS",
        outputLabel: "SIRS",
        description: "Likely individual or personal-name payments.",
        appliesTo: "debit",
        includeKeywords: ["mr", "mrs", "miss", "dr", "refund to individual"],
        excludeKeywords: ["ltd", "limited", "plc", "enterprise", "ventures", "company"],
        priority: 40
      }
    ]
  },
  {
    id: "credit-income",
    name: "Credit-only income analysis",
    description: "Analyze inflows only and group credits into income, funding, loans, transfers, refunds, and unexplained credits.",
    scope: "credit",
    markUncertainAsReview: true,
    aiInstructions: "Classify credit transactions only. Do not classify debit rows unless required for context.",
    categories: [
      { id: "customer-payment", name: "Customer Payment", outputLabel: "Customer Payment", description: "Customer or client inflow.", appliesTo: "credit", includeKeywords: ["payment", "customer", "client", "invoice", "pos", "web payment"], excludeKeywords: ["loan", "refund"], priority: 80 },
      { id: "sales-income", name: "Sales Income", outputLabel: "Sales Income", description: "Sales or revenue inflow.", appliesTo: "credit", includeKeywords: ["sales", "revenue", "receipt"], excludeKeywords: [], priority: 75 },
      { id: "owner-funding", name: "Owner Funding", outputLabel: "Owner Funding", description: "Capital injection or owner funding.", appliesTo: "credit", includeKeywords: ["capital", "owner", "director", "funding"], excludeKeywords: [], priority: 70 },
      { id: "loan-inflow", name: "Loan Inflow", outputLabel: "Loan Inflow", description: "Loan received.", appliesTo: "credit", includeKeywords: ["loan", "facility", "disbursement"], excludeKeywords: [], priority: 85 },
      { id: "internal-transfer", name: "Internal Transfer", outputLabel: "Internal Transfer", description: "Own-account or treasury transfers.", appliesTo: "credit", includeKeywords: ["internal", "own account", "transfer between", "sweep"], excludeKeywords: [], priority: 90 },
      { id: "refund-reversal", name: "Refund/Reversal", outputLabel: "Refund/Reversal", description: "Refunds and reversal inflows.", appliesTo: "credit", includeKeywords: ["refund", "reversal", "reversed"], excludeKeywords: [], priority: 90 },
      { id: "interest-income", name: "Interest Income", outputLabel: "Interest Income", description: "Interest credited by bank.", appliesTo: "credit", includeKeywords: ["interest"], excludeKeywords: ["withholding", "wht"], priority: 80 },
      { id: "unexplained-credit", name: "Unexplained Credit", outputLabel: "Unexplained Credit", description: "Credit that needs explanation.", appliesTo: "credit", includeKeywords: [], excludeKeywords: [], priority: 0 }
    ]
  },
  {
    id: "debit-expense",
    name: "Debit-only expense analysis",
    description: "Analyze outflows only and group expenses into common operating categories.",
    scope: "debit",
    markUncertainAsReview: true,
    aiInstructions: "Classify debit transactions only into normal expense categories. Mark ambiguous rows Review Required.",
    categories: [
      { id: "supplier", name: "Supplier Payment", outputLabel: "Supplier Payment", description: "Payment to vendor or supplier.", appliesTo: "debit", includeKeywords: ["supplier", "invoice", "payment to", "purchase"], excludeKeywords: bankNoise, priority: 60 },
      { id: "staff", name: "Staff/Salary Payment", outputLabel: "Staff/Salary Payment", description: "Salary or staff payments.", appliesTo: "debit", includeKeywords: ["salary", "payroll", "staff", "allowance", "wages"], excludeKeywords: [], priority: 90 },
      { id: "rent", name: "Rent", outputLabel: "Rent", description: "Rent or lease.", appliesTo: "debit", includeKeywords: ["rent", "lease"], excludeKeywords: [], priority: 85 },
      { id: "transport", name: "Transport", outputLabel: "Transport", description: "Transport and logistics.", appliesTo: "debit", includeKeywords: ["transport", "logistics", "uber", "bolt", "fuel"], excludeKeywords: [], priority: 80 },
      { id: "repairs", name: "Repairs & Maintenance", outputLabel: "Repairs & Maintenance", description: "Repairs and maintenance.", appliesTo: "debit", includeKeywords: ["repair", "maintenance", "service"], excludeKeywords: [], priority: 75 },
      { id: "office", name: "Office Expense", outputLabel: "Office Expense", description: "Office/admin costs.", appliesTo: "debit", includeKeywords: ["office", "stationery", "internet", "subscription"], excludeKeywords: [], priority: 70 },
      { id: "travel", name: "Travel", outputLabel: "Travel", description: "Travel expenses.", appliesTo: "debit", includeKeywords: ["travel", "flight", "hotel", "visa"], excludeKeywords: [], priority: 82 },
      { id: "bank-charges", name: "Bank Charges", outputLabel: "Bank Charges", description: "Bank charges and levies.", appliesTo: "debit", includeKeywords: bankNoise, excludeKeywords: [], priority: 100 },
      { id: "tax", name: "Tax/Statutory Payment", outputLabel: "Tax/Statutory Payment", description: "Tax or statutory payments.", appliesTo: "debit", includeKeywords: ["tax", "firs", "sirs", "vat", "wht", "paye", "pension"], excludeKeywords: [], priority: 95 },
      { id: "loan-repayment", name: "Loan Repayment", outputLabel: "Loan Repayment", description: "Loan repayment.", appliesTo: "debit", includeKeywords: ["loan repayment", "repayment", "facility"], excludeKeywords: [], priority: 86 },
      { id: "internal-transfer", name: "Internal Transfer", outputLabel: "Internal Transfer", description: "Own-account transfer.", appliesTo: "debit", includeKeywords: ["internal", "own account", "transfer between"], excludeKeywords: [], priority: 92 },
      { id: "cash", name: "Cash Withdrawal", outputLabel: "Cash Withdrawal", description: "Cash withdrawal.", appliesTo: "debit", includeKeywords: ["cash withdrawal", "atm", "withdrawal"], excludeKeywords: [], priority: 85 }
    ]
  },
  {
    id: "business-category",
    name: "Business income and expense categorization",
    description: "Classify all debits and credits into standard business reporting categories.",
    scope: "both",
    markUncertainAsReview: true,
    aiInstructions: "Classify all transactions into standard business income, expense, transfer, loan, refund, reversal, or review categories.",
    categories: []
  },
  {
    id: "travel-tour",
    name: "Travel/tour business classification",
    description: "Specialized categories for travel agencies and tour businesses.",
    scope: "both",
    markUncertainAsReview: true,
    aiInstructions: "Classify transactions for a travel or tour business. Use travel supplier, airline, hotel, visa, insurance, refund and customer trip payment labels.",
    categories: [
      { id: "trip-payment", name: "Customer Trip Payment", outputLabel: "Customer Trip Payment", description: "Customer payment for trip package.", appliesTo: "credit", includeKeywords: ["trip", "tour", "package", "customer"], excludeKeywords: [], priority: 75 },
      { id: "airline", name: "Flight/Airline Payment", outputLabel: "Flight/Airline Payment", description: "Airline or ticket payment.", appliesTo: "debit", includeKeywords: ["flight", "airline", "ticket", "iata"], excludeKeywords: [], priority: 90 },
      { id: "hotel", name: "Hotel/Accommodation", outputLabel: "Hotel/Accommodation", description: "Hotel accommodation.", appliesTo: "debit", includeKeywords: ["hotel", "accommodation", "lodging"], excludeKeywords: [], priority: 85 },
      { id: "visa", name: "Visa Processing", outputLabel: "Visa Processing", description: "Visa fees and processing.", appliesTo: "debit", includeKeywords: ["visa", "embassy", "vfs"], excludeKeywords: [], priority: 88 },
      { id: "insurance", name: "Insurance", outputLabel: "Insurance", description: "Travel insurance.", appliesTo: "debit", includeKeywords: ["insurance"], excludeKeywords: [], priority: 80 },
      { id: "refund", name: "Customer Refund", outputLabel: "Customer Refund", description: "Refund to customer.", appliesTo: "debit", includeKeywords: ["refund"], excludeKeywords: [], priority: 90 },
      { id: "bank", name: "Bank Charges & Taxes", outputLabel: "Bank Charges & Taxes", description: "Bank charges and taxes.", appliesTo: "both", includeKeywords: [...bankNoise, "tax", "vat", "wht"], excludeKeywords: [], priority: 100 }
    ]
  },
  {
    id: "tax-audit",
    name: "Tax audit analysis",
    description: "Group transactions for tax review and supporting schedules.",
    scope: "both",
    markUncertainAsReview: true,
    aiInstructions: "Group transactions for tax audit. Use taxable income, non-taxable inflow, related party transfer, loan, supplier, individual, statutory, cash, bank charges, internal transfer, reversal or review.",
    categories: [
      { id: "taxable-income", name: "Taxable Business Income", outputLabel: "Taxable Business Income", description: "Likely taxable operating income.", appliesTo: "credit", includeKeywords: ["payment", "sales", "invoice", "customer"], excludeKeywords: ["loan", "refund"], priority: 80 },
      { id: "non-taxable", name: "Non-taxable Inflow", outputLabel: "Non-taxable Inflow", description: "Non-taxable inflow.", appliesTo: "credit", includeKeywords: ["capital", "owner", "refund"], excludeKeywords: [], priority: 70 },
      { id: "related", name: "Related Party Transfer", outputLabel: "Related Party Transfer", description: "Director/shareholder/related party.", appliesTo: "both", includeKeywords: ["director", "shareholder", "related"], excludeKeywords: [], priority: 75 },
      { id: "statutory", name: "Statutory Payment", outputLabel: "Statutory Payment", description: "Tax or statutory payment.", appliesTo: "debit", includeKeywords: ["firs", "sirs", "tax", "vat", "wht", "paye", "pension"], excludeKeywords: [], priority: 95 },
      { id: "individual", name: "Individual Payment", outputLabel: "Individual Payment", description: "Likely payment to individual.", appliesTo: "debit", includeKeywords: ["mr ", "mrs ", "miss ", "dr "], excludeKeywords: ["ltd", "limited"], priority: 40 },
      { id: "bank", name: "Bank Charges", outputLabel: "Bank Charges", description: "Bank charges.", appliesTo: "debit", includeKeywords: bankNoise, excludeKeywords: [], priority: 100 }
    ]
  },
  {
    id: "custom",
    name: "Fully custom user-defined analysis",
    description: "Start from a blank template and define your own categories, scope, and instructions.",
    scope: "both",
    markUncertainAsReview: true,
    aiInstructions: "",
    categories: []
  }
];

const businessDefaults = [
  "Operating Income", "Customer Payment", "Supplier Payment", "Staff Cost", "Rent",
  "Transport", "Repairs and Maintenance", "Office/Admin Expense", "Bank Charges & Levies",
  "Taxes and Statutory Payments", "Internal Transfer", "Loan", "Refund", "Reversal",
  "Cash Withdrawal"
];

analysisTemplates.find(t => t.id === "business-category")!.categories = businessDefaults.map((name, idx) => ({
  id: name.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
  name,
  outputLabel: name,
  description: `${name} transactions.`,
  appliesTo: name.includes("Income") || name.includes("Customer") ? "credit" : "both",
  includeKeywords: name === "Bank Charges & Levies" ? bankNoise : name.toLowerCase().split(/[&/ ]+/).filter(Boolean),
  excludeKeywords: [],
  priority: 60 - idx
}));

export function cloneTemplate(template: AnalysisTemplate): AnalysisTemplate {
  return JSON.parse(JSON.stringify(template));
}
