import React, { useMemo } from 'react';
import { AnalysisResult, Transaction } from '../types';
import { 
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from 'recharts';
import { Download, AlertTriangle, CheckCircle, TrendingDown, TrendingUp, Wallet, Banknote, Building2 } from 'lucide-react';
import { generateExcel } from '../services/excelService';

interface AnalysisDashboardProps {
  data: AnalysisResult;
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#a8a29e'];

export const AnalysisDashboard: React.FC<AnalysisDashboardProps> = ({ data }) => {
  const { transactions, reconciliation_failed, reconciliation_warnings, currency = 'USD', organizationName, bankName } = data;

  const summary = useMemo(() => {
    const totalDebits = transactions.reduce((sum, t) => sum + (t.debit || 0), 0);
    const totalCredits = transactions.reduce((sum, t) => sum + (t.credit || 0), 0);
    
    // Group expenses by category
    const categoryMap: Record<string, number> = {};
    transactions.forEach(t => {
      if (t.debit > 0) {
        categoryMap[t.category] = (categoryMap[t.category] || 0) + t.debit;
      }
    });
    
    // Sort by value desc for better visualization
    const categoryData = Object.entries(categoryMap)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);

    return { totalDebits, totalCredits, categoryData };
  }, [transactions]);

  const handleDownload = () => {
    generateExcel(transactions, reconciliation_warnings, reconciliation_failed, currency, organizationName, bankName);
  };

  const formatCurrency = (val: number) => {
    try {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(val);
    } catch (error) {
      // Fallback to USD if currency code is invalid or not supported
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
    }
  };

  return (
    <div className="space-y-8 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      
      {/* Header Actions */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-200 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold text-slate-900">Analysis Report</h2>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-100">
              <Banknote className="w-3.5 h-3.5" />
              {currency}
            </div>
          </div>
          <div className="flex items-center gap-2 mt-1 text-slate-500 text-sm">
            <Building2 className="w-3.5 h-3.5" />
            <span>{organizationName} &bull; {bankName}</span>
          </div>
        </div>
        <button
          onClick={handleDownload}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
        >
          <Download className="w-4 h-4" />
          Download Excel Report
        </button>
      </div>

      {/* Alerts */}
      {reconciliation_failed && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3 animate-in fade-in slide-in-from-top-2">
          <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5" />
          <div>
            <h4 className="font-semibold text-red-800">Reconciliation Failed</h4>
            <p className="text-sm text-red-700 mt-1">Row-level validation detected discrepancies in running balances. Please review the statement manually.</p>
          </div>
        </div>
      )}

      {reconciliation_warnings && reconciliation_warnings.length > 0 && (
        <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg flex items-start gap-3 animate-in fade-in slide-in-from-top-2">
          <AlertTriangle className="w-5 h-5 text-yellow-600 mt-0.5" />
          <div>
            <h4 className="font-semibold text-yellow-800">Warnings Detected</h4>
            <ul className="text-sm text-yellow-700 mt-1 list-disc list-inside">
              {reconciliation_warnings.map((w, idx) => <li key={idx}>{w}</li>)}
            </ul>
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-red-50 rounded-lg">
              <TrendingDown className="w-5 h-5 text-red-600" />
            </div>
            <span className="text-sm font-medium text-slate-500 uppercase tracking-wider">Total Outflows</span>
          </div>
          <p className="text-3xl font-bold text-slate-900 tracking-tight">{formatCurrency(summary.totalDebits)}</p>
        </div>

        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-green-50 rounded-lg">
              <TrendingUp className="w-5 h-5 text-green-600" />
            </div>
            <span className="text-sm font-medium text-slate-500 uppercase tracking-wider">Total Inflows</span>
          </div>
          <p className="text-3xl font-bold text-slate-900 tracking-tight">{formatCurrency(summary.totalCredits)}</p>
        </div>

        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
           <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-blue-50 rounded-lg">
              <Wallet className="w-5 h-5 text-blue-600" />
            </div>
            <span className="text-sm font-medium text-slate-500 uppercase tracking-wider">Transactions</span>
          </div>
          <p className="text-3xl font-bold text-slate-900 tracking-tight">{transactions.length}</p>
        </div>
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Pie Chart */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 mb-6">Expense Composition</h3>
          <div className="flex-1 min-h-[350px]">
            {summary.categoryData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={summary.categoryData}
                    cx="50%"
                    cy="50%"
                    innerRadius={80}
                    outerRadius={100}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {summary.categoryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} strokeWidth={0} />
                    ))}
                  </Pie>
                  <RechartsTooltip 
                    formatter={(value: number) => formatCurrency(value)}
                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                  />
                  <Legend 
                    layout="horizontal" 
                    verticalAlign="bottom" 
                    align="center"
                    iconType="circle"
                    wrapperStyle={{ paddingTop: '20px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-400">No expense data available</div>
            )}
          </div>
        </div>

        {/* Bar Chart */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 mb-6">Expense Breakdown</h3>
          <div className="flex-1 min-h-[350px]">
            {summary.categoryData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  layout="vertical"
                  data={summary.categoryData}
                  margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
                  <XAxis type="number" hide />
                  <YAxis 
                    dataKey="name" 
                    type="category" 
                    width={140} 
                    tick={{fontSize: 12, fill: '#64748b'}} 
                    axisLine={false}
                    tickLine={false}
                  />
                  <RechartsTooltip
                    cursor={{fill: '#f8fafc'}}
                    formatter={(value: number) => formatCurrency(value)}
                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={24}>
                    {summary.categoryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
               <div className="h-full flex items-center justify-center text-slate-400">No expense data available</div>
            )}
          </div>
        </div>
      </div>

      {/* Transaction Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
        <div className="p-6 border-b border-slate-100 bg-white">
          <h3 className="text-lg font-bold text-slate-900">Transaction Detail Ledger</h3>
        </div>
        <div className="overflow-x-auto flex-1 scrollbar-thin">
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="bg-slate-50 text-xs uppercase font-semibold text-slate-500 sticky top-0 border-b border-slate-200">
              <tr>
                <th className="px-6 py-4">Date</th>
                <th className="px-6 py-4">Description</th>
                <th className="px-6 py-4">Category</th>
                <th className="px-6 py-4 text-right">Debit</th>
                <th className="px-6 py-4 text-right">Credit</th>
                <th className="px-6 py-4 text-right">Balance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {transactions.map((t, idx) => (
                <tr key={idx} className="hover:bg-slate-50 transition-colors group">
                  <td className="px-6 py-3 whitespace-nowrap text-slate-500">{t.date}</td>
                  <td className="px-6 py-3 max-w-sm truncate text-slate-700 font-medium" title={t.description}>{t.description}</td>
                  <td className="px-6 py-3">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-600 group-hover:bg-white border border-transparent group-hover:border-slate-200 transition-all">
                      {t.category}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-right text-red-600 font-semibold tabular-nums">
                    {t.debit ? t.debit.toFixed(2) : <span className="text-slate-300">-</span>}
                  </td>
                  <td className="px-6 py-3 text-right text-green-600 font-semibold tabular-nums">
                    {t.credit ? t.credit.toFixed(2) : <span className="text-slate-300">-</span>}
                  </td>
                  <td className="px-6 py-3 text-right font-semibold text-slate-900 tabular-nums">
                    {t.balance.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};