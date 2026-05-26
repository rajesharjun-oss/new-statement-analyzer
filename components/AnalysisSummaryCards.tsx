import React from "react";
import { AlertTriangle, Bot, CheckCircle2, ClipboardCheck, FileSpreadsheet, Pencil, Scale, ShieldCheck } from "lucide-react";
import { Badge, Card } from "./PrimitiveUI";
import { ClassifiedTransaction, ReconciliationCheck } from "../types";

function money(value: number | null | undefined) {
  if (value === null || value === undefined) return "N/A";
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

export function AnalysisSummaryCards({
  transactions,
  reconciliation
}: {
  transactions: ClassifiedTransaction[];
  reconciliation: ReconciliationCheck;
}) {
  const counts = transactions.reduce(
    (acc, t) => {
      acc.total += 1;
      if (t.decisionSource === "RULE") acc.rule += 1;
      if (t.decisionSource === "AI") acc.ai += 1;
      if (t.decisionSource === "MANUAL") acc.manual += 1;
      if (t.reviewRequired || t.confidence === "Low") acc.review += 1;
      return acc;
    },
    { total: 0, rule: 0, ai: 0, manual: 0, review: 0 }
  );

  const cards = [
    { label: "Transactions", value: counts.total, icon: FileSpreadsheet, tone: "text-[#9B87FF]" },
    { label: "Total Debit", value: money(reconciliation.totalDebit), icon: Scale, tone: "text-[#FFB43C]" },
    { label: "Total Credit", value: money(reconciliation.totalCredit), icon: Scale, tone: "text-[#3CDCAB]" },
    { label: "Opening", value: money(reconciliation.openingBalance), icon: ClipboardCheck, tone: "text-zinc-300" },
    { label: "Closing", value: money(reconciliation.actualClosingBalance), icon: ClipboardCheck, tone: "text-zinc-300" },
    { label: "Rule Classified", value: counts.rule, icon: ShieldCheck, tone: "text-[#3CDCAB]" },
    { label: "AI Classified", value: counts.ai, icon: Bot, tone: "text-[#9B87FF]" },
    { label: "Manual Edits", value: counts.manual, icon: Pencil, tone: "text-[#FFB43C]" },
    { label: "Review Queue", value: counts.review, icon: AlertTriangle, tone: "text-[#FF5A78]" }
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      {cards.map(({ label, value, icon: Icon, tone }) => (
        <Card key={label} className="p-4 rounded-[12px] bg-[#111318]/80">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</div>
            <Icon className={`w-4 h-4 ${tone}`} />
          </div>
          <div className="mt-3 text-lg font-bold text-white font-mono truncate">{value}</div>
        </Card>
      ))}
      <Card className="p-4 rounded-[12px] bg-[#111318]/80">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">Reconciliation</div>
          <CheckCircle2 className="w-4 h-4 text-[#3CDCAB]" />
        </div>
        <div className="mt-3">
          <Badge variant={reconciliation.status === "Passed" ? "success" : reconciliation.status === "Failed" ? "danger" : "warning"}>
            {reconciliation.status}
          </Badge>
        </div>
      </Card>
    </div>
  );
}
