type RecordValue = Record<string, unknown>;

function record(value: unknown): RecordValue | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : null;
}

// Legacy reports used strings; newer reports include structured repair instructions.
function text(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(text).filter(Boolean).join("；");
  const object = record(value);
  return object ? Object.values(object).map(text).filter(Boolean).join("；") : "";
}

const priorities: Record<string, string> = { high: "优先处理", medium: "建议处理", low: "细节优化" };
const dimensions: Record<string, string> = {
  opening_hook: "开头钩子", middle_pacing: "中段节奏", ending_hook: "结尾效果", character_motivation: "人物动机",
};

export default function NovelReaderReport({ report }: { report: RecordValue | null }) {
  const verdict = text(report?.verdict);
  const score = typeof report?.continue_reading_score === "number" && Number.isFinite(report.continue_reading_score) ? report.continue_reading_score : null;
  const issues = Array.isArray(report?.issues) ? report.issues : [];
  const dimensionEntries = Object.entries(record(report?.dimensions) || {}).filter(([key]) => dimensions[key]);
  const constraints = Array.isArray(report?.repair_constraints) ? report.repair_constraints.map(text).filter(Boolean) : [];
  const verdictLabel = ({ revise: "建议返修", reject: "需要重写", pass: "可以继续" } as Record<string, string>)[verdict] || "等待工作流报告";
  return <>
    <div className="mt-5 flex items-end gap-3"><span className={`text-5xl font-semibold ${["revise", "reject"].includes(verdict) ? "text-warning" : "text-success"}`}>{score ?? "—"}</span><span className="mb-2 text-sm text-muted-foreground">{verdictLabel}</span></div>
    {text(report?.summary) && <p className="mt-4 text-sm leading-6 text-muted-foreground">{text(report?.summary)}</p>}
    {issues.length > 0 && <div className="mt-5 space-y-3"><h3 className="text-sm font-medium">读者指出的问题 · {issues.length} 项</h3>{issues.map((issue, index) => {
      const detail = record(issue);
      const priority = text(detail?.priority);
      const fields = detail ? [
        ["问题位置", text(detail.location)], ["阅读影响", text(detail.impact)], ["修改目标", text(detail.goal ?? detail.suggestion ?? detail.recommendation)],
      ].filter(([, value]) => value) : [];
      return <article key={index} className="rounded-xl border border-border bg-secondary/30 p-4 text-sm leading-6"><div className="mb-2 flex flex-wrap items-center gap-2"><span className="font-medium">问题 {index + 1}</span>{priority && <span className="rounded-full bg-background/60 px-2 py-0.5 text-xs text-muted-foreground">{priorities[priority] || "待评估优先级"}</span>}</div>{fields.length ? <dl className="space-y-2">{fields.map(([label, value]) => <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-0.5 whitespace-pre-wrap">{value}</dd></div>)}</dl> : <p className="whitespace-pre-wrap">{text(issue) || "这条建议暂缺详细说明，请刷新评估。"}</p>}</article>;
    })}</div>}
    {dimensionEntries.length > 0 && <details className="mt-4 rounded-xl border border-border p-3"><summary className="cursor-pointer text-sm">各项阅读评价</summary><dl className="mt-3 space-y-3">{dimensionEntries.map(([key, value]) => <div key={key}><dt className="text-sm font-medium">{dimensions[key]}</dt><dd className="mt-1 text-sm leading-6 text-muted-foreground">{text(record(value)?.note ?? value)}</dd></div>)}</dl></details>}
    {constraints.length > 0 && <details className="mt-3 rounded-xl border border-border p-3"><summary className="cursor-pointer text-sm">返修时需要保留的设定</summary><ul className="mt-3 list-disc space-y-2 pl-4 text-sm leading-6 text-muted-foreground">{constraints.map((constraint, index) => <li key={index}>{constraint}</li>)}</ul></details>}
    {!report && <p className="mt-3 text-sm leading-6 text-muted-foreground">尚未读取到评估报告。完成模拟读者步骤后，可刷新查看。</p>}
  </>;
}
