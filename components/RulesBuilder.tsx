import React from "react";
import { Plus, Sparkles, Trash2 } from "lucide-react";
import { AnalysisCategoryRule, AnalysisTemplate } from "../types";
import { Button, Card, Input } from "./PrimitiveUI";
import { parseKeywordInput } from "../services/analysisRules";

const blankRule = (): AnalysisCategoryRule => ({
  id: `cat-${Date.now()}`,
  name: "New Category",
  outputLabel: "New Category",
  description: "",
  appliesTo: "both",
  includeKeywords: [],
  excludeKeywords: [],
  priority: 10
});

const starterRules = (): AnalysisCategoryRule[] => [
  {
    id: `cat-income-${Date.now()}`,
    name: "Custom Income",
    outputLabel: "Custom Income",
    description: "Credits that match your income keywords.",
    appliesTo: "credit",
    includeKeywords: ["income", "payment", "receipt"],
    excludeKeywords: ["loan", "reversal"],
    priority: 80
  },
  {
    id: `cat-expense-${Date.now() + 1}`,
    name: "Custom Expense",
    outputLabel: "Custom Expense",
    description: "Debits that match your expense keywords.",
    appliesTo: "debit",
    includeKeywords: ["purchase", "payment", "supplier"],
    excludeKeywords: ["transfer charge", "commission", "vat"],
    priority: 70
  },
  {
    id: `cat-transfer-${Date.now() + 2}`,
    name: "Internal Transfer",
    outputLabel: "Internal Transfer",
    description: "Own-account transfers and treasury movements.",
    appliesTo: "both",
    includeKeywords: ["own account", "internal transfer", "transfer between"],
    excludeKeywords: [],
    priority: 90
  },
  {
    id: `cat-bank-charges-${Date.now() + 3}`,
    name: "Bank Charges",
    outputLabel: "Bank Charges",
    description: "Bank fees, charges, VAT, commissions, and levies.",
    appliesTo: "debit",
    includeKeywords: ["charge", "commission", "vat", "sms", "levy", "stamp duty"],
    excludeKeywords: [],
    priority: 100
  }
];

export function RulesBuilder({
  template,
  customInstructions,
  onTemplateChange,
  onInstructionsChange,
  onSaveTemplate,
  onResetTemplate
}: {
  template: AnalysisTemplate;
  customInstructions: string;
  onTemplateChange: (template: AnalysisTemplate) => void;
  onInstructionsChange: (value: string) => void;
  onSaveTemplate: () => void;
  onResetTemplate: () => void;
}) {
  const isCustomTemplate = template.id === "custom" || template.id.startsWith("custom-");

  const updateRule = (idx: number, patch: Partial<AnalysisCategoryRule>) => {
    const categories = template.categories.map((rule, i) => i === idx ? { ...rule, ...patch } : rule);
    onTemplateChange({ ...template, categories });
  };

  return (
    <div className="space-y-4">
      <Card className="p-5 rounded-[12px]">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h3 className="text-sm font-semibold text-white">Rules Builder</h3>
            <p className="text-xs text-zinc-500 mt-1">Deterministic rules run first. Unclear rows can then go to AI using the same template.</p>
          </div>
          <div className="flex gap-2">
            <Button size="xs" variant="outline" onClick={onResetTemplate}>Reset</Button>
            <Button size="xs" variant="primary" onClick={onSaveTemplate}>Save Template</Button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 mb-3">
          <label className="lg:col-span-3">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-zinc-500 mb-1">Analysis Name</span>
            <Input
              value={template.name}
              onChange={(e) => onTemplateChange({ ...template, name: e.target.value })}
              disabled={!isCustomTemplate}
            />
          </label>
          <label className="lg:col-span-4">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-zinc-500 mb-1">Description</span>
            <Input
              value={template.description}
              onChange={(e) => onTemplateChange({ ...template, description: e.target.value })}
              disabled={!isCustomTemplate}
            />
          </label>
          <label className="lg:col-span-2">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-zinc-500 mb-1">Scope</span>
            <select
              className="h-10 w-full rounded-[10px] border border-white/10 bg-[#070707] px-3 text-sm text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
              value={template.scope}
              onChange={(e) => onTemplateChange({ ...template, scope: e.target.value as any })}
              disabled={!isCustomTemplate}
            >
              <option value="both">Both</option>
              <option value="debit">Debit only</option>
              <option value="credit">Credit only</option>
            </select>
          </label>
          <label className="lg:col-span-3 flex items-center gap-3 rounded-[10px] border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              checked={template.markUncertainAsReview}
              onChange={(e) => onTemplateChange({ ...template, markUncertainAsReview: e.target.checked })}
            />
            <span>Mark unclear rows for review</span>
          </label>
        </div>

        <textarea
          className="w-full min-h-[92px] rounded-[10px] border border-white/10 bg-[#070707] px-3 py-2 text-sm text-zinc-100 resize-y focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#9B87FF]"
          value={customInstructions}
          onChange={(e) => onInstructionsChange(e.target.value)}
          placeholder="Write analysis instructions for ambiguous rows..."
        />
        {template.id === "firs-sirs-na" && (
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="flex flex-wrap items-center gap-3 rounded-[10px] border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-zinc-300">
              <span>Treat salary/payroll payments as:</span>
              <select
                className="h-9 rounded-[9px] border border-white/10 bg-[#070707] px-3 text-sm text-zinc-100"
                value={template.salaryTreatment || (template.treatSalaryAsSirs ? "sirs" : "review")}
                onChange={(e) => onTemplateChange({
                  ...template,
                  salaryTreatment: e.target.value as any,
                  treatSalaryAsSirs: e.target.value === "sirs"
                })}
              >
                <option value="review">Review Required</option>
                <option value="sirs">SIRS</option>
                <option value="not_applicable">Not Applicable</option>
              </select>
            </label>
            <label className="flex flex-wrap items-center gap-3 rounded-[10px] border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-zinc-300">
              <span>Treat unregistered business/trade names as:</span>
              <select
                className="h-9 rounded-[9px] border border-white/10 bg-[#070707] px-3 text-sm text-zinc-100"
                value={template.tradeNameTreatment || "review"}
                onChange={(e) => onTemplateChange({ ...template, tradeNameTreatment: e.target.value as any })}
              >
                <option value="review">Review Required</option>
                <option value="sirs">SIRS</option>
                <option value="firs">FIRS</option>
              </select>
            </label>
          </div>
        )}
      </Card>

      <Card className="overflow-hidden rounded-[12px]">
        <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between">
          <div>
            <span className="text-sm font-semibold text-white">Category Rules</span>
            <p className="text-xs text-zinc-500 mt-1">Output labels become export categories and manual review options.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {isCustomTemplate && template.categories.length === 0 && (
              <Button size="xs" variant="outline" onClick={() => onTemplateChange({ ...template, categories: starterRules() })}>
                <Sparkles className="w-3.5 h-3.5 mr-1" /> Seed
              </Button>
            )}
            <Button size="xs" variant="outline" onClick={() => onTemplateChange({ ...template, categories: [...template.categories, blankRule()] })}>
              <Plus className="w-3.5 h-3.5 mr-1" /> Add
            </Button>
          </div>
        </div>
        <div className="divide-y divide-white/[0.06]">
          {template.categories.map((rule, idx) => (
            <div key={rule.id} className="p-4 grid grid-cols-1 lg:grid-cols-12 gap-3">
              <Input className="lg:col-span-2" value={rule.name} onChange={(e) => updateRule(idx, { name: e.target.value })} />
              <Input className="lg:col-span-2" value={rule.outputLabel} onChange={(e) => updateRule(idx, { outputLabel: e.target.value })} />
              <select
                className="lg:col-span-1 h-10 rounded-[10px] border border-white/10 bg-[#070707] px-2 text-sm text-zinc-100"
                value={rule.appliesTo}
                onChange={(e) => updateRule(idx, { appliesTo: e.target.value as any })}
              >
                <option value="both">Both</option>
                <option value="debit">Debit</option>
                <option value="credit">Credit</option>
              </select>
              <Input className="lg:col-span-2" placeholder="Include keywords" value={rule.includeKeywords.join(", ")} onChange={(e) => updateRule(idx, { includeKeywords: parseKeywordInput(e.target.value) })} />
              <Input className="lg:col-span-2" placeholder="Exclude keywords" value={rule.excludeKeywords.join(", ")} onChange={(e) => updateRule(idx, { excludeKeywords: parseKeywordInput(e.target.value) })} />
              <Input className="lg:col-span-1" type="number" value={rule.priority} onChange={(e) => updateRule(idx, { priority: Number(e.target.value) })} />
              <Input className="lg:col-span-1" placeholder="Description" value={rule.description} onChange={(e) => updateRule(idx, { description: e.target.value })} />
              <Button
                size="xs"
                variant="danger"
                className="lg:col-span-1"
                onClick={() => onTemplateChange({ ...template, categories: template.categories.filter((_, i) => i !== idx) })}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
          {template.categories.length === 0 && (
            <div className="p-8 text-center text-sm text-zinc-500">No category rules yet.</div>
          )}
        </div>
      </Card>
    </div>
  );
}
