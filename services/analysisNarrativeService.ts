import { AnalysisInsights, AnalysisNarrative, AnalysisQualityReport } from "../types";

export async function generateAINarrative({
  insights,
  quality,
  deterministicNarrative
}: {
  insights: AnalysisInsights;
  quality: AnalysisQualityReport;
  deterministicNarrative: AnalysisNarrative;
}): Promise<AnalysisNarrative> {
  const compactInsights = {
    periodStart: insights.periodStart,
    periodEnd: insights.periodEnd,
    activeMonths: insights.activeMonths,
    netCashFlow: insights.netCashFlow,
    averageMonthlyDebit: insights.averageMonthlyDebit,
    averageMonthlyCredit: insights.averageMonthlyCredit,
    largestDebit: insights.largestDebit,
    largestCredit: insights.largestCredit,
    topCounterpartyConcentrationPercent: insights.topCounterpartyConcentrationPercent,
    monthlyTrends: insights.monthlyTrends.slice(-12),
    topCounterparties: insights.topCounterparties.slice(0, 6).map(row => ({ ...row, transactionIds: row.transactionIds.slice(0, 5) })),
    recurringPatterns: insights.recurringPatterns.slice(0, 5).map(row => ({ ...row, transactionIds: row.transactionIds.slice(0, 5) })),
    anomalies: insights.anomalies.slice(0, 12)
  };
  const compactQuality = {
    score: quality.score,
    grade: quality.grade,
    status: quality.status,
    classificationCoveragePercent: quality.classificationCoveragePercent,
    highConfidencePercent: quality.highConfidencePercent,
    reviewCount: quality.reviewCount,
    issues: quality.issues.map(issue => ({ ...issue, transactionIds: issue.transactionIds.slice(0, 5) }))
  };
  const allowedEvidenceIds = Array.from(new Set([
    ...deterministicNarrative.findings.flatMap(finding => finding.evidenceTransactionIds),
    ...compactInsights.anomalies.map(item => item.transactionId),
    ...compactInsights.topCounterparties.flatMap(item => item.transactionIds),
    ...compactInsights.recurringPatterns.flatMap(item => item.transactionIds)
  ])).slice(0, 250);

  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 45_000);
  try {
    const response = await fetch(`/analysis-narrative?t=${Date.now()}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        insights: compactInsights,
        quality: compactQuality,
        deterministicNarrative,
        allowedEvidenceIds
      }),
      signal: controller.signal
    });
    if (!response.ok) throw new Error(`AI narrative unavailable (${response.status})`);
    const data = await response.json();
    if (data.generatedBy !== "AI" || !Array.isArray(data.findings) || !Array.isArray(data.caveats)) {
      throw new Error("AI narrative returned an invalid response");
    }
    return {
      generatedBy: "AI",
      summary: String(data.summary || deterministicNarrative.summary),
      findings: data.findings.slice(0, 8).map((finding: any) => ({
        title: String(finding.title || "Analysis finding"),
        body: String(finding.body || ""),
        severity: ["Positive", "Neutral", "Review"].includes(finding.severity) ? finding.severity : "Neutral",
        evidenceTransactionIds: Array.isArray(finding.evidenceTransactionIds)
          ? finding.evidenceTransactionIds.filter((id: unknown) => allowedEvidenceIds.includes(String(id))).map(String)
          : []
      })),
      caveats: data.caveats.slice(0, 8).map(String)
    };
  } finally {
    globalThis.clearTimeout(timeout);
  }
}
