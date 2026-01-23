
export interface Transaction {
  date: string;
  description: string;
  category: string;
  reference: string;
  debit: number;
  credit: number;
  balance: number;
  is_reversal: boolean;
}

export interface AnalysisResult {
  reconciliation_failed: boolean;
  reconciliation_warnings: string[];
  currency: string;
  transactions: Transaction[];
  organizationName: string;
  bankName: string;
}

export enum AppStatus {
  IDLE = 'IDLE',
  ANALYZING = 'ANALYZING',
  COMPLETE = 'COMPLETE',
  ERROR = 'ERROR',
}

export const CATEGORIES = [
  // Inflows (Credit Side)
  'Operating Income', 
  'Student Exam Fees (Pass-Through)', 
  'Owner\'s Capital', 
  'Inter-Account Transfer', 
  'Interest Income', 
  'Refund / Reversal',
  'Incoming Transfer',

  // Expenses (Decision Tree)
  'Staff Costs',           // Salary / Staff
  'Cost of Service',       // Student / Exam / Uniform
  'Repairs & Maintenance', // Repairs / Servicing
  'Utilities',             // Utility / Fuel
  'Bank Charges',          // Bank / SMS / Charges
  'Tax Payable',           // Tax
  'Capital Asset',         // Asset Purchase
  'Administrative Expenses', // Otherwise

  // Fallback
  'Unallocated'
];
