import React, { useMemo, useState } from "react";
import { Download, FileCheck, Loader2, Play, Upload } from "lucide-react";
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
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-bold text-white tracking-tight">AI Analysis Workspace</h1>
          <p className="text-sm text-zinc-500 mt-1">Extract first, classify second, review uncertain rows, then export a complete workbook.</p>
        </div>
        <Badge variant={isBusy ? "warning" : "success"}>{isBusy ? "Processing" : "Ready"}</Badge>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {steps.map((label, idx) => (
          <button key={label} onClick={() => setStep(idx)} className={cn("px-3 py-2 rounded-[10px] border text-xs font-semibold text-left", step === idx ? "border-[#9B87FF]/40 bg-[#9B87FF]/15 text-[#C6B8FF]" : "border-white/10 bg-white/[0.02] text-zinc-500")}>
            Step {idx + 1}<div className="text-zinc-200 mt-1">{label}</div>
          </button>
        ))}
      </div>

      {error && <Card className="p-4 border-red-500/20 bg-red-500/10 text-red-200 text-sm">{error}</Card>}
      {isBusy && <Progress value={progress || 25} />}
      {status && <div className="text-xs text-zinc-500 font-mono">{status}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <Card className="lg:col-span-5 p-5 rounded-[12px]">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold text-white">Upload & Extract</h2>
              <p className="text-xs text-zinc-500 mt-1">PDF, Excel, CSV and supported images route through the backend extractor.</p>
            </div>
            <FileCheck className="w-5 h-5 text-[#9B87FF]" />
          </div>
          <label className="block border border-dashed border-white/10 rounded-[12px] p-6 text-center hover:bg-white/[0.02] cursor-pointer">
            <Upload className="w-7 h-7 mx-auto text-zinc-500 mb-3" />
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

        <Card className="lg:col-span-7 p-5 rounded-[12px]">
          <h2 className="text-sm font-semibold text-white mb-4">Choose Analysis</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {analysisTemplates.map(item => (
              <button key={item.id} onClick={() => chooseTemplate(item.id)} className={cn("text-left rounded-[10px] border p-3 transition-colors", templateId === item.id ? "border-[#9B87FF]/40 bg-[#9B87FF]/10" : "border-white/10 bg-white/[0.02] hover:bg-white/[0.04]")}>
                <div className="text-sm font-semibold text-white">{item.name}</div>
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

      <div className="flex flex-wrap gap-3">
        <Button variant="outline" onClick={() => setUseAI(v => !v)}>{useAI ? "AI fallback on" : "AI fallback off"}</Button>
        <Button variant="primary" onClick={runClassification} disabled={isBusy || !extractedResult?.transactions?.length}>
          {isBusy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
          Classify Transactions
        </Button>
        <Button variant="outline" onClick={handleExport} disabled={!classified.length}>
          <Download className="w-4 h-4 mr-2" /> Export Workbook
        </Button>
      </div>

      {classified.length > 0 && (
        <>
          <AnalysisSummaryCards transactions={classified} reconciliation={reconciliation} />
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            {categorySummary.map(row => (
              <Card key={row.category} className="p-4 rounded-[12px]">
                <div className="text-sm font-semibold text-white truncate">{row.category}</div>
                <div className="text-xs text-zinc-500 mt-2">{row.transactionCount} txns</div>
                <div className="text-lg font-mono text-[#3CDCAB] mt-2">{row.netMovement.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
              </Card>
            ))}
          </div>
          <TransactionPreviewTable transactions={classified} filter={filter} onFilterChange={setFilter} onManualEdit={manualEdit} />
        </>
      )}
    </div>
  );
}
