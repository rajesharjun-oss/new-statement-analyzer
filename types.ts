export interface Transaction {
  date: string;
  description: string;
  category: string;
  reference: string;
  debit: number;
  credit: number;
  balance: number;
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
  // Income
  'Operating Income', 'Other Income',
  // Cost of Sales
  'COS 1', 'COS 2',
  // Operating Expenses
  'Salaries & Wages', 'Staff Welfare', 'Staff Meals/Canteen', 'Staff Uniforms/Laundry', 
  'Staff Training', 'Staff Incentives', 'Telephone Expense', 'Utilities', 'Cable & Internet', 
  'Repairs & Maintenance', 'Cleaning', 'Diesel', 'Security', 'Depreciation', 'Travel Expense', 
  'Insurance', 'Licenses & Permits', 'Software Subscriptions', 'IT Maintenance & Repairs',
  // Marketing
  'Advertising & Promotions',
  // Professional Fees
  'Legal Fees', 'Audit Fees', 'Consultancy Fees',
  // Finance Costs
  'Bank POS / Merchant Transaction Fees', 'Bank Charges', 'Interest Expense', 'Exchange Rate Loss',
  // Taxes
  'Company Income Tax', 'Education Tax', 'Hotel Occupancy & Restaurant Consumption Tax', 'Fines & Penalties',
  // Transfers
  'Transfer In', 'Transfer Out', 
  // Default
  'Unallocated'
];