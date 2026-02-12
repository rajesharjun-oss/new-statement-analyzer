/**
 * Ecobank Statement Parser - Enhanced Version
 * Fixes the issue where large debit amounts were being skipped
 * Handles: ₦1,000,000 | ₦8,000,000 | ₦1,500,000 (large debits)
 *          ₦50 | ₦3.75 (small fees)
 */

import { Transaction } from '../types';

interface EcobankRow {
    date: string;
    description: string;
    debit: number;
    credit: number;
    balance: number;
}

/**
 * IMPROVED MONEY REGEX - The Core Fix
 * Old pattern was too restrictive for large amounts
 * New pattern: [₦£$€]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)
 * 
 * Captures:
 *   - ₦1,000,000 (large with separators)
 *   - 8000000 (large without separators)
 *   - 50 (small amounts)
 *   - 3.75 (decimals)
 */
const MONEY_PATTERN = /[₦£$€]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)/g;

// Ecobank date format: DD/MM/YYYY
const ECOBANK_DATE_PATTERN = /\d{1,2}\/\d{1,2}\/\d{4}/;

export class EcobankParser {
    /**
     * Parse amount string to number, handling various formats
     * Examples:
     *   "1,000,000.00" -> 1000000
     *   "₦50" -> 50
     *   "3.75" -> 3.75
     *   "8000000" -> 8000000
     */
    static parseAmount(amountStr: string): number {
        if (!amountStr || amountStr.trim() === '') {
            return 0;
        }

        // Remove currency symbols
        let cleaned = amountStr.replace(/[₦£$€\s]/g, '').trim();

        // Remove commas (thousand separators)
        cleaned = cleaned.replace(/,/g, '');

        // Handle parentheses as negative indicator
        const isNegative = /^\(.*\)$/.test(amountStr.trim());

        const num = parseFloat(cleaned);
        if (isNaN(num)) {
            console.warn(`Warning: Could not parse amount '${amountStr}'`);
            return 0;
        }

        return isNegative ? -num : num;
    }

    /**
     * Extract all money amounts from a line using improved regex
     * This is the KEY FIX - it captures ALL amounts, not just small ones
     */
    static extractAllAmounts(text: string): number[] {
        const amounts: number[] = [];
        let match;

        // Reset regex lastIndex since we're using global flag
        MONEY_PATTERN.lastIndex = 0;

        while ((match = MONEY_PATTERN.exec(text)) !== null) {
            const amount = this.parseAmount(match[0]);
            if (amount > 0) {
                amounts.push(amount);
            }
        }

        return amounts;
    }

    /**
     * Check if a string contains a valid Ecobank date
     */
    static isValidDate(str: string): boolean {
        return ECOBANK_DATE_PATTERN.test(str);
    }

    /**
     * Parse a single row from Ecobank statement
     * Expected format: DATE | DESCRIPTION | DEBIT | CREDIT | BALANCE
     * 
     * Example:
     *   01/15/2024  Fund Transfer       1,000,000.00  -              8,500,000.00
     *   01/15/2024  ATM Fee             50.00         -              8,449,950.00
     */
    static parseRow(line: string): EcobankRow | null {
        // Split by multiple spaces/tabs (common in PDF extracts)
        const parts = line.trim().split(/\s{2,}/).map(p => p.trim());

        if (parts.length < 4) {
            return null;
        }

        // First part should be a date
        const date = parts[0];
        if (!this.isValidDate(date)) {
            return null;
        }

        // Description is typically the next part
        const description = parts[1];

        // Extract all amounts from remaining parts
        // Usually in order: [debit, credit, balance] or [amount, balance]
        let amounts: number[] = [];

        for (let i = 2; i < parts.length; i++) {
            const part = parts[i];
            
            // Skip dashes and empty cells
            if (part === '-' || part === '' || !part) {
                continue;
            }

            const amount = this.parseAmount(part);
            if (amount > 0 || amount < 0) {
                amounts.push(amount);
            }
        }

        // Assign amounts based on position
        // Expected: [debit, credit, balance] or [amount, balance]
        if (amounts.length < 2) {
            return null;
        }

        let debit = 0;
        let credit = 0;
        let balance = 0;

        if (amounts.length === 2) {
            // Format: [amount, balance]
            const amount = amounts[0];
            balance = amounts[1];
            if (amount > 0) {
                debit = amount;
            } else {
                credit = Math.abs(amount);
            }
        } else if (amounts.length >= 3) {
            // Format: [debit, credit, balance]
            debit = Math.abs(amounts[0]);
            credit = Math.abs(amounts[1]);
            balance = amounts[amounts.length - 1]; // Last is balance
        }

        return {
            date,
            description,
            debit,
            credit,
            balance
        };
    }

    /**
     * Parse entire Ecobank statement text and return Transaction array
     */
    static parseStatement(text: string): Transaction[] {
        const lines = text.split('\n');
        const transactions: Transaction[] = [];

        for (const line of lines) {
            if (!line.trim()) continue;

            const row = this.parseRow(line);
            if (row) {
                const txn: Transaction = {
                    date: row.date,
                    description: row.description,
                    category: 'Unallocated',
                    debit: row.debit,
                    credit: row.credit,
                    balance: row.balance,
                    is_reversal: false,
                    confidence: 0.95
                };

                transactions.push(txn);
            }
        }

        return transactions;
    }

    /**
     * Validate parsed transactions and calculate totals
     */
    static validateAndGetTotals(transactions: Transaction[]): {
        isValid: boolean;
        totalDebit: number;
        totalCredit: number;
        issues: string[];
    } {
        const issues: string[] = [];
        let totalDebit = 0;
        let totalCredit = 0;

        transactions.forEach((txn, idx) => {
            totalDebit += txn.debit || 0;
            totalCredit += txn.credit || 0;

            // Check balance continuity
            if (idx > 0) {
                const prevTxn = transactions[idx - 1];
                const expected = prevTxn.balance + (txn.credit || 0) - (txn.debit || 0);
                const tolerance = 0.01; // Allow for rounding

                if (Math.abs(expected - txn.balance) > tolerance) {
                    issues.push(
                        `Row ${idx + 1}: Balance mismatch. Expected ~${expected.toFixed(2)}, got ${txn.balance.toFixed(2)}`
                    );
                }
            }
        });

        return {
            isValid: issues.length === 0,
            totalDebit,
            totalCredit,
            issues
        };
    }
}

/**
 * Export a convenience function for use in analysisService
 */
export function parseEcobankStatement(text: string): {
    transactions: Transaction[];
    summary: {
        totalDebit: number;
        totalCredit: number;
        transactionCount: number;
        isValid: boolean;
        validationIssues: string[];
    };
} {
    const transactions = EcobankParser.parseStatement(text);
    const validation = EcobankParser.validateAndGetTotals(transactions);

    return {
        transactions,
        summary: {
            totalDebit: validation.totalDebit,
            totalCredit: validation.totalCredit,
            transactionCount: transactions.length,
            isValid: validation.isValid,
            validationIssues: validation.issues
        }
    };
}