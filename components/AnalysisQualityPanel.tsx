import React from "react";
import { AlertTriangle, CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import { AnalysisQualityReport } from "../types";
import { Badge, Card } from "./PrimitiveUI";

function badgeVariant(status: AnalysisQualityReport["status"]): "success" | "warning" | "danger" {
  if (status === "Passed") return "success";
  if (status === "Failed") return "danger";
  return "warning";
}

export function AnalysisQualityPanel({ report }: { report: AnalysisQualityReport }) {
  const StatusIcon = report.status === "Passed" ? CheckCircle2 : report.status === "Failed" ? XCircle : AlertTriangle;
  const metrics = [
    { label: "Classification coverage", value: `${report.classificationCoveragePercent}%` },
    { label: "High confidence", value: `${report.highConfidencePercent}%` },
    { label: "Source evidence", value: `${report.sourceEvidencePercent}%` },
    { label: "Review queue", value: report.reviewCount },
    { label: "Possible duplicates", value: report.duplicateCount },
    { label: "Balance issues", value: report.balanceContinuityIssueCount }
  ];

  return (
    <Card className="overflow-hidden rounded-[14px] bg-[#111318]/80">
      <div className="flex flex-col gap-4 border-b border-white/[0.06] p-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border border-white/10 bg-black/20">
            <ShieldCheck className="h-5 w-5 text-[#9B87FF]" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-white">Analysis Quality Gate</h3>
              <Badge variant={badgeVariant(report.status)}>{report.status}</Badge>
            </div>
            <p className="mt-1 text-xs text-zinc-500">Deterministic checks for ledger integrity, classification coverage, and source traceability.</p>
          </div>
        </div>
        <div className="flex items-center gap-3 lg:text-right">
          <StatusIcon className={`h-5 w-5 ${report.status === "Passed" ? "text-[#3CDCAB]" : report.status === "Failed" ? "text-[#FF5A78]" : "text-[#FFB43C]"}`} />
          <div>
            <div className="font-mono text-2xl font-bold text-white">{report.score}/100</div>
            <div className="text-[10px] uppercase text-zinc-500">{report.grade}</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 border-b border-white/[0.06] md:grid-cols-3 lg:grid-cols-6">
        {metrics.map(metric => (
          <div key={metric.label} className="min-w-0 border-b border-r border-white/[0.06] p-4 last:border-r-0 md:border-b-0">
            <div className="truncate text-[10px] font-semibold uppercase text-zinc-500">{metric.label}</div>
            <div className="mt-2 font-mono text-lg font-semibold text-white">{metric.value}</div>
          </div>
        ))}
      </div>

      <div className="p-5">
        <div className="mb-3 text-[10px] font-semibold uppercase text-zinc-500">Findings</div>
        {report.issues.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-[#3CDCAB]">
            <CheckCircle2 className="h-4 w-4" />
            No integrity or review findings detected.
          </div>
        ) : (
          <div className="divide-y divide-white/[0.06]">
            {report.issues.slice(0, 6).map(issue => (
              <div key={issue.code} className="flex flex-col gap-2 py-3 first:pt-0 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={issue.severity === "Critical" ? "danger" : issue.severity === "Warning" ? "warning" : "outline"}>{issue.severity}</Badge>
                    <span className="font-mono text-xs text-zinc-400">{issue.code}</span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-zinc-400">{issue.message}</p>
                </div>
                <div className="shrink-0 font-mono text-xs text-zinc-300">{issue.count} row{issue.count === 1 ? "" : "s"}</div>
              </div>
            ))}
            {report.issues.length > 6 && <div className="pt-3 text-xs text-zinc-500">{report.issues.length - 6} additional finding types are included in the export.</div>}
          </div>
        )}
      </div>
    </Card>
  );
}
