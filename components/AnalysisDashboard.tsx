
import React, { useMemo } from 'react';
import { AnalysisResult, Transaction } from '../types';
import { 
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from 'recharts';
import { Download, AlertTriangle, CheckCircle, TrendingDown, TrendingUp, Wallet, Banknote, Building2, RotateCcw, ArrowDownRight, ArrowUpRight, Activity } from 'lucide-react';
import { generateExcel } from '../services/excelService';

interface AnalysisDashboardProps {
  data: AnalysisResult;
}

// Sophisticated, muted palette
const COLORS = [
  '#0f172a', // Slate 900
  '#334155', // Slate 700
  '#475569', // Slate 600
  '#64748b', // Slate 500
  '#94a3b8', // Slate 400
  '#0ea5e9', // Sky 500
  '#0284c7', // Sky 600
  '#f59e0b', // Amber 500
  '#10b981', // Emerald 500
];

export const AnalysisDashboard: React.FC<AnalysisDashboardProps> = ({ data }) => {
  const { transactions, reconciliation_failed, reconciliation_warnings, currency = 'USD', organizationName, bankName } = data;

  const summary = useMemo(() => {
    const totalDebits = transactions.reduce((sum, t) => sum + (t.debit || 0), 0);
    const totalCredits = transactions.reduce((sum, t) => sum + (t.credit || 0), 0);
    
    const categoryMap: Record<string, number> = {};
    transactions.forEach(t => {
      if (t.debit > 0) {
        categoryMap[t.category] = (categoryMap[t.category] || 0) + t.debit;
      }
    });
    
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
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
    }
  };

  return (
    <div className="space-y-8 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      
      {/* Meta Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-end gap-6 pb-6 border-b border-slate-200">
        <div>
          <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Financial Overview</h2>
          <div className="flex items-center gap-3 mt-2 text-slate-500">
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white border border-slate-200 shadow-sm text-xs font-semibold uppercase tracking-wider">
              <Building2 className="w-3 h-3 text-slate-400" />
              {organizationName}
            </div>
            <div className="w-1 h-1 rounded-full bg-slate-300"></div>
            <div className="text-sm font-medium">{bankName}</div>
          </div>
        </div>
        <button
          onClick={handleDownload}
          className="group inline-flex items-center gap-2 px-6 py-3 bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded-xl transition-all shadow-lg hover:shadow-xl hover:-translate-y-0.5"
        >
          <Download className="w-4 h-4 text-slate-300 group-hover:text-white transition-colors" />
          Export Ledger
        </button>
      </div>

      {/* Reconciliation Alerts */}
      {reconciliation_failed && (
        <div className="p-4 bg-red-50 border border-red-100 rounded-xl flex items-start gap-4 shadow-sm animate-in fade-in slide-in-from-top-2">
          <div className="p-2 bg-red-100 rounded-lg">
            <AlertTriangle className="w-5 h-5 text-red-600" />
          </div>
          <div>
            <h4 className="font-bold text-red-900">Reconciliation Discrepancy</h4>
            <p className="text-sm text-red-700 mt-1 leading-relaxed">Row-level mathematical validation failed. Running balances do not align with transaction amounts. Manual review is required.</p>
          </div>
        </div>
      )}

      {reconciliation_warnings && reconciliation_warnings.length > 0 && (
        <div className="p-4 bg-amber-50 border border-amber-100 rounded-xl flex items-start gap-4 shadow-sm animate-in fade-in slide-in-from-top-2">
           <div className="p-2 bg-amber-100 rounded-lg">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <h4 className="font-bold text-amber-900">Audit Warnings</h4>
            <ul className="text-sm text-amber-700 mt-1 space-y-1 list-disc list-inside">
              {reconciliation_warnings.map((w, idx) => <li key={idx}>{w}</li>)}
            </ul>
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-[0_8px_30px_rgb(0,0,0,0.08)] transition-shadow relative overflow-hidden group">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-red-500 to-red-600"></div>
          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">Total Outflows</p>
              <h3 className="text-3xl font-bold text-slate-900 mt-1 tracking-tight">{formatCurrency(summary.totalDebits)}</h3>
            </div>
            <div className="p-2 bg-red-50 rounded-lg group-hover:bg-red-100 transition-colors">
              <TrendingDown className="w-5 h-5 text-red-600" />
            </div>
          </div>
          <div className="flex items-center text-xs text-slate-500">
             <span className="font-medium text-slate-700">Debits processed</span>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-[0_8px_30px_rgb(0,0,0,0.08)] transition-shadow relative overflow-hidden group">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-emerald-500 to-emerald-600"></div>
          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">Total Inflows</p>
              <h3 className="text-3xl font-bold text-slate-900 mt-1 tracking-tight">{formatCurrency(summary.totalCredits)}</h3>
            </div>
             <div className="p-2 bg-emerald-50 rounded-lg group-hover:bg-emerald-100 transition-colors">
              <TrendingUp className="w-5 h-5 text-emerald-600" />
            </div>
          </div>
           <div className="flex items-center text-xs text-slate-500">
             <span className="font-medium text-slate-700">Credits processed</span>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-[0_8px_30px_rgb(0,0,0,0.08)] transition-shadow relative overflow-hidden group">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 to-blue-600"></div>
           <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">Volume</p>
              <h3 className="text-3xl font-bold text-slate-900 mt-1 tracking-tight">{transactions.length}</h3>
            </div>
             <div className="p-2 bg-blue-50 rounded-lg group-hover:bg-blue-100 transition-colors">
              <Activity className="w-5 h-5 text-blue-600" />
            </div>
          </div>
           <div className="flex items-center text-xs text-slate-500">
             <span className="font-medium text-slate-700">Transactions analyzed</span>
          </div>
        </div>
      </div>

      {/* Analytics Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Pie Chart */}
        <div className="bg-white p-8 rounded-2xl border border-slate-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 mb-6">Expense Allocation</h3>
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
                    paddingAngle={2}
                    dataKey="value"
                    stroke="none"
                  >
                    {summary.categoryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip 
                    formatter={(value: number) => [formatCurrency(value), 'Amount']}
                    contentStyle={{ 
                      borderRadius: '12px', 
                      border: '1px solid #e2e8f0', 
                      boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)',
                      fontFamily: 'Inter, sans-serif'
                    }}
                    itemStyle={{ color: '#0f172a', fontWeight: 600 }}
                  />
                  <Legend 
                    layout="horizontal" 
                    verticalAlign="bottom" 
                    align="center"
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ paddingTop: '40px', fontSize: '12px', color: '#64748b' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-slate-400">
                 <div className="w-12 h-12 rounded-full bg-slate-50 flex items-center justify-center mb-3">
                   <Banknote className="w-6 h-6 text-slate-300" />
                 </div>
                 <span>No expense data available</span>
              </div>
            )}
          </div>
        </div>

        {/* Bar Chart */}
        <div className="bg-white p-8 rounded-2xl border border-slate-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 mb-6">Category Breakdown</h3>
          <div className="flex-1 min-h-[350px]">
            {summary.categoryData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  layout="vertical"
                  data={summary.categoryData}
                  margin={{ top: 0, right: 0, left: 40, bottom: 0 }}
                  barCategoryGap={16}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                  <XAxis type="number" hide />
                  <YAxis 
                    dataKey="name" 
                    type="category" 
                    width={150} 
                    tick={{fontSize: 12, fill: '#64748b', fontWeight: 500}} 
                    axisLine={false}
                    tickLine={false}
                  />
                  <RechartsTooltip
                    cursor={{fill: '#f8fafc', radius: 4}}
                    formatter={(value: number) => [formatCurrency(value), 'Amount']}
                    contentStyle={{ 
                      borderRadius: '12px', 
                      border: '1px solid #e2e8f0', 
                      boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)',
                      fontFamily: 'Inter, sans-serif'
                    }}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={20} animationDuration={1000}>
                    {summary.categoryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
               <div className="h-full flex flex-col items-center justify-center text-slate-400">
                 <div className="w-12 h-12 rounded-full bg-slate-50 flex items-center justify-center mb-3">
                   <Banknote className="w-6 h-6 text-slate-300" />
                 </div>
                 <span>No expense data available</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Transaction Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] overflow-hidden">
        <div className="p-6 border-b border-slate-100 bg-white flex justify-between items-center">
          <h3 className="text-lg font-bold text-slate-900">Transaction Ledger</h3>
          <span className="text-xs font-medium text-slate-400 uppercase tracking-widest">{transactions.length} ENTRIES</span>
        </div>
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="bg-slate-50 text-xs uppercase font-bold text-slate-400 tracking-wider">
              <tr>
                <th className="px-8 py-4 font-semibold">Date</th>
                <th className="px-8 py-4 font-semibold">Details</th>
                <th className="px-8 py-4 font-semibold">Category</th>
                <th className="px-8 py-4 font-semibold text-right">Debit</th>
                <th className="px-8 py-4 font-semibold text-right">Credit</th>
                <th className="px-8 py-4 font-semibold text-right">Balance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {transactions.map((t, idx) => (
                <tr key={idx} className="hover:bg-slate-50/80 transition-colors group">
                  <td className="px-8 py-4 whitespace-nowrap text-slate-500 font-mono text-xs">{t.date}</td>
                  <td className="px-8 py-4 max-w-sm truncate text-slate-700 font-medium" title={t.description}>
                    <div className="flex items-center gap-2">
                      <span className="truncate">{t.description}</span>
                      {t.is_reversal && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-amber-50 text-amber-700 border border-amber-200 whitespace-nowrap shadow-sm">
                          <RotateCcw className="w-3 h-3" /> REV
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-8 py-4">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-600 group-hover:bg-white border border-transparent group-hover:border-slate-200 group-hover:shadow-sm transition-all">
                      {t.category}
                    </span>
                  </td>
                  <td className="px-8 py-4 text-right tabular-nums">
                    {t.debit ? (
                      <span className="text-slate-900 font-medium">{t.debit.toFixed(2)}</span>
                    ) : (
                      <span className="text-slate-200">-</span>
                    )}
                  </td>
                  <td className="px-8 py-4 text-right tabular-nums">
                    {t.credit ? (
                      <span className={t.credit < 0 ? "text-slate-600 font-medium" : "text-emerald-600 font-medium"}>
                         {t.credit > 0 ? "+" : ""}{t.credit.toFixed(2)}
                      </span>
                    ) : (
                      <span className="text-slate-200">-</span>
                    )}
                  </td>
                  <td className="px-8 py-4 text-right font-bold text-slate-700 tabular-nums font-mono text-xs">
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
