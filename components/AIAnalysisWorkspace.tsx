import React, { useMemo, useState } from "react";
import { BarChart3, CheckCircle2, Download, FileCheck, FileSpreadsheet, Loader2, Play, ShieldCheck, Sparkles, Upload } from "lucide-react";
import { AnalysisTemplate, ClassifiedTransaction } from "../types";
import { analyzeDocument } from "../services/analysisService";
import { analysisTemplates, cloneTemplate } from "../services/analysisTemplates";
import { calculateCategorySummary, calculateReconciliation } from "../services/analysisRules";
import { classifyTransactions } from "../services/classifyTransactions";
import { exportAnalysisWorkbook } from "../services/analysisExportService";
import { AnalysisSummaryCards } from "./AnalysisSummaryCards";
import { RulesBuilder } from "./RulesBuilder";
import { TransactionPreviewTable } from "./TransactionPreviewTable";
import { Badge, Button, Card, Progress, cn } from "./PrimitiveUI";

const savedKey = "ledger_ai_analysis_templates";

function safeName(value: string) {
  return (value || "AI Analysis").replace(/[^a-z0-9]+/gi, "_").replace(/_+/g, "_");
}

export function AIAnalysisWorkspace({ selectedBank }: { selectedBank: string }) {
  const [step, setStep] = useState(0);
  const [fileName, setFileName] = useState("");
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [extractedResult, setExtractedResult] = useState<any>(null);
  const [classified, setClassified] = useState<ClassifiedTransaction[]>([]);
  const [templateId, setTemplateId] = useState("firs-sirs-na");
  const [template, setTemplate] = useState<AnalysisTemplate>(() => cloneTemplate(analysisTemplates[0]));
  const [customInstructions, setCustomInstructions] = useState(analysisTemplates[0].aiInstructions);
  const [savedTemplates, setSavedTemplates] = useState<AnalysisTemplate[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(savedKey) || "[]");
    } catch {
      return [];
    }
  });
  const [useAI, setUseAI] = useState(true);
  const [filter, setFilter] = useState<"all" | "review" | "low">("all");

  const reconciliation = useMemo(() => calculateReconciliation(
    classified,
    extractedResult?.statement_summary?.opening_balance,
    extractedResult?.statement_summary?.closing_balance
  ), [classified, extractedResult]);

  const categorySummary = useMemo(() => calculateCategorySummary(classified).slice(0, 8), [classified]);
  const reviewCount = classified.filter(t => t.reviewRequired || t.confidence === "Low").length;
  const outputFileName = `${safeName(extractedResult?.organizationName || "Statement")}_${safeName(template.name)}.xlsx`;

  const chooseTemplate = (id: string) => {
    setTemplateId(id);
    const next = cloneTemplate(analysisTemplates.find(t => t.id === id) || analysisTemplates[0]);
    setTemplate(next);
    setCustomInstructions(next.aiInstructions);
    setStep(Math.max(step, 1));
  };

  const loadSavedTemplates = (): AnalysisTemplate[] => {
    try {
      return JSON.parse(localStorage.getItem(savedKey) || "[]");
    } catch {
      return [];
    }
  };

  const saveTemplate = () => {
    const saved = loadSavedTemplates().filter(t => t.id !== template.id);
    const nextSaved = [...saved, { ...template, aiInstructions: customInstructions }];
    localStorage.setItem(savedKey, JSON.stringify(nextSaved));
    setSavedTemplates(nextSaved);
    setStatus("Template saved locally");
  };

  const handleExtract = async (file: File) => {
    setIsBusy(true);
    setError(null);
    setStatus("Uploading statement");
    setProgress(8);
    setFileName(file.name);
    setClassified([]);
    try {
      const result = await analyzeDocument(file, selectedBank, (msg, pct) => {
        setStatus(msg);
        setProgress(pct);
      });
      setExtractedResult(result);
      setProgress(100);
      setStatus(`${result.transactions.length} transactions extracted`);
      setStep(1);
    } catch (e: any) {
      setError(e.message || "Extraction failed");
    } finally {
      setIsBusy(false);
    }
  };

  const runClassification = async () => {
    if (!extractedResult?.transactions?.length) {
      setError("Extract transactions before classification.");
      return;
    }
    setIsBusy(true);
    setError(null);
    try {
      const rows = await classifyTransactions({
        transactions: extractedResult.transactions,
        template,
        customInstructions,
        sourceFileName: fileName,
        useAI,
        onProgress: setStatus
      });
      setClassified(rows);
      setStatus(`${rows.length} rows classified`);
      setStep(3);
    } catch (e: any) {
      setError(e.message || "Classification failed. Extracted rows are still available.");
    } finally {
      setIsBusy(false);
    }
  };

  const manualEdit = (id: string, patch: Partial<ClassifiedTransaction>) => {
    setClassified(rows => rows.map(row => row.id === id ? {
      ...row,
      ...patch,
      decisionSource: "MANUAL",
      reason: patch.reason || row.reason || "Manual review update."
    } : row));
  };

  const handleExport = () => {
    if (!classified.length) {
      setError("Classify or preview transactions before export.");
      return;
    }
    exportAnalysisWorkbook({
      transactions: classified,
      template,
      customInstructions,
      openingBalance: extractedResult?.statement_summary?.opening_balance,
      closingBalance: extractedResult?.statement_summary?.closing_balance,
      fileName: `${safeName(extractedResult?.organizationName || "Statement")}_${safeName(template.name)}.xlsx`
    });
  };

  const steps = ["Upload & Extract", "Choose Analysis", "Rules Builder", "Preview & Review", "Export"];

  return (
    <div className="animate-enter space-y-6">
      <div className="rounded-[18px] border border-white/[0.08] bg-[linear-gradient(135deg,rgba(155,135,255,0.12),rgba(60,220,171,0.05)_45%,rgba(255,255,255,0.02))] p-6 shadow-[0_24px_70px_rgba(0,0,0,0.5)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 mb-3">
              <Badge variant="purple" className="font-mono">Audit Mode</Badge>
              <Badge variant={isBusy ? "warning" : "success"}>{isBusy ? "Processing" : "Ready"}</Badge>
              {extractedResult?.backend_version && <Badge variant="outline">API {extractedResult.backend_version}</Badge>}
            </div>
            <h1 className="text-[30px] font-bold text-white tracking-tight">AI Analysis Workspace</h1>
            <p className="text-sm text-zinc-400 mt-2">Extract clean transaction rows, apply deterministic audit rules, review exceptions, and export a professional workbook.</p>
          </div>
          <div className="grid grid-cols-3 gap-2 min-w-[260px]">
            <div className="rounded-[12px] border border-white/10 bg-black/20 p-3">
              <div className="text-[10px] uppercase text-zinc-500">Extracted</div>
              <div className="mt-1 font-mono text-lg text-white">{extractedResult?.transactions?.length || 0}</div>
            </div>
            <div className="rounded-[12px] border border-white/10 bg-black/20 p-3">
              <div className="text-[10px] uppercase text-zinc-500">Classified</div>
              <div className="mt-1 font-mono text-lg text-white">{classified.length}</div>
            </div>
            <div className="rounded-[12px] border border-white/10 bg-black/20 p-3">
              <div className="text-[10px] uppercase text-zinc-500">Review</div>
              <div className="mt-1 font-mono text-lg text-[#FF5A78]">{reviewCount}</div>
            </div>
          </div>
        </div>
      </div>

      {/* <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-bold text-white tracking-tight">AI Analysis Workspace</h1>
          <p className="text-sm text-zinc-500 mt-1">Extract first, classify second, review uncertain rows, then export a complete workbook.</p>
        </div>
        <Badge variant={isBusy ? "warning" : "success"}>{isBusy ? "Processing" : "Ready"}</Badge>
      </div> */}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 rounded-[14px] border border-white/[0.06] bg-[#0E0F12] p-2">
        {steps.map((label, idx) => (
          <button key={label} onClick={() => setStep(idx)} className={cn("px-3 py-3 rounded-[10px] border text-xs font-semibold text-left transition-colors", step === idx ? "border-[#9B87FF]/40 bg-[#9B87FF]/15 text-[#C6B8FF]" : "border-transparent bg-transparent text-zinc-500 hover:bg-white/[0.03]")}>
            <div className="flex items-center justify-between">
              <span>Step {idx + 1}</span>
              {(idx < step || (idx === 0 && extractedResult) || (idx === 3 && classified.length)) && <CheckCircle2 className="w-3.5 h-3.5 text-[#3CDCAB]" />}
            </div>
            <div className="text-zinc-200 mt-1">{label}</div>
          </button>
        ))}
      </div>

      {error && <Card className="p-4 border-red-500/20 bg-red-500/10 text-red-200 text-sm">{error}</Card>}
      {isBusy && <Progress value={progress || 25} />}
      {status && <div className="text-xs text-zinc-500 font-mono">{status}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <Card className="lg:col-span-5 p-5 rounded-[14px] bg-[#111318]/80">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold text-white">Upload & Extract</h2>
              <p className="text-xs text-zinc-500 mt-1">PDF, Excel, CSV and supported images route through the backend extractor.</p>
            </div>
            <FileCheck className="w-5 h-5 text-[#9B87FF]" />
          </div>
          <label className="block border border-dashed border-[#9B87FF]/25 rounded-[14px] p-6 text-center hover:bg-[#9B87FF]/[0.04] cursor-pointer transition-colors">
            <div className="w-12 h-12 rounded-full bg-[#9B87FF]/10 border border-[#9B87FF]/20 flex items-center justify-center mx-auto mb-3">
              <Upload className="w-6 h-6 text-[#C6B8FF]" />
            </div>
            <div className="text-sm text-white font-semibold">{fileName || "Select statement"}</div>
            <div className="text-xs text-zinc-500 mt-1">PDF, Excel, CSV, JPG, PNG</div>
            <input type="file" className="hidden" accept=".pdf,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.webp" onChange={(e) => e.target.files?.[0] && handleExtract(e.target.files[0])} />
          </label>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-[10px] bg-white/[0.03] p-3">
              <div className="text-[10px] uppercase text-zinc-500">Extracted</div>
              <div className="text-lg font-bold text-white font-mono">{extractedResult?.transactions?.length || 0}</div>
            </div>
            <div className="rounded-[10px] bg-white/[0.03] p-3">
              <div className="text-[10px] uppercase text-zinc-500">Bank</div>
              <div className="text-sm font-semibold text-white truncate">{extractedResult?.bankName || selectedBank}</div>
            </div>
          </div>
        </Card>

        <Card className="lg:col-span-7 p-5 rounded-[14px] bg-[#111318]/80">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-white">Choose Analysis</h2>
            <Badge variant="purple">{template.scope}</Badge>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {analysisTemplates.map(item => (
              <button key={item.id} onClick={() => chooseTemplate(item.id)} className={cn("text-left rounded-[12px] border p-3 transition-colors min-h-[104px]", templateId === item.id ? "border-[#9B87FF]/50 bg-[#9B87FF]/10 shadow-[0_0_0_1px_rgba(155,135,255,0.15)]" : "border-white/10 bg-white/[0.02] hover:bg-white/[0.04]")}>
                <div className="flex items-start justify-between gap-2">
                  <div className="text-sm font-semibold text-white">{item.name}</div>
                  {templateId === item.id && <Sparkles className="w-4 h-4 text-[#9B87FF]" />}
                </div>
                <p className="text-xs text-zinc-500 mt-1 line-clamp-2">{item.description}</p>
                <Badge variant="outline" className="mt-2">{item.scope}</Badge>
              </button>
            ))}
          </div>
          {savedTemplates.length > 0 && (
            <div className="mt-5 pt-5 border-t border-white/[0.06]">
              <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-3">Saved Templates</div>
              <div className="flex flex-wrap gap-2">
                {savedTemplates.map(item => (
                  <Button key={item.id} size="xs" variant="outline" onClick={() => {
                    setTemplateId(item.id);
                    setTemplate(cloneTemplate(item));
                    setCustomInstructions(item.aiInstructions);
                  }}>
                    {item.name}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      <RulesBuilder
        template={template}
        customInstructions={customInstructions}
        onTemplateChange={setTemplate}
        onInstructionsChange={setCustomInstructions}
        onSaveTemplate={saveTemplate}
        onResetTemplate={() => chooseTemplate(templateId)}
      />

      <Card className="p-5 rounded-[14px] bg-[#111318]/80">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
          <div className="lg:col-span-5">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-[#3CDCAB]" />
              <h3 className="text-sm font-semibold text-white">Classification Controls</h3>
            </div>
            <p className="text-xs text-zinc-500 mt-1">Rules run first. AI is only used for unclear rows when provider keys are configured.</p>
          </div>
          <div className="lg:col-span-3 flex flex-wrap gap-2">
            <Button variant={useAI ? "primary" : "outline"} onClick={() => setUseAI(v => !v)}>{useAI ? "AI fallback on" : "AI fallback off"}</Button>
            <Button variant="primary" onClick={runClassification} disabled={isBusy || !extractedResult?.transactions?.length}>
              {isBusy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
              Classify
            </Button>
          </div>
          <div className="lg:col-span-4 rounded-[12px] border border-white/[0.08] bg-black/20 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <FileSpreadsheet className="w-4 h-4 text-[#9B87FF]" />
                  <span className="text-sm font-semibold text-white">Professional Export</span>
                </div>
                <p className="text-xs text-zinc-500 mt-1 truncate">{outputFileName}</p>
              </div>
              <Button variant="outline" onClick={handleExport} disabled={!classified.length}>
                <Download className="w-4 h-4 mr-2" /> Export
              </Button>
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-5 rounded-[14px] border-[#9B87FF]/20 bg-[linear-gradient(135deg,rgba(155,135,255,0.10),rgba(17,19,24,0.92))]">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-[12px] bg-[#9B87FF]/15 border border-[#9B87FF]/25 flex items-center justify-center">
              <Download className="w-5 h-5 text-[#C6B8FF]" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold text-white">Export Audit Workbook</h3>
                <Badge variant={classified.length ? "success" : "outline"}>{classified.length ? "Ready" : "Classify first"}</Badge>
              </div>
              <p className="text-sm text-zinc-400 mt-1">
                Creates Extracted Transactions, Classified Transactions, Category Summary, Monthly Summary, Review Required, Reconciliation Check, and Rules Used sheets.
              </p>
              <p className="text-xs text-zinc-500 mt-2 font-mono">{outputFileName}</p>
            </div>
          </div>
          <Button variant="primary" className="lg:min-w-[190px]" onClick={handleExport} disabled={!classified.length}>
            <FileSpreadsheet className="w-4 h-4 mr-2" />
            Export Excel
          </Button>
        </div>
      </Card>

      {classified.length > 0 && (
        <>
          <AnalysisSummaryCards transactions={classified} reconciliation={reconciliation} />
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-[#9B87FF]" />
            <h3 className="text-sm font-semibold text-white">Category Movement</h3>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            {categorySummary.map(row => (
              <Card key={row.category} className="p-4 rounded-[12px] bg-[#111318]/80">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-white truncate">{row.category}</div>
                  <Badge variant="outline">{row.transactionCount}</Badge>
                </div>
                <div className="text-xs text-zinc-500 mt-3">Net movement</div>
                <div className={`text-lg font-mono mt-1 ${row.netMovement >= 0 ? "text-[#3CDCAB]" : "text-[#FFB43C]"}`}>{row.netMovement.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
              </Card>
            ))}
          </div>
          <TransactionPreviewTable transactions={classified} filter={filter} onFilterChange={setFilter} onManualEdit={manualEdit} />
        </>
      )}
    </div>
  );
}
