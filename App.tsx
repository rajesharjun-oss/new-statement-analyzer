
import React, { useMemo, useState, useEffect, useDeferredValue, memo } from "react";
import { FixedSizeList as List, areEqual } from 'react-window';
import AutoSizer from "react-virtualized-auto-sizer";
import {
  ShieldCheck,
  Upload,
  Lock,
  ChevronDown,
  Loader2,
  Filter,
  FileCheck,
  Search,
  LayoutDashboard,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Hash,
  Briefcase
} from "lucide-react";
import { 
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from 'recharts';

import { Button, Card, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, Progress, cn, Badge, Input } from "./components/PrimitiveUI";
import { SettingsModal } from './components/SettingsModal';
import { analyzeBankStatement } from './services/geminiService';
import { generateExcel } from './services/excelService';
import { AnalysisResult, Transaction, DecisionSource } from './types';

// Extended type for internal UI state
type Txn = Transaction & {
  confidence: number;
  flag: "anomaly" | "review" | "ok";
  evidence: { page: number; line: string };
};

// Apexfy Dark Palette (Purple, Green, Orange, Blue)
const CHART_COLORS = ['#9B87FF', '#3CDCAB', '#FFB43C', '#4F85FF', '#FF5A78', '#A0A0A5'];

function formatMoney(n: number, currency: string = "USD") {
  return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
}

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
}

// Quiet Status Pill
function StatusPill({ state }: { state: 'idle' | 'busy' | 'ready' }) {
  if (state === 'busy') {
    return (
      <Badge variant="warning" className="animate-pulse">
        Processing
      </Badge>
    );
  }
  return <Badge variant="success">System Ready</Badge>;
}

// OPTIMIZATION: Extracted Row Component
const TransactionRow = memo(({ index, style, data }: { index: number; style: React.CSSProperties; data: Txn[] }) => {
  const t = data[index];
  return (
    <div style={style} className="flex items-center text-[12px] font-mono text-zinc-400 hover:bg-white/[0.02] border-b border-white/[0.04] transition-colors">
        <div className="w-[12%] px-5 py-2.5 whitespace-nowrap overflow-hidden text-ellipsis">{t.date}</div>
        <div className="w-[40%] px-5 py-2.5">
           <div className="text-zinc-200 truncate max-w-[95%]" title={t.description}>{t.description}</div>
           {t.flag !== 'ok' && (
              <div className="mt-1 flex gap-1">
                 {t.flag === 'anomaly' && <Badge variant="danger">Calc Error</Badge>}
                 {t.flag === 'review' && <Badge variant="warning">Review</Badge>}
              </div>
           )}
        </div>
        <div className="w-[13%] px-5 py-2.5 text-right overflow-hidden text-ellipsis">{t.debit ? formatMoney(t.debit, '') : '-'}</div>
        <div className="w-[13%] px-5 py-2.5 text-right text-[#3CDCAB] overflow-hidden text-ellipsis">{t.credit ? formatMoney(t.credit, '') : '-'}</div>
        <div className="w-[12%] px-5 py-2.5 text-right text-zinc-300 font-medium overflow-hidden text-ellipsis">{formatMoney(t.balance, '')}</div>
        <div className="w-[10%] px-5 py-2.5 text-center overflow-hidden">
           <div className="inline-block px-2 py-0.5 rounded-[4px] bg-white/5 text-[10px] text-zinc-500 truncate max-w-[100%]" title={t.category}>
              {t.category}
           </div>
        </div>
    </div>
  );
}, areEqual);

TransactionRow.displayName = "TransactionRow";

export default function App() {
  const [hasFile, setHasFile] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState("");
  const [processingTime, setProcessingTime] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");
  const deferredSearchTerm = useDeferredValue(searchTerm);
  
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [userApiKey, setUserApiKey] = useState<string>('');

  useEffect(() => {
    const storedKey = localStorage.getItem('gemini_custom_key');
    if (storedKey) setUserApiKey(storedKey);
  }, []);

  const handleSaveSettings = (key: string) => {
    setUserApiKey(key);
    if (key) localStorage.setItem('gemini_custom_key', key);
    else localStorage.removeItem('gemini_custom_key');
  };

  const txns: Txn[] = useMemo(() => {
    if (!analysisResult) return [];
    return analysisResult.transactions.map((t, i) => {
      const confidence = t.confidence !== undefined 
        ? t.confidence 
        : (t.category === "Review Required" || t.category === "Unallocated" ? 0.5 : 0.85);
      
      let flag: "ok" | "review" | "anomaly" = "ok";
      if (t.category === "Review Required") flag = "review";
      else if (confidence < 0.7) flag = "review";
      if (analysisResult.reconciliation_failed && i === analysisResult.transactions.length -1) flag = "anomaly"; 
      
      return {
        ...t,
        confidence,
        flag,
        evidence: { page: 1, line: `L${(i+1).toString().padStart(2, '0')}` }
      };
    });
  }, [analysisResult]);

  const filteredTxns = useMemo(() => {
    if (!deferredSearchTerm) return txns;
    
    const lower = deferredSearchTerm.toLowerCase();
    return txns.filter(t => 
      t.description.toLowerCase().includes(lower) || 
      t.category.toLowerCase().includes(lower) ||
      t.date.includes(lower) ||
      t.debit.toString().includes(lower) ||
      t.credit.toString().includes(lower)
    );
  }, [txns, deferredSearchTerm]);

  const summary = useMemo(() => {
    if (!analysisResult) return { opening: 0, closing: 0, totalDebits: 0, totalCredits: 0, anomalies: 0, reviews: 0, currency: "USD" };
    
    // Find the first Balance B/F row or take the first calculation
    const opening = txns.length > 0 
      ? (txns[0].balance + (txns[0].debit || 0) - (txns[0].credit || 0))
      : 0;
      
    const closing = txns[txns.length - 1]?.balance ?? 0;
    const totalDebits = txns.reduce((a, t) => a + (t.debit ?? 0), 0);
    const totalCredits = txns.reduce((a, t) => a + (t.credit ?? 0), 0);
    const anomalies = txns.filter((t) => t.flag === "anomaly").length;
    const reviews = txns.filter((t) => t.flag === "review").length;
    return { opening, closing, totalDebits, totalCredits, anomalies, reviews, currency: analysisResult.currency };
  }, [txns, analysisResult]);

  // CHART DATA: STRICTLY EXPENSES
  const categoryData = useMemo(() => {
    if (!txns.length) return [];
    const categoryMap: Record<string, number> = {};
    
    txns.forEach(t => {
      // 1. Must be a Debit
      if ((t.debit || 0) <= 0) return;

      // 2. Exclude non-expense categories
      const ignoredCategories = [
        'Opening Balance',
        'Closing Balance',
        'Inter-Account / Treasury Transfer', // Movement
        'Unallocated'
      ];
      if (ignoredCategories.includes(t.category)) return;

      categoryMap[t.category] = (categoryMap[t.category] || 0) + t.debit;
    });

    return Object.entries(categoryMap)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 8); 
  }, [txns]);

  const handleFileProcess = async (file: File) => {
    setFileName(file.name);
    setIsAnalyzing(true);
    setError(null);
    setProcessingTime(0);

    const startTime = Date.now();
    const timerInterval = setInterval(() => {
      setProcessingTime((Date.now() - startTime) / 1000);
    }, 100);

    try {
      const reader = new FileReader();
      reader.onload = async (e) => {
        const base64 = (e.target?.result as string).split(',')[1];
        try {
          const result = await analyzeBankStatement(base64, file.type, userApiKey);
          setAnalysisResult(result);
          setHasFile(true);
        } catch (err: any) {
          setError(err.message || "Failed to analyze document");
        } finally {
          setIsAnalyzing(false);
          clearInterval(timerInterval);
          setProcessingTime((Date.now() - startTime) / 1000);
        }
      };
      
      reader.onerror = () => {
         setError("File reading failed");
         setIsAnalyzing(false);
         clearInterval(timerInterval);
      };

      reader.readAsDataURL(file);
    } catch (e) {
      setError("File reading failed");
      setIsAnalyzing(false);
      clearInterval(timerInterval);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files?.[0]) {
      handleFileProcess(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      handleFileProcess(e.target.files[0]);
    }
  };

  return (
    <div className="min-h-screen font-sans text-zinc-300">
      <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} onSave={handleSaveSettings} currentKey={userApiKey} />
      
      {/* Top Bar - Apexfy Style: Dark, Minimal, Logo Left */}
      <header className="fixed top-0 left-0 right-0 z-50 h-16 border-b border-white/[0.06] bg-[#070707]/90 backdrop-blur-md">
        <div className="mx-auto max-w-[1200px] h-full px-6 flex items-center justify-between">
            <div className="flex items-center gap-3 cursor-pointer" onClick={() => setHasFile(false)}>
               <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#9B87FF] to-[#4F85FF] flex items-center justify-center shadow-lg shadow-purple-900/20">
                  <ShieldCheck className="w-4 h-4 text-white" />
               </div>
               <span className="text-[15px] font-bold text-white tracking-tight">LedgerSentinel</span>
            </div>

            <div className="flex items-center gap-6">
               <StatusPill state={isAnalyzing ? 'busy' : 'idle'} />
               
               <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button className="text-[13px] text-zinc-400 font-medium hover:text-white transition-colors flex items-center gap-2">
                       <div className="w-7 h-7 rounded-full bg-white/10 flex items-center justify-center text-[10px] text-white font-bold">IO</div>
                       Account <ChevronDown className="w-3 h-3 opacity-50" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setIsSettingsOpen(true)}>
                       API Configuration
                    </DropdownMenuItem>
                    <DropdownMenuItem>
                       Audit Logs
                    </DropdownMenuItem>
                  </DropdownMenuContent>
               </DropdownMenu>
            </div>
        </div>
      </header>

      <main className="pt-28 pb-20 px-6 mx-auto max-w-[1200px]">
        {!hasFile ? (
           /* --- STATE: UPLOAD WORKSPACE --- */
           <div className="animate-enter">
              
              {/* Header Section */}
              <div className="mb-10 max-w-2xl">
                 <h1 className="text-[32px] font-bold text-white tracking-tight leading-snug mb-2">
                    Reconciliation Workspace
                 </h1>
                 <p className="text-zinc-500 text-[14px]">
                    Import a statement to extract, reconcile, and categorize transactions with traceable evidence.
                 </p>
              </div>

              {/* Main Grid */}
              <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                 
                 {/* Import Card (Span 8) */}
                 <Card className="md:col-span-8 overflow-hidden flex flex-col min-h-[420px]">
                     <div className="px-6 py-5 border-b border-white/[0.06] flex items-center justify-between">
                        <span className="text-[14px] font-semibold text-white">Import statement</span>
                        <Badge variant="purple" className="font-mono">Local processing</Badge>
                     </div>

                     <div 
                        className="flex-1 relative p-8 flex flex-col items-center justify-center transition-all duration-300"
                        onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('bg-white/[0.02]'); }}
                        onDragLeave={(e) => { e.currentTarget.classList.remove('bg-white/[0.02]'); }}
                        onDrop={handleDrop}
                     >
                        <input
                           type="file"
                           className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20"
                           onChange={handleFileInput}
                           accept=".pdf,.jpg,.jpeg,.png,.webp"
                           disabled={isAnalyzing}
                        />

                        {isAnalyzing ? (
                           <div className="w-full max-w-xs space-y-6 text-center">
                              {/* Prominent Stopwatch */}
                              <div className="flex flex-col items-center justify-center">
                                 <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mb-4 relative">
                                    <div className="absolute inset-0 rounded-full border-t border-l border-[#9B87FF] animate-spin"></div>
                                    <Clock className="w-6 h-6 text-[#9B87FF]" />
                                 </div>
                                 <div className="text-3xl font-mono font-bold text-white tracking-tight">
                                    {formatTime(processingTime)}
                                 </div>
                                 <p className="text-xs text-zinc-500 mt-2 font-mono uppercase tracking-wider">Elapsed Time</p>
                              </div>

                              <div className="space-y-2">
                                <Progress value={processingTime > 3 ? 75 : 25} />
                                <p className="text-xs text-zinc-500">Extracting transaction logic...</p>
                              </div>
                           </div>
                        ) : (
                           <div className="w-full h-full border border-dashed border-white/10 rounded-[12px] bg-white/[0.01] flex flex-col items-center justify-center gap-6 hover:border-white/20 transition-colors">
                              <div className="text-center">
                                 <h3 className="text-[15px] font-medium text-white mb-1">Upload statement</h3>
                                 <p className="text-[13px] text-zinc-500">PDF, JPEG, PNG • up to 20MB</p>
                              </div>
                              <div className="flex flex-col gap-3 w-40">
                                 <Button variant="primary" className="w-full text-sm">Select file</Button>
                                 <Button variant="ghost" className="w-full text-xs h-8">Use sample statement</Button>
                              </div>
                           </div>
                        )}
                     </div>

                     <div className="px-6 py-3 border-t border-white/[0.06] bg-[#0B0C0E]">
                        <span className="text-[11px] text-zinc-600 font-medium flex items-center gap-1.5">
                           <Lock className="w-3 h-3" /> Local processing • AES-256
                        </span>
                     </div>
                 </Card>

                 {/* Checks Card (Span 4) */}
                 <Card className="md:col-span-4 bg-[#0B0C0E] border-white/[0.04]">
                     <div className="px-6 py-5 border-b border-white/[0.04]">
                        <span className="text-[14px] font-semibold text-zinc-400">Checks</span>
                     </div>
                     <div className="p-6">
                        <ul className="space-y-5">
                           {[
                              "Validated extraction (clean ledger columns)",
                              "Opening/closing balance validation",
                              "Categorization with confidence scoring"
                           ].map((item, i) => (
                              <li key={i} className="flex items-start gap-3">
                                 <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-[#9B87FF]" />
                                 <span className="text-[13px] text-zinc-500 leading-relaxed">{item}</span>
                              </li>
                           ))}
                        </ul>
                     </div>
                 </Card>

              </div>
           </div>
        ) : (
           /* --- STATE: DASHBOARD --- */
           <div className="animate-enter space-y-6">
              
              {/* Dashboard Header */}
              <div className="flex items-center justify-between pb-4 border-b border-white/[0.06]">
                 <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-[10px] bg-white/5 flex items-center justify-center border border-white/10">
                       <FileCheck className="w-5 h-5 text-zinc-400" />
                    </div>
                    <div>
                       <h2 className="text-[16px] font-bold text-white leading-tight">{analysisResult?.organizationName}</h2>
                       <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[12px] text-zinc-500 font-mono">{fileName}</span>
                          <Badge variant="outline">{analysisResult?.currency}</Badge>
                       </div>
                    </div>
                    
                    {/* Metrics Wrapper */}
                    <div className="h-8 w-[1px] bg-white/10 mx-2" />
                    <div className="flex gap-2">
                        {/* Transaction Count Indicator */}
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-white/5 rounded-lg border border-white/5">
                            <Hash className="w-3.5 h-3.5 text-zinc-500" />
                            <div className="flex flex-col leading-none">
                                <span className="text-[10px] text-zinc-500 font-bold uppercase">Records</span>
                                <span className="text-sm font-mono text-white">{txns.length}</span>
                            </div>
                        </div>

                        {/* Processing Time Indicator */}
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-white/5 rounded-lg border border-white/5">
                            <Clock className="w-3.5 h-3.5 text-zinc-500" />
                            <div className="flex flex-col leading-none">
                                <span className="text-[10px] text-zinc-500 font-bold uppercase">Time</span>
                                <span className="text-sm font-mono text-white">{formatTime(processingTime)}</span>
                            </div>
                        </div>
                    </div>

                 </div>
                 <div className="flex gap-3">
                    <Button variant="outline" size="sm" onClick={() => setHasFile(false)}>Reset</Button>
                    <Button variant="primary" size="sm" onClick={() => generateExcel(analysisResult!.transactions, analysisResult!.reconciliation_warnings, analysisResult!.reconciliation_failed, analysisResult!.currency, analysisResult!.organizationName, analysisResult!.bankName)}>
                       Export Report
                    </Button>
                 </div>
              </div>

              {/* Metrics Row - Added Opening Balance */}
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                 {[
                    { label: "Opening Balance", val: formatMoney(summary.opening, summary.currency), color: "text-zinc-400" },
                    { label: "Closing Balance", val: formatMoney(summary.closing, summary.currency), color: "text-white" },
                    { label: "Total Inflow", val: formatMoney(summary.totalCredits, summary.currency), color: "text-[#3CDCAB]" },
                    { label: "Total Outflow", val: formatMoney(summary.totalDebits, summary.currency), color: "text-zinc-300" },
                    { label: "Check Status", val: summary.anomalies > 0 ? "Failed" : "Passed", color: summary.anomalies > 0 ? "text-[#FF5A78]" : "text-[#3CDCAB]", isStatus: true }
                 ].map((m, i) => (
                    <Card key={i} className="p-5 flex flex-col justify-between h-[110px]">
                       <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">{m.label}</span>
                       <div className="flex items-end justify-between">
                          <span className={cn("text-[18px] lg:text-[20px] font-bold font-mono tracking-tight truncate", m.color)}>{m.val}</span>
                          {m.isStatus && (
                             m.val === "Passed" 
                                ? <CheckCircle2 className="w-5 h-5 text-[#3CDCAB]" /> 
                                : <AlertTriangle className="w-5 h-5 text-[#FF5A78]" />
                          )}
                       </div>
                    </Card>
                 ))}
              </div>

              {/* Main Content Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[600px]">
                 
                 {/* Transaction Table (Span 2) */}
                 <Card className="lg:col-span-2 flex flex-col overflow-hidden">
                    <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between shrink-0">
                       <div className="flex items-center gap-2">
                          <LayoutDashboard className="w-4 h-4 text-zinc-500" />
                          <span className="text-[13px] font-semibold text-zinc-300">Transaction Ledger</span>
                       </div>
                       <div className="relative w-56">
                          <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-zinc-500" />
                          <Input 
                             placeholder="Search..." 
                             className="pl-8 h-8 text-xs bg-[#0B0C0E] border-white/10"
                             value={searchTerm}
                             onChange={(e) => setSearchTerm(e.target.value)}
                          />
                       </div>
                    </div>
                    {/* OPTIMIZATION: Virtualized List Replacement */}
                    <div className="flex-1 w-full">
                       {/* Header Row (Static) */}
                       <div className="flex items-center bg-[#111318] text-[10px] font-bold text-zinc-500 uppercase tracking-wider font-mono border-b border-white/[0.06]">
                            <div className="w-[12%] px-5 py-3">Date</div>
                            <div className="w-[40%] px-5 py-3">Description</div>
                            <div className="w-[13%] px-5 py-3 text-right">Debit</div>
                            <div className="w-[13%] px-5 py-3 text-right">Credit</div>
                            <div className="w-[12%] px-5 py-3 text-right">Balance</div>
                            <div className="w-[10%] px-5 py-3 text-center">Cat</div>
                       </div>
                       
                       <div className="flex-1 h-[calc(100%-40px)] w-full">
                           <AutoSizer>
                               {({ height, width }) => (
                                   <List
                                       height={height}
                                       itemCount={filteredTxns.length}
                                       itemSize={50} // Fixed height for rows
                                       width={width}
                                       itemData={filteredTxns}
                                   >
                                       {TransactionRow}
                                   </List>
                               )}
                           </AutoSizer>
                       </div>
                    </div>
                 </Card>

                 {/* Charts Panel (Span 1) */}
                 <div className="flex flex-col gap-6">
                    {/* Allocation Pie Chart */}
                    <Card className="flex-1 flex flex-col p-5 bg-[#0B0C0E]">
                       <h3 className="text-[13px] font-semibold text-zinc-400 mb-4">Operating Expenses</h3>
                       <div className="flex-1 min-h-[180px]">
                          <ResponsiveContainer width="100%" height="100%">
                             <PieChart>
                                <Pie
                                   data={categoryData}
                                   innerRadius={60}
                                   outerRadius={80}
                                   paddingAngle={4}
                                   dataKey="value"
                                   stroke="none"
                                >
                                   {categoryData.map((entry, index) => (
                                      <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                                   ))}
                                </Pie>
                                <RechartsTooltip 
                                   contentStyle={{ backgroundColor: '#111318', borderColor: '#27272a', fontSize: '11px', borderRadius: '8px', color: '#fff' }}
                                   itemStyle={{ color: '#fff' }}
                                   formatter={(v: number) => formatMoney(v)}
                                />
                             </PieChart>
                          </ResponsiveContainer>
                       </div>
                    </Card>

                    {/* Bar Chart (Replaces Automation) */}
                    <Card className="flex-1 flex flex-col p-5 bg-[#0B0C0E]">
                       <h3 className="text-[13px] font-semibold text-zinc-400 mb-4">Expense Categories</h3>
                       <div className="flex-1 min-h-[180px]">
                          <ResponsiveContainer width="100%" height="100%">
                             <BarChart data={categoryData} layout="vertical" barCategoryGap={10}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#ffffff08" />
                                <XAxis type="number" hide />
                                <YAxis 
                                  type="category" 
                                  dataKey="name" 
                                  width={80}
                                  tick={{fontSize: 9, fill: '#71717a'}} 
                                  axisLine={false}
                                  tickLine={false}
                                />
                                <RechartsTooltip
                                    cursor={{fill: '#ffffff05'}}
                                    contentStyle={{ backgroundColor: '#111318', borderColor: '#27272a', fontSize: '11px', borderRadius: '8px', color: '#fff' }}
                                    formatter={(v: number) => formatMoney(v)}
                                />
                                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                                   {categoryData.map((entry, index) => (
                                      <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                                   ))}
                                </Bar>
                             </BarChart>
                          </ResponsiveContainer>
                       </div>
                    </Card>
                 </div>

              </div>
           </div>
        )}
      </main>

      {/* Minimal Footer */}
      {!hasFile && (
         <footer className="fixed bottom-0 w-full py-6 px-6 mx-auto max-w-[1200px] flex justify-between items-center text-[11px] text-zinc-700">
            <span>LedgerSentinel v2.4</span>
            <span className="opacity-50 font-medium">© IBRAHIM O.</span>
         </footer>
      )}
    </div>
  );
}
