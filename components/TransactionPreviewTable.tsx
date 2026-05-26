import React from "react";
import { ClassifiedTransaction, ConfidenceLabel } from "../types";
import { Badge, Button } from "./PrimitiveUI";

const categories = ["Review Required", "FIRS", "SIRS", "Not Applicable", "Customer Payment", "Sales Income", "Supplier Payment", "Bank Charges", "Internal Transfer", "Tax/Statutory Payment", "Operating Income", "Unallocated/Review Required"];
const taxAuthorities = ["", "FIRS", "SIRS", "Not Applicable", "Review Required"];
const confidences: ConfidenceLabel[] = ["High", "Medium", "Low"];

function amount(n: number) {
  return n ? new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n) : "-";
}

export function TransactionPreviewTable({
  transactions,
  filter,
  onFilterChange,
  onManualEdit
}: {
  transactions: ClassifiedTransaction[];
  filter: "all" | "review" | "low";
  onFilterChange: (filter: "all" | "review" | "low") => void;
  onManualEdit: (id: string, patch: Partial<ClassifiedTransaction>) => void;
}) {
  const visible = transactions.filter(t => {
    if (filter === "review") return t.reviewRequired;
    if (filter === "low") return t.confidence === "Low";
    return true;
  });

  return (
    <div className="rounded-[12px] border border-white/[0.08] overflow-hidden bg-[#0E0F12]">
      <div className="px-5 py-4 border-b border-white/[0.06] flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white">Preview & Review</h3>
          <p className="text-xs text-zinc-500 mt-1">{visible.length} rows visible</p>
        </div>
        <div className="flex gap-2">
          {(["all", "review", "low"] as const).map(option => (
            <Button key={option} size="xs" variant={filter === option ? "primary" : "outline"} onClick={() => onFilterChange(option)}>
              {option === "all" ? "All" : option === "review" ? "Review" : "Low"}
            </Button>
          ))}
        </div>
      </div>
      <div className="overflow-auto max-h-[520px]">
        <table className="min-w-[1500px] w-full text-left text-xs">
          <thead className="sticky top-0 bg-[#111318] text-zinc-500 uppercase tracking-wider font-mono">
            <tr>
              {["Date", "Value Date", "Reference", "Description", "Debit", "Credit", "Balance", "Category", "Tax Authority", "Confidence", "Source", "Reason", "Review"].map(h => (
                <th key={h} className="px-3 py-3 font-semibold">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {visible.map(t => (
              <tr key={t.id} className="hover:bg-white/[0.02]">
                <td className="px-3 py-2 font-mono text-zinc-300">{t.transactionDate}</td>
                <td className="px-3 py-2 font-mono text-zinc-500">{t.valueDate || ""}</td>
                <td className="px-3 py-2 font-mono text-zinc-500 max-w-[140px] truncate">{t.reference}</td>
                <td className="px-3 py-2 text-zinc-200 max-w-[320px] truncate" title={t.description}>{t.description}</td>
                <td className="px-3 py-2 text-right font-mono">{amount(t.debit)}</td>
                <td className="px-3 py-2 text-right font-mono text-[#3CDCAB]">{amount(t.credit)}</td>
                <td className="px-3 py-2 text-right font-mono">{amount(t.balance)}</td>
                <td className="px-3 py-2">
                  <select className="w-44 h-8 bg-[#070707] border border-white/10 rounded-[8px] px-2 text-zinc-100" value={t.category} onChange={(e) => onManualEdit(t.id, { category: e.target.value })}>
                    <option value={t.category}>{t.category}</option>
                    {categories.filter(c => c !== t.category).map(c => <option key={c}>{c}</option>)}
                  </select>
                </td>
                <td className="px-3 py-2">
                  <select className="w-36 h-8 bg-[#070707] border border-white/10 rounded-[8px] px-2 text-zinc-100" value={t.taxAuthority || ""} onChange={(e) => onManualEdit(t.id, { taxAuthority: (e.target.value || null) as any })}>
                    {taxAuthorities.map(v => <option key={v} value={v}>{v || "None"}</option>)}
                  </select>
                </td>
                <td className="px-3 py-2">
                  <select className="w-28 h-8 bg-[#070707] border border-white/10 rounded-[8px] px-2 text-zinc-100" value={t.confidence} onChange={(e) => onManualEdit(t.id, { confidence: e.target.value as ConfidenceLabel })}>
                    {confidences.map(v => <option key={v}>{v}</option>)}
                  </select>
                </td>
                <td className="px-3 py-2"><Badge variant={t.decisionSource === "AI" ? "purple" : t.decisionSource === "MANUAL" ? "warning" : "outline"}>{t.decisionSource}</Badge></td>
                <td className="px-3 py-2 text-zinc-500 max-w-[260px] truncate" title={t.reason}>{t.reason}</td>
                <td className="px-3 py-2">
                  <input type="checkbox" checked={t.reviewRequired} onChange={(e) => onManualEdit(t.id, { reviewRequired: e.target.checked })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
