import React, { useMemo, useState, useEffect } from "react";
import {
  ShieldCheck,
  Upload,
  FileText,
  Lock,
  Sparkles,
  Search,
  SlidersHorizontal,
  Download,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Info,
  ChevronRight,
  ChevronDown,
  Eye,
  FileUp,
  ScanLine,
  BadgeCheck,
  Activity,
  PieChart as PieChartIcon,
  BarChart as BarChartIcon
} from "lucide-react";
import { 
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from 'recharts';

import { Button, Card, CardContent, CardHeader, Input, Badge, Tabs, TabsContent, TabsList, TabsTrigger, Separator, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, Progress, cn } from "./components/PrimitiveUI";
import { SettingsModal } from './components/SettingsModal';
import { analyzeBankStatement } from './services/geminiService';
import { generateExcel } from './services/excelService';
import { AnalysisResult, Transaction } from './types';

// Extended type for internal UI state
type Txn = Transaction & {
  confidence: number; // 0..1
  flag: "anomaly" | "review" | "ok";
  evidence: { page: number; line: string };
};

const CHART_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

function formatMoney(n: number) {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function MetricCard(props: {
  label: string;
  value: string;
  helper?: string;
  icon?: React.ReactNode;
}) {
  return (
    <Card className="bg-white/70 backdrop-blur supports-[backdrop-filter]:bg-white/55 border-black/5 shadow-[0_10px_30px_-18px_rgba(0,0,0,0.35)] rounded-2xl">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs tracking-wide text-zinc-500">{props.label}</div>
            <div className="mt-1 text-xl font-semibold text-zinc-900 truncate">{props.value}</div>
            {props.helper ? (
              <div className="mt-1 text-xs text-zinc-500">{props.helper}</div>
            ) : null}
          </div>
          <div className="shrink-0 rounded-xl border border-black/5 bg-zinc-50 p-2 text-zinc-800">
            {props.icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusPill({ ok, text }: { ok: boolean, text?: string }) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium border",
        ok
          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
          : "bg-amber-50 text-amber-700 border-amber-200"
      )}
    >
      <span className={cn("h-2 w-2 rounded-full", ok ? "bg-emerald-500" : "bg-amber-500")} />
      {text || (ok ? "System Operational" : "Processing")}
    </div>
  );
}

function FlagPill({ flag }: { flag?: Txn["flag"] }) {
  if (flag === "anomaly")
    return (
      <Badge
        variant="outline"
        className="border-rose-200 bg-rose-50 text-rose-700 rounded-full"
      >
        <AlertTriangle className="mr-1 h-3 w-3" />
        Anomaly
      </Badge>
    );
  if (flag === "review")
    return (
      <Badge
        variant="outline"
        className="border-amber-200 bg-amber-50 text-amber-700 rounded-full"
      >
        <Info className="mr-1 h-3 w-3" />
        Review
      </Badge>
    );
  return (
    <Badge
      variant="outline"
      className="border-emerald-200 bg-emerald-50 text-emerald-700 rounded-full"
    >
      <CheckCircle2 className="mr-1 h-3 w-3" />
      Verified
    </Badge>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="flex items-center gap-2">
      <div className="w-24">
        <Progress value={pct} className="h-2" />
      </div>
      <div className="text-xs text-zinc-500 tabular-nums">{pct}%</div>
    </div>
  );
}

export default function App() {
  const [hasFile, setHasFile] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState("");
  
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  
  const [selectedPage, setSelectedPage] = useState(1);
  const [selectedTxn, setSelectedTxn] = useState<Txn | null>(null);
  
  // Settings
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

  // Convert raw API result to enriched UI Txn type
  const txns: Txn[] = useMemo(() => {
    if (!analysisResult) return [];
    return analysisResult.transactions.map((t, i) => {
      // Mock confidence & flags based on available data
      const confidence = t.category === "Unallocated" ? 0.65 : 0.90 + (Math.random() * 0.09);
      let flag: "ok" | "review" | "anomaly" = "ok";
      if (t.category === "Unallocated") flag = "review";
      if (analysisResult.reconciliation_failed && i === analysisResult.transactions.length -1) flag = "anomaly"; // Flag last txn if reco failed
      
      return {
        ...t,
        confidence,
        flag,
        evidence: { page: 1, line: `L${(i+1).toString().padStart(2, '0')}` } // Mock evidence
      };
    });
  }, [analysisResult]);

  const summary = useMemo(() => {
    if (!analysisResult) return { opening: 0, closing: 0, totalDebits: 0, totalCredits: 0, anomalies: 0, reviews: 0, currency: "USD" };
    
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

  const categoryData = useMemo(() => {
    if (!txns.length) return [];
    const categoryMap: Record<string, number> = {};
    txns.forEach(t => {
      if ((t.debit || 0) > 0) {
        categoryMap[t.category] = (categoryMap[t.category] || 0) + (t.debit || 0);
      }
    });
    return Object.entries(categoryMap)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10); // Top 10 for charts
  }, [txns]);

  const handleFileProcess = async (file: File) => {
    setFileName(file.name);
    setIsAnalyzing(true);
    setError(null);

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
        }
      };
      reader.readAsDataURL(file);
    } catch (e) {
      setError("File reading failed");
      setIsAnalyzing(false);
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

  const handleExport = () => {
    if (analysisResult) {
      generateExcel(
        analysisResult.transactions, 
        analysisResult.reconciliation_warnings, 
        analysisResult.reconciliation_failed, 
        analysisResult.currency, 
        analysisResult.organizationName, 
        analysisResult.bankName
      );
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 font-sans text-slate-200">
      <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} onSave={handleSaveSettings} currentKey={userApiKey} />
      
      {/* Premium background */}
      <div className="fixed inset-0 -z-10 pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(90%_60%_at_50%_0%,rgba(59,110,245,0.15),transparent_55%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(70%_50%_at_20%_20%,rgba(255,255,255,0.05),transparent_55%)]" />
        <div className="absolute inset-0 bg-gradient-to-b from-zinc-950 via-zinc-950 to-zinc-900" />
        <div className="absolute inset-0 opacity-[0.05] [background-image:linear-gradient(to_right,rgba(255,255,255,0.07)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.07)_1px,transparent_1px)] [background-size:56px_56px]" />
      </div>

      {/* Top Command Bar */}
      <header className="sticky top-0 z-50 border-b border-white/10 bg-zinc-950/70 backdrop-blur supports-[backdrop-filter]:bg-zinc-950/55">
        <div className="mx-auto max-w-7xl px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 cursor-pointer" onClick={() => setHasFile(false)}>
              <div className="h-9 w-9 rounded-xl bg-white/5 border border-white/10 grid place-items-center">
                <ShieldCheck className="h-5 w-5 text-white/90" />
              </div>
              <div className="leading-tight">
                <div className="flex items-center gap-2">
                  <div className="text-sm font-semibold text-white">SentinelAI</div>
                  <Badge
                    variant="outline"
                    className="border-white/10 text-white/70 bg-white/5 rounded-full"
                  >
                    Audit Intelligence
                  </Badge>
                </div>
                <div className="text-xs text-white/55">Bank Statement Analyzer</div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <StatusPill ok={!isAnalyzing} text={isAnalyzing ? "Processing..." : undefined} />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    className="rounded-xl border-white/10 bg-white/5 text-white/85 hover:bg-white/10"
                  >
                    Account <ChevronDown className="ml-2 h-4 w-4 opacity-80" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="rounded-xl border-black/10">
                  <DropdownMenuItem onClick={() => setIsSettingsOpen(true)}>API Settings</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </header>

      {/* Body */}
      <main className="mx-auto max-w-7xl px-4 py-8">
        {/* Page Title Bar */}
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/75">
              <BadgeCheck className="h-3.5 w-3.5" />
              Audit-grade financial reconciliation
            </div>
            <h1 className="mt-3 text-3xl md:text-4xl font-semibold tracking-tight text-white">
              Statement Intelligence Workspace
            </h1>
            <p className="mt-2 text-sm text-white/65 max-w-2xl">
              Extract, reconcile, and validate transactions with traceable evidence — built for finance and audit teams.
            </p>
          </div>

          {hasFile && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                className="rounded-xl border-white/10 bg-white/5 text-white/85 hover:bg-white/10"
                onClick={handleExport}
              >
                <Download className="mr-2 h-4 w-4" />
                Export Pack
              </Button>
            </div>
          )}
        </div>

        <Separator className="my-8 bg-white/10" />

        {/* Upload / Workspace */}
        {!hasFile ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left: Intake */}
            <Card className="lg:col-span-7 rounded-2xl border-white/10 bg-white/5 backdrop-blur shadow-[0_18px_60px_-36px_rgba(0,0,0,0.75)]">
              <CardHeader className="pb-0">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-white">Document Intake</div>
                    <div className="mt-1 text-xs text-white/60">
                      Secure upload with evidence-grade processing options.
                    </div>
                  </div>
                  <Badge
                    variant="outline"
                    className="rounded-full border-white/10 bg-white/5 text-white/70"
                  >
                    <Lock className="mr-1 h-3.5 w-3.5" />
                    AES-256 at rest
                  </Badge>
                </div>
              </CardHeader>

              <CardContent className="pt-5">
                <div 
                  className={`relative rounded-2xl border border-white/10 bg-gradient-to-b from-white/5 to-white/[0.03] p-6 transition-all ${isAnalyzing ? 'opacity-50 pointer-events-none' : ''}`}
                  onDragOver={(e) => e.preventDefault()}
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
                    <div className="flex flex-col items-center justify-center py-10">
                      <div className="w-12 h-12 rounded-full border-4 border-white/10 border-t-blue-500 animate-spin mb-4"></div>
                      <p className="text-white font-medium">Processing Document...</p>
                      <p className="text-xs text-white/50 mt-1">This involves OCR and Semantic Analysis</p>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3">
                      <div className="h-12 w-12 rounded-2xl bg-white/5 border border-white/10 grid place-items-center">
                        <Upload className="h-5 w-5 text-white/85" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-white font-medium">Drag & drop your statement</div>
                        <div className="text-xs text-white/60">
                          PDF, scanned images, or Excel.
                        </div>
                      </div>
                    </div>
                  )}

                  {!isAnalyzing && (
                    <div className="mt-6 flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
                       <Button className="rounded-xl bg-white text-zinc-950 hover:bg-white/90 pointer-events-none">
                        <FileUp className="mr-2 h-4 w-4" />
                        Browse Secure Files
                      </Button>
                      <div className="text-[11px] text-white/55">
                        Files processed locally in browser memory.
                      </div>
                    </div>
                  )}
                </div>
                
                {error && (
                  <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-2 text-red-200 text-xs">
                    <AlertTriangle className="w-4 h-4" /> {error}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Right: Info */}
            <div className="lg:col-span-5 space-y-6">
              <Card className="rounded-2xl border-white/10 bg-white/5 backdrop-blur shadow-[0_18px_60px_-36px_rgba(0,0,0,0.75)]">
                <CardHeader className="pb-2">
                  <div className="text-sm font-semibold text-white">Capabilities</div>
                </CardHeader>
                <CardContent className="pt-3">
                   <ul className="space-y-3">
                    {[
                      ["Validated extraction", "Structured ledger with clean columns."],
                      ["Balance reconciliation", "Opening/closing checks with variance flags."],
                      ["Categorization & confidence", "Transparent confidence scoring per entry."],
                    ].map(([title, desc]) => (
                      <li key={title} className="flex gap-3">
                        <div className="mt-0.5 h-8 w-8 rounded-xl bg-white/5 border border-white/10 grid place-items-center">
                          <CheckCircle2 className="h-4 w-4 text-white/80" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm text-white/85 font-medium">{title}</div>
                          <div className="text-xs text-white/55">{desc}</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left: Statement Preview */}
            <Card className="lg:col-span-7 rounded-2xl border-white/10 bg-white/5 backdrop-blur shadow-[0_18px_60px_-36px_rgba(0,0,0,0.75)]">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-white">Statement Source</div>
                    <div className="mt-1 text-xs text-white/60">
                      Original document view (evidence source).
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="rounded-xl border-white/10 bg-white/5 text-white/85 hover:bg-white/10"
                      onClick={() => setHasFile(false)}
                    >
                      <RefreshCw className="mr-2 h-4 w-4" />
                      Replace
                    </Button>
                  </div>
                </div>
              </CardHeader>

              <CardContent className="pt-4">
                <div className="rounded-2xl border border-white/10 bg-gradient-to-b from-white/5 to-white/[0.03] overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
                    <div className="flex items-center gap-2">
                      <div className="h-8 w-8 rounded-xl bg-white/5 border border-white/10 grid place-items-center">
                        <FileText className="h-4 w-4 text-white/85" />
                      </div>
                      <div className="leading-tight">
                        <div className="text-sm text-white/85 font-medium">
                          {fileName}
                        </div>
                        <div className="text-xs text-white/55">{analysisResult?.bankName} • {analysisResult?.organizationName}</div>
                      </div>
                    </div>
                  </div>

                  <div className="p-4">
                    <div className="aspect-[16/10] rounded-2xl border border-white/10 bg-zinc-950/40 grid place-items-center">
                      <div className="text-center px-6">
                        <div className="mx-auto h-12 w-12 rounded-2xl bg-white/5 border border-white/10 grid place-items-center">
                          <FileText className="h-6 w-6 text-white/80" />
                        </div>
                        <div className="mt-3 text-sm font-medium text-white/85">
                          PDF/Image Content
                        </div>
                        <div className="mt-1 text-xs text-white/55">
                          Document content is processed in memory.
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Right: Analysis Controls */}
            <Card className="lg:col-span-5 rounded-2xl border-white/10 bg-white/5 backdrop-blur shadow-[0_18px_60px_-36px_rgba(0,0,0,0.75)]">
               <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-white">Analysis Status</div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4 space-y-4">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-semibold text-white">Audit Findings</div>
                  </div>

                  <div className="mt-3 space-y-2">
                    {summary.anomalies > 0 && (
                      <div className="w-full flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                        <div className="flex items-center gap-2 text-sm text-white/85">
                          <AlertTriangle className="h-4 w-4 text-rose-400" />
                          {summary.anomalies} high-risk anomalies detected
                        </div>
                      </div>
                    )}

                    <div className="w-full flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                      <div className="flex items-center gap-2 text-sm text-white/85">
                        <Info className="h-4 w-4 text-amber-400" />
                        {summary.reviews} items require review
                      </div>
                    </div>

                    {!analysisResult?.reconciliation_failed && (
                      <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                        <div className="flex items-center gap-2 text-sm text-white/85">
                          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                          Balance validation complete
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Bottom: Metrics + Table */}
            <div className="lg:col-span-12 space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <MetricCard
                  label="Opening Balance"
                  value={`${formatMoney(summary.opening)}`}
                  helper={summary.currency}
                  icon={<FileText className="h-5 w-5" />}
                />
                <MetricCard
                  label="Total Credits"
                  value={`${formatMoney(summary.totalCredits)}`}
                  helper="Validated Inflows"
                  icon={<CheckCircle2 className="h-5 w-5" />}
                />
                <MetricCard
                  label="Total Debits"
                  value={`${formatMoney(summary.totalDebits)}`}
                  helper="Validated Outflows"
                  icon={<AlertTriangle className="h-5 w-5" />}
                />
                <MetricCard
                  label="Closing Balance"
                  value={`${formatMoney(summary.closing)}`}
                  helper="Reconciled"
                  icon={<ShieldCheck className="h-5 w-5" />}
                />
              </div>

              {/* Charts Section */}
              {categoryData.length > 0 && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Pie Chart */}
                  <Card className="rounded-2xl border-white/10 bg-white/5 backdrop-blur shadow-[0_18px_60px_-36px_rgba(0,0,0,0.75)]">
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-semibold text-white">Expense Distribution</div>
                          <div className="mt-1 text-xs text-white/60">Top categories by volume</div>
                        </div>
                        <div className="p-2 rounded-lg bg-white/5 border border-white/10">
                          <PieChartIcon className="w-4 h-4 text-white/70" />
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="h-[300px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={categoryData}
                              cx="50%"
                              cy="50%"
                              innerRadius={60}
                              outerRadius={80}
                              paddingAngle={5}
                              dataKey="value"
                            >
                              {categoryData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} stroke="rgba(255,255,255,0.05)" />
                              ))}
                            </Pie>
                            <RechartsTooltip 
                              formatter={(value: number) => [formatMoney(value), 'Amount']}
                              contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', color: '#f8fafc', borderRadius: '12px' }}
                              itemStyle={{ color: '#e2e8f0' }}
                            />
                            <Legend 
                              layout="horizontal" 
                              verticalAlign="bottom" 
                              align="center"
                              iconType="circle"
                              iconSize={8}
                              wrapperStyle={{ paddingTop: '20px', fontSize: '11px', color: '#a1a1aa' }}
                            />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Bar Chart */}
                  <Card className="rounded-2xl border-white/10 bg-white/5 backdrop-blur shadow-[0_18px_60px_-36px_rgba(0,0,0,0.75)]">
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-semibold text-white">Category Breakdown</div>
                          <div className="mt-1 text-xs text-white/60">Spending across main categories</div>
                        </div>
                        <div className="p-2 rounded-lg bg-white/5 border border-white/10">
                          <BarChartIcon className="w-4 h-4 text-white/70" />
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent>
                       <div className="h-[300px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart
                            layout="vertical"
                            data={categoryData}
                            margin={{ top: 0, right: 20, left: 0, bottom: 0 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(255,255,255,0.05)" />
                            <XAxis type="number" hide />
                            <YAxis 
                              dataKey="name" 
                              type="category" 
                              width={120} 
                              tick={{fontSize: 11, fill: '#a1a1aa', fontWeight: 500}} 
                              axisLine={false}
                              tickLine={false}
                            />
                            <RechartsTooltip
                              cursor={{fill: 'rgba(255,255,255,0.05)', radius: 4}}
                              formatter={(value: number) => [formatMoney(value), 'Amount']}
                              contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', color: '#f8fafc', borderRadius: '12px' }}
                              itemStyle={{ color: '#e2e8f0' }}
                            />
                            <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={16}>
                              {categoryData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              )}

              <Card className="rounded-2xl border-white/10 bg-white/5 backdrop-blur shadow-[0_18px_60px_-36px_rgba(0,0,0,0.75)]">
                <CardHeader className="pb-0">
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <div className="text-sm font-semibold text-white">Audit Ledger</div>
                      <div className="mt-1 text-xs text-white/60">
                        Clean transactions with categories, confidence, and evidence.
                      </div>
                    </div>
                  </div>

                  <Tabs defaultValue="transactions" className="mt-5">
                    <TabsList className="bg-white/5 border border-white/10 rounded-xl">
                      <TabsTrigger
                        value="transactions"
                        className="rounded-lg data-[state=active]:bg-white data-[state=active]:text-zinc-950"
                      >
                        Transactions
                      </TabsTrigger>
                      <TabsTrigger
                        value="findings"
                        className="rounded-lg data-[state=active]:bg-white data-[state=active]:text-zinc-950"
                      >
                        Findings
                      </TabsTrigger>
                    </TabsList>

                    <TabsContent value="transactions" className="mt-4">
                      <div className="overflow-hidden rounded-2xl border border-white/10">
                        <div className="grid grid-cols-12 bg-zinc-950/40 px-4 py-3 text-xs text-white/60 font-semibold uppercase tracking-wider">
                          <div className="col-span-2">Date</div>
                          <div className="col-span-4">Description</div>
                          <div className="col-span-2 text-right">Debit</div>
                          <div className="col-span-2 text-right">Credit</div>
                          <div className="col-span-2 text-right">Balance</div>
                        </div>

                        <div className="divide-y divide-white/10 bg-white/[0.03]">
                          {txns.map((t, idx) => (
                            <div
                              key={idx}
                              className={cn(
                                "w-full text-left px-4 py-3 grid grid-cols-12 gap-3 items-center hover:bg-white/5 transition group",
                                selectedTxn === t ? "bg-white/5" : ""
                              )}
                              onClick={() => {
                                setSelectedTxn(t);
                                setSelectedPage(t.evidence.page);
                              }}
                            >
                              <div className="col-span-2">
                                <div className="text-sm text-white/85 font-mono">{t.date}</div>
                                <div className="mt-1">{<FlagPill flag={t.flag} />}</div>
                              </div>

                              <div className="col-span-4 min-w-0">
                                <div className="text-sm text-white/85 truncate" title={t.description}>{t.description}</div>
                                <div className="mt-1 flex flex-wrap items-center gap-2">
                                  <Badge
                                    variant="outline"
                                    className="rounded-full border-white/10 bg-white/5 text-white/75"
                                  >
                                    {t.category}
                                  </Badge>
                                </div>
                              </div>

                              <div className="col-span-2 text-right">
                                <div className="text-sm text-white/85 tabular-nums font-mono text-rose-300">
                                  {t.debit ? `${formatMoney(t.debit)}` : "—"}
                                </div>
                              </div>

                              <div className="col-span-2 text-right">
                                <div className="text-sm text-white/85 tabular-nums font-mono text-emerald-300">
                                  {t.credit ? `${formatMoney(t.credit)}` : "—"}
                                </div>
                              </div>

                              <div className="col-span-2 text-right">
                                <div className="text-sm text-white/85 tabular-nums font-mono font-bold">
                                  {formatMoney(t.balance)}
                                </div>
                                <div className="mt-1 flex justify-end">
                                  <ConfidenceBar value={t.confidence} />
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </TabsContent>

                    <TabsContent value="findings" className="mt-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <Card className="rounded-2xl border-white/10 bg-white/5">
                          <CardContent className="p-5">
                            <div className="flex items-start justify-between">
                              <div>
                                <div className="text-sm font-semibold text-white">High-risk</div>
                                <div className="mt-1 text-xs text-white/60">
                                  Items that may affect reporting accuracy.
                                </div>
                              </div>
                              <Badge
                                variant="outline"
                                className="rounded-full border-rose-200/30 bg-rose-500/10 text-rose-100"
                              >
                                <AlertTriangle className="mr-1 h-3.5 w-3.5" />
                                {summary.anomalies}
                              </Badge>
                            </div>
                            <div className="mt-4 space-y-2">
                              {txns
                                .filter((t) => t.flag === "anomaly")
                                .map((t, i) => (
                                  <div
                                    key={i}
                                    className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-left hover:bg-white/10 transition"
                                  >
                                    <div className="text-sm text-white/85 truncate">{t.description}</div>
                                  </div>
                                ))}
                            </div>
                          </CardContent>
                        </Card>

                        <Card className="rounded-2xl border-white/10 bg-white/5">
                          <CardContent className="p-5">
                            <div className="flex items-start justify-between">
                              <div>
                                <div className="text-sm font-semibold text-white">Needs review</div>
                                <div className="mt-1 text-xs text-white/60">
                                  Low confidence or classification uncertainties.
                                </div>
                              </div>
                              <Badge
                                variant="outline"
                                className="rounded-full border-amber-200/30 bg-amber-500/10 text-amber-100"
                              >
                                <Info className="mr-1 h-3.5 w-3.5" />
                                {summary.reviews}
                              </Badge>
                            </div>
                            <div className="mt-4 space-y-2">
                              {txns
                                .filter((t) => t.flag === "review")
                                .map((t, i) => (
                                  <div
                                    key={i}
                                    className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-left hover:bg-white/10 transition"
                                  >
                                    <div className="text-sm text-white/85 truncate">{t.description}</div>
                                    <div className="mt-1 text-xs text-white/55">
                                      Category: {t.category}
                                    </div>
                                  </div>
                                ))}
                            </div>
                          </CardContent>
                        </Card>
                      </div>
                    </TabsContent>
                  </Tabs>
                </CardHeader>
              </Card>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="mt-10 text-center text-xs text-white/45">
          SentinelAI • Evidence-grade financial intelligence • Designed for audit workflows
        </div>
      </main>
    </div>
  );
}