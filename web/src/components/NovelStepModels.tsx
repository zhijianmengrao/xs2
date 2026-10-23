import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Cpu, Loader2, RefreshCw } from "lucide-react";
import { getAllModels } from "../lib/api";
import { readNovelModels, recordedTaskModels, saveNovelModels, type NovelModelSettings } from "../lib/novel-workbench-models";
import type { WorkflowTask } from "../types";

const sources = { workflow: "步骤设置", agent: "角色默认", system: "系统默认", parameter: "工作流参数" };
type ModelOption = { value: string; label: string };

export default function NovelStepModels({ workflowId, task, disabled, onPendingChange, onSaved }: {
  workflowId: string; task: WorkflowTask | null; disabled: boolean;
  onPendingChange: (pending: boolean) => void; onSaved: () => void;
}) {
  const [settings, setSettings] = useState<NovelModelSettings | null>(null);
  const [options, setOptions] = useState<ModelOption[]>([]);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [open, setOpen] = useState(false);
  const [allModel, setAllModel] = useState("");
  const alive = useRef(true);
  const loadSequence = useRef(0);
  const callback = useRef(onPendingChange); callback.current = onPendingChange;
  const dirty = !!settings && settings.nodes.some(node => node.editable && choices[node.id] !== node.override);
  useEffect(() => { callback.current(saving || dirty); }, [saving, dirty]);
  useEffect(() => () => { alive.current = false; callback.current(false); }, []);

  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    setLoading(true); setError(""); setFeedback("");
    try {
      const [current, available] = await Promise.all([readNovelModels(workflowId), getAllModels()]);
      if (!alive.current || sequence !== loadSequence.current) return;
      setSettings(current); setChoices(Object.fromEntries(current.nodes.map(node => [node.id, node.override])));
      setOptions(available.models); setAllModel("");
    } catch (failure) {
      if (alive.current && sequence === loadSequence.current) setError(failure instanceof Error ? failure.message : "模型设置读取失败，请重试。");
    } finally { if (alive.current && sequence === loadSequence.current) setLoading(false); }
  }, [workflowId]);
  useEffect(() => { alive.current = true; void load(); }, [workflowId, load]);
  const name = (model: string) => options.find(option => option.value === model)?.label || model || "未配置";
  const effective = [...new Set(settings?.nodes.map(node => node.source === "parameter" ? "由参数决定" : name(node.effective_model)) || [])];
  const records = useMemo(() => recordedTaskModels(task), [task]);
  const actual = [...new Set(records.flatMap(record => record.models))];

  async function save() {
    if (!settings || saving || disabled || !dirty) return;
    setSaving(true); setError(""); setFeedback("正在保存到对应工作流…");
    try {
      const result = await saveNovelModels(settings, Object.fromEntries(settings.nodes.filter(node => node.editable).map(node => [node.id, choices[node.id]])));
      if (!alive.current) return;
      setSettings(result); setChoices(Object.fromEntries(result.nodes.map(node => [node.id, node.override])));
      setFeedback("已保存并回读确认，后续任务将使用新模型。"); onSaved();
    } catch (failure) {
      if (alive.current) { setError(failure instanceof Error ? failure.message : "模型设置保存失败，请重试。"); setFeedback(""); }
    } finally { if (alive.current) setSaving(false); }
  }
  const locked = disabled || saving || loading;
  return <section className="novel-model-panel mt-5 rounded-xl border border-border bg-secondary/20 p-4" aria-label="当前步骤模型" aria-busy={loading || saving}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex min-w-0 items-start gap-2.5"><Cpu className="mt-0.5 h-4 w-4 shrink-0 text-primary" /><div>
        <p className="text-xs font-medium text-muted-foreground">后续任务模型</p>
        <p className="mt-1 break-words text-sm font-medium">{loading ? "正在读取工作流模型…" : settings?.nodes.length === 0 ? "此步骤无需大模型" : effective.length > 1 ? `按角色使用 ${effective.length} 种配置` : effective[0] || "暂时无法读取"}</p>
        {settings?.nodes.length === 1 && <p className="mt-1 text-xs text-muted-foreground">来自{sources[settings.nodes[0].source]}</p>}
      </div></div>
      <div className="flex items-center gap-2"><button onClick={() => void load()} disabled={locked} title="重新读取已保存的模型配置" aria-label="刷新步骤模型" className="rounded-lg p-2 hover:bg-secondary disabled:opacity-50"><RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /></button>
        {!!settings?.nodes.length && <button onClick={() => setOpen(value => !value)} aria-expanded={open} className="flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-xs hover:bg-secondary">{open ? "收起模型设置" : "调整模型"}<ChevronDown className={`h-3 w-3 ${open ? "rotate-180" : ""}`} /></button>}
      </div>
    </div>
    {settings?.nodes.some(node => !node.available && node.editable) && <p className="mt-3 text-xs text-warning">部分模型未配置或已不可用，请展开模型设置检查。</p>}
    {open && !!settings?.nodes.length && <div className="mt-4 space-y-4 border-t border-border pt-4">
      <p className="text-xs leading-6 text-muted-foreground">保存会更新本步骤的工作流默认配置，所有作品后续新建的同一步骤任务均会采用。已创建或正在运行的任务保留原配置。</p>
      <label className="block text-sm">统一设置本步骤<select aria-label="统一设置步骤模型" value={allModel} disabled={locked || !settings.nodes.some(node => node.editable)} onChange={event => {
        const value = event.target.value; setAllModel(value); setFeedback("");
        setChoices(current => ({ ...current, ...Object.fromEntries(settings.nodes.filter(node => node.editable).map(node => [node.id, value === "inherit" ? "" : value])) }));
      }} className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"><option value="" disabled>选择模型，或展开下方逐个设置</option><option value="inherit">恢复各角色 / 系统默认</option>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <details className="rounded-lg border border-border p-3"><summary className="cursor-pointer text-xs font-medium">分别设置 {settings.nodes.length} 个 AI 角色</summary><div className="mt-3 space-y-3">{settings.nodes.map(node => <label key={node.id} className="block text-sm"><span>{node.label}</span><span className="ml-2 text-[11px] text-muted-foreground">{sources[node.source]}{node.condition ? " · 按流程条件执行" : ""}</span>{node.editable ? <select aria-label={`${node.label}模型`} value={choices[node.id] || ""} disabled={locked} onChange={event => { setAllModel(""); setFeedback(""); setChoices(current => ({ ...current, [node.id]: event.target.value })); }} className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"><option value="">角色 / 系统默认</option>{choices[node.id] && !options.some(option => option.value === choices[node.id]) && <option value={choices[node.id]}>{choices[node.id]}（不可用）</option>}{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select> : <p className="mt-2 text-xs text-muted-foreground">此角色由参数绑定模型，请在原有工作流参数中调整。</p>}<p className="mt-1 text-xs text-muted-foreground">已保存：{node.source === "parameter" ? "由参数决定" : name(node.effective_model)}</p></label>)}</div></details>
      <div className="flex flex-wrap items-center gap-3"><button onClick={() => void save()} disabled={locked || !dirty} className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-xs font-semibold text-primary-foreground disabled:opacity-50">{saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}{saving ? "正在保存…" : dirty ? "保存并同步工作流" : "配置已同步"}</button>{dirty && <><button disabled={saving} onClick={() => { setChoices(Object.fromEntries(settings.nodes.map(node => [node.id, node.override]))); setAllModel(""); setFeedback("已撤销尚未保存的选择。"); }} className="text-xs text-muted-foreground hover:text-foreground">撤销选择</button><span className="text-xs text-warning">尚未保存，当前配置仍生效</span></>}</div>
    </div>}
    {task && <details className="mt-3 text-xs text-muted-foreground"><summary className="cursor-pointer">已有任务的模型记录 · {actual.length ? actual.map(name).join("、") : "尚无调用记录"}</summary><ul className="mt-2 space-y-1.5">{settings?.nodes.map(node => { const record = records.find(row => row.id === node.id); return <li key={node.id}>{node.label}：{record?.models.length ? record.models.map(name).join(" → ") : record?.status === "skipped" ? "已跳过" : "未记录模型调用"}</li>; })}</ul><p className="mt-2 leading-5">这里显示任务实际调用记录，修改后续配置不会改写历史记录。</p></details>}
    {feedback && <p role="status" aria-live="polite" className={`mt-3 text-xs ${saving ? "text-primary" : "text-success"}`}>{feedback}</p>}
    {error && <p role="alert" className="mt-3 text-xs leading-6 text-destructive">{error}<button disabled={loading || saving} onClick={() => void load()} className="ml-2 underline">重新读取</button></p>}
  </section>;
}
