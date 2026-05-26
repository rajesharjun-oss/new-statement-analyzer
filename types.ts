
export type DecisionSource = 'AI' | 'RULE' | 'MEMORY' | 'HUMAN' | 'MANUAL' | 'SYSTEM';

export interface Transaction {
  id?: string;
  sourceFileName?: string;
  pageNumber?: number;
  rowNumber?: number;
  date: string;
  transactionDate?: string;
  valueDate?: string;
  reference?: string;
  description: string;
  rawText?: string;
  category: string;
  debit: number;
  credit: number;
  balance: number;
  subCategory?: string | null;
  taxAuthority?: 'FIRS' | 'SIRS' | 'Not Applicable' | 'Review Required' | null;
  confidence?: number | 'High' | 'Medium' | 'Low';
  reason?: string;
  ruleId?: string;
  decision_source?: DecisionSource;
  decisionSource?: DecisionSource;
  reviewRequired?: boolean;
  is_reversal?: boolean;
}

export type AnalysisScope = 'debit' | 'credit' | 'both';
export type ConfidenceLabel = 'High' | 'Medium' | 'Low';

export interface AnalysisCategoryRule {
  id: string;
  name: string;
  outputLabel: string;
  description: string;
  appliesTo: AnalysisScope;
  includeKeywords: string[];
  excludeKeywords: string[];
  priority: number;
}

export interface AnalysisTemplate {
  id: string;
  name: string;
  description: string;
  scope: AnalysisScope;
  categories: AnalysisCategoryRule[];
  aiInstructions: string;
  markUncertainAsReview: boolean;
}

export interface ClassifiedTransaction extends Transaction {
  id: string;
  sourceFileName: string;
  transactionDate: string;
  valueDate?: string;
  reference?: string;
  debit: number;
  credit: number;
  balance: number;
  category: string;
  subCategory?: string | null;
  taxAuthority?: 'FIRS' | 'SIRS' | 'Not Applicable' | 'Review Required' | null;
  confidence: ConfidenceLabel;
  reason: string;
  decisionSource: DecisionSource;
  reviewRequired: boolean;
}

export interface ReconciliationCheck {
  openingBalance: number | null;
  totalDebit: number;
  totalCredit: number;
  expectedClosingBalance: number | null;
  actualClosingBalance: number | null;
  difference: number | null;
  status: 'Passed' | 'Failed' | 'Unverified';
}

export interface AnalysisStatistics {
  total_txns: number;
  rule_hits: number;
  memory_hits: number;
  ai_txns: number;
  ai_calls: number;
  human_overrides: number;
  ai_rate_percent: number;
  auto_rate_percent: number;
}

export interface AnalysisResult {
  reconciliation_failed: boolean;
  reconciliation_warnings: string[];
  error_indices: number[]; // Indices of rows that failed math check
  currency: string;
  transactions: Transaction[];
  organizationName: string;
  bankName: string;
  statement_summary?: {
    period?: string;
    transaction_count?: number;
    validation_status?: string;
    totals_match?: boolean | null;
    total_debit?: number;
    total_credit?: number;
    opening_balance?: number | null;
    closing_balance?: number | null;
    extracted_total_debit?: number;
    extracted_total_credit?: number;
  };
  downloadUrl?: string;
  stats?: AnalysisStatistics;
  backend_version?: string;
}

export enum AppStatus {
  IDLE = 'IDLE',
  ANALYZING = 'ANALYZING',
  COMPLETE = 'COMPLETE',
  ERROR = 'ERROR',
}

export const CATEGORIES = [
  'Unallocated',

  // Special
  'Stock Purchase',

  // System
  'Opening Balance',
  'Closing Balance',

  // P&L - Income
  'Operating Income',
  'Interest Income',

  // P&L - Expenses
  'Bank Charges',
  'Administrative Expenses',
  'Office Rent / Lease',
  'Event & Conference Expenses',
  'Transport & Logistics',
  'Repairs & Maintenance',
  'Staff Welfare',
  'Salaries & Wages',
  'Staff Training & Development',
  'Foreign Exam Fees',

  // Balance Sheet - Assets
  'Capital Expenditure (CWIP)',
  'WHT Receivable',
  'VAT Receivable',
  'Staff Debtors / Salary Advances',

  // Balance Sheet - Liabilities/Movement
  'Student Exam Fees (Pass-Through)',
  'Inter-Account / Treasury Transfer',

  // Control
  'Review Required'
];
