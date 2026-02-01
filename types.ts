
export type DecisionSource = 'AI' | 'RULE' | 'MEMORY' | 'HUMAN';

export interface Transaction {
  date: string;
  description: string;
  category: string;
  debit: number;
  credit: number;
  balance: number;
  confidence?: number;
  ruleId?: string;
  decision_source?: DecisionSource;
  is_reversal?: boolean;
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
  stats?: AnalysisStatistics;
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
