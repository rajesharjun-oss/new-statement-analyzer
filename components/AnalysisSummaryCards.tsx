import React from "react";
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
    ["Transactions", counts.total],
    ["Total Debit", money(reconciliation.totalDebit)],
    ["Total Credit", money(reconciliation.totalCredit)],
    ["Opening", money(reconciliation.openingBalance)],
    ["Closing", money(reconciliation.actualClosingBalance)],
    ["Rule", counts.rule],
    ["AI", counts.ai],
    ["Manual", counts.manual],
    ["Review", counts.review]
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      {cards.map(([label, value]) => (
        <Card key={String(label)} className="p-4 rounded-[12px]">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</div>
          <div className="mt-2 text-lg font-bold text-white font-mono">{value}</div>
        </Card>
      ))}
      <Card className="p-4 rounded-[12px]">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">Reconciliation</div>
        <div className="mt-2">
          <Badge variant={reconciliation.status === "Passed" ? "success" : reconciliation.status === "Failed" ? "danger" : "warning"}>
            {reconciliation.status}
          </Badge>
        </div>
      </Card>
    </div>
  );
}
