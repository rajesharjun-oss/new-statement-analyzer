import React from "react";
import { Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, Bot, CalendarRange, Loader2, Repeat2, Users } from "lucide-react";
import { AnalysisInsights, AnalysisNarrative } from "../types";
import { Badge, Button, Card } from "./PrimitiveUI";

function money(value: number) {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

export function AnalysisInsightsPanel({
  insights,
  narrative,
  aiEnabled,
  isGeneratingNarrative,
  onGenerateNarrative
}: {
  insights: AnalysisInsights;
  narrative: AnalysisNarrative;
  aiEnabled: boolean;
  isGeneratingNarrative: boolean;
  onGenerateNarrative: () => void;
}) {
  const metrics = [
    { label: "Net cash flow", value: money(insights.netCashFlow), icon: Activity, tone: insights.netCashFlow >= 0 ? "text-[#3CDCAB]" : "text-[#FF5A78]" },
    { label: "Average monthly debit", value: money(insights.averageMonthlyDebit), icon: ArrowDownRight, tone: "text-[#FFB43C]" },
    { label: "Average monthly credit", value: money(insights.averageMonthlyCredit), icon: ArrowUpRight, tone: "text-[#3CDCAB]" },
    { label: "Top concentration", value: `${insights.topCounterpartyConcentrationPercent}%`, icon: Users, tone: "text-[#9B87FF]" }
  ];

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden rounded-[14px] bg-[#111318]/80">
        <div className="flex flex-col gap-3 border-b border-white/[0.06] p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-[#9B87FF]" />
              <h3 className="text-sm font-semibold text-white">Cash Flow &amp; Risk Insights</h3>
            </div>
            <p className="mt-1 text-xs text-zinc-500">Deterministic trends and review signals with transaction-level evidence.</p>
          </div>
          <Badge variant="outline"><CalendarRange className="mr-1 h-3 w-3" />{insights.periodStart || "N/A"} to {insights.periodEnd || "N/A"}</Badge>
        </div>

        <div className="grid grid-cols-2 border-b border-white/[0.06] lg:grid-cols-4">
          {metrics.map(({ label, value, icon: Icon, tone }) => (
            <div key={label} className="min-w-0 border-b border-r border-white/[0.06] p-4 last:border-r-0 lg:border-b-0">
              <div className="flex items-center justify-between gap-2">
                <div className="truncate text-[10px] font-semibold uppercase text-zinc-500">{label}</div>
                <Icon className={`h-4 w-4 ${tone}`} />
              </div>
              <div className="mt-2 truncate font-mono text-lg font-semibold text-white">{value}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 divide-y divide-white/[0.06] xl:grid-cols-2 xl:divide-x xl:divide-y-0">
          <div className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <h4 className="text-xs font-semibold uppercase text-zinc-400">Monthly movement</h4>
              <Badge variant="outline">{insights.activeMonths} months</Badge>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-xs">
                <thead className="text-left uppercase text-zinc-600">
                  <tr><th className="pb-2">Month</th><th className="pb-2 text-right">Debit</th><th className="pb-2 text-right">Credit</th><th className="pb-2 text-right">Net</th><th className="pb-2 text-right">Change</th></tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {insights.monthlyTrends.slice(-8).map(row => (
                    <tr key={row.month}>
                      <td className="py-2 font-mono text-zinc-300">{row.month}</td>
                      <td className="py-2 text-right font-mono text-zinc-400">{money(row.debitTotal)}</td>
                      <td className="py-2 text-right font-mono text-[#3CDCAB]">{money(row.creditTotal)}</td>
                      <td className={`py-2 text-right font-mono ${row.netMovement >= 0 ? "text-[#3CDCAB]" : "text-[#FF5A78]"}`}>{money(row.netMovement)}</td>
                      <td className="py-2 text-right font-mono text-zinc-500">{row.netChangePercent === null ? "-" : `${row.netChangePercent}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <h4 className="text-xs font-semibold uppercase text-zinc-400">Top counterparties</h4>
              <Users className="h-4 w-4 text-zinc-600" />
            </div>
            <div className="divide-y divide-white/[0.05]">
              {insights.topCounterparties.slice(0, 8).map(row => (
                <div key={`${row.direction}-${row.counterparty}`} className="flex items-center justify-between gap-4 py-2.5">
                  <div className="min-w-0">
                    <div className="truncate text-xs text-zinc-200" title={row.counterparty}>{row.counterparty}</div>
                    <div className="mt-1 text-[10px] text-zinc-600">{row.transactionCount} transaction(s) | {row.sharePercent}% of {row.direction.toLowerCase()} value</div>
                  </div>
                  <div className={`shrink-0 font-mono text-xs ${row.direction === "Credit" ? "text-[#3CDCAB]" : "text-[#FFB43C]"}`}>{money(row.totalAmount)}</div>
                </div>
              ))}
              {insights.topCounterparties.length === 0 && <div className="py-6 text-center text-xs text-zinc-600">No counterparty activity available.</div>}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 border-t border-white/[0.06] xl:grid-cols-2 xl:divide-x xl:divide-white/[0.06]">
          <div className="p-5">
            <div className="mb-3 flex items-center gap-2">
              <Repeat2 className="h-4 w-4 text-[#9B87FF]" />
              <h4 className="text-xs font-semibold uppercase text-zinc-400">Recurring activity</h4>
            </div>
            <div className="divide-y divide-white/[0.05]">
              {insights.recurringPatterns.slice(0, 6).map(row => (
                <div key={`${row.direction}-${row.counterparty}-${row.typicalAmount}`} className="flex items-center justify-between gap-4 py-2.5">
                  <div className="min-w-0">
                    <div className="truncate text-xs text-zinc-200">{row.counterparty}</div>
                    <div className="mt-1 text-[10px] text-zinc-600">{row.cadence} | {row.transactionCount} occurrences</div>
                  </div>
                  <div className="font-mono text-xs text-zinc-300">{money(row.typicalAmount)}</div>
                </div>
              ))}
              {insights.recurringPatterns.length === 0 && <div className="py-6 text-center text-xs text-zinc-600">No stable recurring patterns detected.</div>}
            </div>
          </div>

          <div className="p-5">
            <div className="mb-3 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-[#FFB43C]" />
              <h4 className="text-xs font-semibold uppercase text-zinc-400">Anomaly review</h4>
            </div>
            <div className="divide-y divide-white/[0.05]">
              {insights.anomalies.slice(0, 6).map(row => (
                <div key={`${row.type}-${row.transactionId}`} className="py-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="truncate text-xs text-zinc-200" title={row.description}>{row.description || "Missing description"}</div>
                    <Badge variant={row.severity === "High" ? "danger" : "warning"}>{row.type}</Badge>
                  </div>
                  <div className="mt-1 flex justify-between gap-3 text-[10px] text-zinc-600"><span>{row.transactionId} | {row.date}</span><span className="font-mono">{money(row.amount)}</span></div>
                </div>
              ))}
              {insights.anomalies.length === 0 && <div className="py-6 text-center text-xs text-zinc-600">No deterministic anomaly signals detected.</div>}
            </div>
          </div>
        </div>
      </Card>

      <Card className="rounded-[14px] bg-[#111318]/80 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white">Evidence-backed Narrative</h3>
            <p className="mt-1 text-xs text-zinc-500">{narrative.summary}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={narrative.generatedBy === "AI" ? "purple" : "success"}>{narrative.generatedBy === "AI" ? "AI with citations" : "Deterministic"}</Badge>
            <Button size="sm" variant="outline" onClick={onGenerateNarrative} disabled={!aiEnabled || isGeneratingNarrative} title={aiEnabled ? "Generate an AI narrative from verified metrics" : "Turn on AI fallback to enable this optional narrative"}>
              {isGeneratingNarrative ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Bot className="mr-2 h-4 w-4" />}
              {isGeneratingNarrative ? "Generating" : "AI narrative"}
            </Button>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
          {narrative.findings.map(finding => (
            <div key={finding.title} className="border-l border-white/10 pl-3">
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-xs font-semibold text-zinc-200">{finding.title}</div>
                <Badge variant={finding.severity === "Positive" ? "success" : finding.severity === "Review" ? "warning" : "outline"}>{finding.severity}</Badge>
              </div>
              <p className="mt-2 text-xs leading-5 text-zinc-500">{finding.body}</p>
              {finding.evidenceTransactionIds.length > 0 && <div className="mt-2 truncate font-mono text-[10px] text-zinc-700">Evidence: {finding.evidenceTransactionIds.slice(0, 5).join(", ")}</div>}
            </div>
          ))}
        </div>
        <div className="mt-4 border-t border-white/[0.06] pt-3 text-[10px] leading-5 text-zinc-600">{narrative.caveats.join(" ")}</div>
      </Card>
    </div>
  );
}
