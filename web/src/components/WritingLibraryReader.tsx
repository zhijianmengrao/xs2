import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Loader2, RefreshCw, Search } from "lucide-react";
import { getWritingLibraryItem } from "../lib/api";
import NovelReferenceContent from "./NovelReferenceContent";
import NovelReferenceChoice, { ReferenceEvidence } from "./NovelReferenceChoice";
import { referenceText, referenceTitle } from "./novel-reference";
import type { WritingLibraryUsage } from "../lib/api";

type Detail = Awaited<ReturnType<typeof getWritingLibraryItem>>;
type Tab = "profile" | "mechanisms" | "conflicts";
const documents: Record<string, string> = {"Writing-DNA.md": "综合风格", "语言DNA.md": "语言表达", "文章结构模板.md": "叙事结构", "写作视角与认知框架.md": "叙事视角", "视觉风格指南.md": "意象与呈现", "人物写法.md": "人物写法"};
export default function WritingLibraryReader({ id, usage, attaching, onBack, onAttach, onUpdate, onConfirm }: { id: string; usage?: WritingLibraryUsage; attaching: boolean; onBack: () => void; onAttach: () => void; onUpdate: () => void; onConfirm: () => void }) {
  const cacheKey = `xs2-writing-reading:${id}`;
  const [reading, setReading] = useState<{tab: Tab; query: string; selection: Partial<Record<Tab, string>>; document: string}>(() => {
    try { const saved = JSON.parse(sessionStorage.getItem(cacheKey) || "null"); if (saved && ["profile", "mechanisms", "conflicts"].includes(saved.tab)) return saved; } catch { /* invalid reading position */ }
    return {tab: "profile", query: "", selection: {}, document: "Writing-DNA.md"};
  });
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const {tab, query} = reading;
  const attached = usage?.status === "attached" || usage?.status === "adopted";
  useEffect(() => { sessionStorage.setItem(cacheKey, JSON.stringify(reading)); }, [cacheKey, reading]);
  useEffect(() => {
    let active = true; setLoading(true); setError("");
    void getWritingLibraryItem(id).then(value => { if (active) setDetail(value); }).catch(failure => { if (active) setError(failure instanceof Error ? failure.message : "读取失败，请重试。"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, revision]);
  const candidateLists = useMemo(
    () => ({
      mechanisms: detail?.candidates.candidates || [],
      styles: detail?.candidates.style_choices || [],
      conflicts: detail?.candidates.conflict_choices || [],
    }),
    [detail],
  );
  const { mechanisms, styles, conflicts } = candidateLists;
  const entries = useMemo(() => (tab === "profile" ? styles : tab === "conflicts" ? conflicts : mechanisms).map((value, index) => ({value, index, id: String(value.choice_id || value.candidate_id || index), title: referenceTitle(value.title || value.mechanism)})).filter(item => !query.trim() || referenceText(item.value).includes(query.trim())), [tab, styles, conflicts, mechanisms, query]);
  const selected = entries.find(item => item.id === reading.selection[tab]) || entries[0];
  const adoptedIds = (tab === "profile" ? usage?.selected_style_ids : tab === "conflicts" ? usage?.selected_conflict_ids : usage?.selected_candidate_ids) || [];
  const adopted = selected && adoptedIds.includes(selected.id);
  const setTab = (value: Tab) => setReading(current => ({...current, tab: value, query: ""}));
  return <div className="space-y-5">
    <button onClick={onBack} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />返回写法库</button>
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs text-primary">写法阅读</p><h1 className="mt-2 text-2xl font-semibold">{detail?.manifest.name || "正在读取写法…"}</h1><p className="mt-2 text-sm text-muted-foreground">库中分析与本书采用内容分别记录；只有确认采用的内容才进入创作。</p></div><div className="flex flex-wrap gap-2"><button disabled={loading} onClick={() => setRevision(value => value + 1)} className="rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-50"><RefreshCw className={`inline h-4 w-4 ${loading ? "animate-spin" : ""}`} /> {loading ? "读取中…" : "刷新"}</button><button disabled={loading || !detail || attaching || attached} onClick={onAttach} className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">{attaching ? "正在加入…" : attached ? "已加入本书候选" : "加入本书候选"}</button></div></header>
    {detail && <p className="text-xs leading-6 text-muted-foreground">来源范围：{detail.manifest.source_mode === "serial_chapters" ? "长篇章节样本" : detail.manifest.source_mode === "short_full" ? "短篇全文" : "样本范围待判断"} · 结论仅覆盖已导入内容</p>}
    {loading && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在读取分析内容…</p>}
    {error && <p role="alert" className="rounded-xl border border-destructive/30 p-4 text-sm text-destructive">读取失败：{error}。可以刷新重试。</p>}
    {detail && <>
      {attached && <p role="status" className="rounded-lg bg-success/10 px-4 py-3 text-sm leading-7 text-success">本书已采用：风格 {usage?.style_count || 0} 条 · 写法 {usage?.selected_count || 0} 条 · 冲突 {usage?.conflict_count || 0} 条。<button onClick={onConfirm} className="ml-3 underline underline-offset-4">查看本书采用内容 / 选择新增 →</button></p>}
      {usage?.error && <p role="alert" className="text-sm text-destructive">{usage.error}</p>}
      {usage?.update_available && <p role="status" className="rounded-lg border border-primary/25 px-4 py-3 text-sm leading-7">库中有新增分析。<button disabled={attaching} onClick={onUpdate} className="ml-3 text-primary underline disabled:opacity-50">更新本书候选</button><span className="block text-xs text-muted-foreground">已有采用内容持续保留，新增内容需确认。</span></p>}
      <div role="tablist" aria-label="写法内容" className="flex gap-1 overflow-x-auto border-b border-border">{([{id: "profile", label: `风格 · ${styles.length}`}, {id: "mechanisms", label: `写法 · ${mechanisms.length}`}, {id: "conflicts", label: `冲突 · ${conflicts.length}`}] as const).map(item => <button key={item.id} role="tab" aria-selected={tab === item.id} onClick={() => setTab(item.id)} className={`shrink-0 border-b-2 px-4 py-3 text-sm ${tab === item.id ? "border-primary font-medium text-primary" : "border-transparent text-muted-foreground"}`}>{item.label}</button>)}</div>
      <label className="flex max-w-xl items-center gap-2 rounded-xl border border-border bg-card px-3 py-2.5"><Search className="h-4 w-4 text-muted-foreground" /><input aria-label="搜索分析内容" placeholder="搜索当前模块的特点、应用方法或使用边界" value={query} onChange={event => setReading(current => ({...current, query: event.target.value}))} className="w-full bg-transparent text-sm outline-none" /></label>
      {!entries.length && <p role="status" className="rounded-xl border border-border p-6 text-sm leading-7 text-muted-foreground">{query ? "没有匹配的条目，试试其他关键词。" : "暂无该类独立分析；已有其他内容仍可使用。"}</p>}
      {selected && <section className="rounded-2xl border border-border bg-card p-6 sm:p-8"><div className="mx-auto max-w-[76ch]">
        <label className="mb-6 flex flex-wrap items-center gap-3 border-b border-border/60 pb-4 text-sm text-muted-foreground">查看条目<select aria-label="选择分析条目" value={selected.id} onChange={event => setReading(current => ({...current, selection: {...current.selection, [tab]: event.target.value}}))} className="max-w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground">{entries.map(item => <option key={item.id} value={item.id}>{item.index + 1}. {item.title}</option>)}</select><span className="text-xs">共 {entries.length} 项</span></label>
        <p role="status" className={`mb-6 text-sm ${adopted ? "text-success" : "text-muted-foreground"}`}>{adopted ? "已采用 · 持续保留" : attached ? selected.value.requires_adaptation ? "本书候选 · 需适配，尚未采用" : "本书候选 · 尚未采用" : "库中分析 · 尚未加入本书"}</p>
        {tab === "mechanisms" ? <div className="space-y-6"><h2 className="text-xl font-semibold leading-8">{selected.title}</h2><div><h3 className="mb-3 text-sm font-medium text-accent">写法与作用</h3><p className="whitespace-pre-wrap text-[15px] leading-8">{referenceText(selected.value.mechanism)}</p></div>{[["怎么用到自己的故事", selected.value.transfer_guidance], ["适配建议", selected.value.adaptation_guidance], ["使用边界", selected.value.constraints], ["需要留意", selected.value.risk_flags]].map(([label, value], i) => referenceText(value) && <section key={i} className="border-t border-border/60 pt-5"><h3 className="mb-3 font-semibold">{String(label)}</h3><p className="whitespace-pre-wrap text-[15px] leading-8">{referenceText(value)}</p></section>)}<ReferenceEvidence value={selected.value.evidence} /></div> : <NovelReferenceChoice choice={(tab === "profile" ? styles : conflicts).find(item => item.choice_id === selected.id)!} />}
        {attached && !adopted && <button onClick={onConfirm} className="mt-6 text-sm text-primary underline underline-offset-4">到本书参考写法中选择与确认 →</button>}
      </div></section>}
      {tab === "profile" && detail.profile.markdown?.trim() && <details className="rounded-2xl border border-border bg-card p-6"><summary className="cursor-pointer font-medium">完整风格分析与统计依据</summary><div className="mx-auto mt-6 max-w-[76ch]"><label className="mb-6 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">阅读内容<select aria-label="选择风格文档" value={reading.document} onChange={event => setReading(current => ({...current, document: event.target.value}))} className="max-w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground">{Object.keys(detail.profile.documents || {"Writing-DNA.md": detail.profile.markdown}).map(name => <option key={name} value={name}>{documents[name] || name.replace(/\.md$/, "")}</option>)}</select></label><NovelReferenceContent content={detail.profile.documents?.[reading.document] || detail.profile.markdown} />{detail.profile.upstream?.repository && <p className="mt-6 text-xs text-muted-foreground">分析方法：<a href={detail.profile.upstream.repository} target="_blank" rel="noreferrer" className="text-primary underline">writing-dna-skill</a>，结合本项目的小说适配。</p>}</div></details>}
    </>}
  </div>;
}
