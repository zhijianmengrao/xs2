import { useEffect, useRef, useState } from 'react';
import { Loader2, Sparkles, WandSparkles } from 'lucide-react';
import { askNovelAssistant, applyNovelRepairPlan, fetchNovelAssistantHistory, type NovelAssistantEntry } from '../lib/api';
import NovelArchiveContent from './NovelArchiveContent';

type Props = {workspace: string; chapter: string; project: Record<string, unknown>; ready: boolean;
  readerSummary: string; onRepair: (feedbackPath: string, modelId: string) => Promise<void>; onFlow: () => void};

export default function NovelRepairPanel({workspace, chapter, project, ready, readerSummary, onRepair, onFlow}: Props) {
  const [entries, setEntries] = useState<NovelAssistantEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [applying, setApplying] = useState(false);
  const [extra, setExtra] = useState('');
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [refresh, setRefresh] = useState(0);
  const guard = useRef(false);
  const appliedGuard = useRef(false);
  const active = useRef(true);
  useEffect(() => {active.current = true; return () => {active.current = false;};}, []);
  useEffect(() => {
    let mounted = true;
    let timer: number | undefined;
    const poll = async () => {
      let again = false;
      try {
        const data = await fetchNovelAssistantHistory('xs2-novel-flywheel-build', workspace);
        if (!mounted) return;
        setEntries(data.entries);
        again = data.entries.some(item => item.status === 'running');
      } catch (error) {
        if (mounted) setFeedback(`读取方案失败：${error instanceof Error ? error.message : String(error)}。将自动重试。`);
        again = true;
      } finally {
        if (mounted) {setLoading(false); if (again) timer = window.setTimeout(() => void poll(), 2500);}
      }
    };
    void poll();
    return () => {mounted = false; if (timer) window.clearTimeout(timer);};
  }, [workspace, refresh]);
  const running = entries.find(item => item.status === 'running');
  const plans = entries.filter(item => item.purpose === 'reader_repair' && item.chapter === chapter);
  const latest = plans[plans.length - 1];
  const plan = [...plans].reverse().find(item => item.status === 'completed');
  useEffect(() => {setDraft(plan?.applied_plan || plan?.reply || ''); setEditing(false);}, [plan?.id, plan?.applied_plan, plan?.reply]);
  const busy = loading || submitting || !!running || applying;
  const ask = async () => {
    if (busy || guard.current || !ready) return;
    guard.current = true; setSubmitting(true); setFeedback('正在提交，读取本章正文和完整读者报告…');
    try {
      const result = await askNovelAssistant({workflow_id:'xs2-novel-flywheel-build', workspace,
        request_id:crypto.randomUUID(), purpose:'reader_repair', chapter, project, stage:'读者评估后返修规划',
        question:`请根据第${chapter}章的正文及最新读者评估，规划定向返修，逐项回应问题并给出可执行修改和复评验收点。${extra.trim() ? '\n用户追加意见：'+extra.trim() : ''}`});
      if (!active.current) return;
      setEntries(current => [...current.filter(item => item.id !== result.entry.id), result.entry]);
      setFeedback(result.entry.purpose === 'reader_repair' ? '' : '另一个助手分析正在进行，请等待完成后再规划返修。');
      setRefresh(value => value + 1);
    } catch (error) {if (active.current) {setFeedback(`规划未完成：${error instanceof Error ? error.message : String(error)}`); setRefresh(value => value + 1);}}
    finally {guard.current = false; if (active.current) setSubmitting(false);}
  };
  const apply = async () => {
    if (!plan || busy || plan.applied_at || appliedGuard.current) return;
    appliedGuard.current = true; setApplying(true); setFeedback('正在保存已确认意见，准备启动原有返修工作流…');
    try {
      const result = await applyNovelRepairPlan({workflow_id:'xs2-novel-flywheel-polish', workspace, entry_id:plan.id, plan:draft});
      if (!active.current) return;
      if (result.already_applied) {setFeedback('这份方案已准备好，正在恢复对应章节的返修流程…');}
      await onRepair(result.feedback_path, result.model_id);
    } catch (error) {if (active.current) setFeedback(`尚未启动返修：${error instanceof Error ? error.message : String(error)}`);}
    finally {appliedGuard.current = false; if (active.current) setApplying(false);}
  };
  return <section className="rounded-2xl border border-primary/25 bg-card p-5">
    <h2 className="flex items-center gap-2 font-semibold"><Sparkles className="h-4 w-4 text-primary"/>根据读者意见返修</h2>
    {!plan && readerSummary && <p className="mt-3 rounded-lg bg-secondary/40 p-3 text-sm leading-7">本次读者结论：{readerSummary}</p>}
    <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm leading-6 text-muted-foreground"><li>AI 读取本章正文、完整读者报告、人物档案和本书风格。</li><li>查看方案，可补充或调整意见。</li><li>默认模型按原工作流执行润色返修 → 读者复评，完成后回到此页。</li></ol>
    <label className="mt-4 block text-sm">补充返修要求（选填）<textarea aria-label="补充返修要求" value={extra} disabled={busy} onChange={event => setExtra(event.target.value)} rows={3} placeholder="例如：保留结尾的人物互动，重点压缩中段重复说明。" className="mt-2 w-full rounded-xl border border-border bg-background p-3 text-sm"/></label>
    <button disabled={!ready || busy} onClick={() => void ask()} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-primary/30 bg-primary/10 px-4 py-3 text-sm text-primary disabled:opacity-50">{busy && !applying ? <Loader2 className="h-4 w-4 animate-spin"/> : <WandSparkles className="h-4 w-4"/>}{loading ? '正在恢复方案…' : submitting ? '正在提交…' : running ? 'AI 正在分析…' : plan ? '根据最新评估重新规划' : '让 AI 助手规划返修'}</button>
    {!ready && <p className="mt-2 text-xs text-muted-foreground">本章正文和读者报告就绪后才能规划返修。</p>}
    {running && <p role="status" className="mt-3 text-sm leading-6 text-muted-foreground">{running.message || '正在分析正文和读者问题…'} 方案完成前不会修改正文。切换页面后分析仍会保留。</p>}
    {feedback && <p role="status" className="mt-3 text-sm leading-6 text-warning">{feedback}</p>}
    {latest?.status === 'failed' && <p role="alert" className="mt-3 text-sm text-warning">本次规划失败：{latest.message}，可重新规划。</p>}
    {plan && <div className="mt-5 border-t border-border pt-4">
      <h3 className="font-medium">第 {Number(chapter)} 章 · AI 返修方案</h3>
      <p className="mt-2 text-xs leading-6 text-muted-foreground">依据：本章正文 + 完整读者报告（问题、优先级、保留约束）。分析时间：{new Date(plan.created_at).toLocaleString('zh-CN')}。</p>
      {plan.reader_summary && <p className="mt-3 rounded-lg bg-secondary/40 p-3 text-sm leading-7">读者结论：{plan.reader_summary}</p>}
      <button disabled={busy || !!plan.applied_at || !draft.trim()} onClick={() => void apply()} className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-50">{applying && <Loader2 className="h-4 w-4 animate-spin"/>}{applying ? '正在准备返修…' : plan.applied_at ? '此方案已交给返修流程' : '按此方案返修并复评'}</button>
      <p className="mt-2 text-xs leading-6 text-muted-foreground">请先查看下方方案，必要时调整，再点击上方按钮确认执行。</p>
      <div className="mt-4 max-h-[540px] overflow-auto"><NovelArchiveContent content={draft}/></div>
      {!plan.applied_at && <><button disabled={busy} onClick={() => setEditing(value => !value)} className="mt-3 rounded-lg border border-border px-3 py-2 text-sm">{editing ? '收起编辑' : '调整返修意见'}</button>{editing && <textarea aria-label="返修方案" value={draft} disabled={busy} onChange={event => setDraft(event.target.value)} rows={12} className="mt-3 w-full rounded-xl border border-border bg-background p-3 text-sm leading-7"/>}</>}
      <p className="mt-2 text-xs leading-6 text-muted-foreground">仅修改本章，原稿会备份。运行时需保持创作流程页打开；复评后停下供你检查，不会直接覆盖导出成品。方案过期会提示重新分析。</p>
      {plan.applied_at && <button disabled={busy} onClick={onFlow} className="mt-3 text-sm text-primary underline underline-offset-4">查看返修任务与进度</button>}
    </div>}
  </section>;
}
