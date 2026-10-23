import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Loader2, RefreshCw, Trash2 } from "lucide-react";
import {
  deleteWritingLibrary, getWritingLibraryUsage, listWritingLibrary,
  type WritingLibraryItem, type WritingLibraryUsage,
} from "../lib/api";
import { useDialog } from "./ui/use-dialog";
import WritingLibraryReader from "./WritingLibraryReader";

type Props = {
  project: { values: Record<string, string> };
  workflowId: string;
  workspace: string;
  onAttach: (id: string, refresh?: boolean) => Promise<void>;
  onBack: () => void;
  onConfirm: (adopted?: boolean) => void;
};

export default function WritingLibraryView({ project, workflowId, workspace, onAttach, onBack, onConfirm }: Props) {
  const dialog = useDialog();
  const [items, setItems] = useState<WritingLibraryItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [usageLoading, setUsageLoading] = useState(true);
  const [attachingId, setAttachingId] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [readingId, setReadingId] = useState("");
  const [usageById, setUsageById] = useState<Record<string, WritingLibraryUsage>>({});
  const operation = useRef(false);
  const mounted = useRef(true);
  const requestVersion = useRef(0);
  const allSelected = items.length > 0 && items.every(item => selected.includes(item.id));
  const busy = loading || deleting || !!attachingId;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      // 卸载失效由 mounted 标志覆盖（refresh/attach 都先查 mounted.current）；
      // 不再在 cleanup 里读写 requestVersion，避免 exhaustive-deps 对 ref 的告警。
      dialog.cancelMatching("writing-library-delete:");
    };
  }, [dialog]);

  const refresh = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true); setUsageLoading(true); setError("");
    const [library, usage] = await Promise.allSettled([
      listWritingLibrary(), getWritingLibraryUsage(workflowId, workspace),
    ]);
    if (!mounted.current || version !== requestVersion.current) return;
    if (library.status === "fulfilled") {
      setItems(library.value.items);
      setSelected(current => current.filter(id => library.value.items.some(item => item.id === id)));
      setReadingId(current => library.value.items.some(item => item.id === current) ? current : "");
    }
    if (usage.status === "fulfilled") setUsageById(usage.value.items);
    const failures = [];
    if (library.status === "rejected") failures.push(`读取写法库失败：${String(library.reason instanceof Error ? library.reason.message : library.reason)}`);
    if (usage.status === "rejected") failures.push(`读取采用状态失败：${String(usage.reason instanceof Error ? usage.reason.message : usage.reason)}`);
    setError(failures.join("；"));
    setLoading(false);
    // Do not offer adoption with an unknown state; a failed usage read can retry.
    setUsageLoading(usage.status === "rejected");
  }, [workflowId, workspace]);

  useEffect(() => { void refresh(); }, [refresh]);

  const attach = async (id: string, update = false) => {
    if (operation.current || usageLoading || (!update && usageById[id]?.status && usageById[id].status !== "available")) return;
    operation.current = true; setAttachingId(id); setError(""); setFeedback("正在把写法带入本书…");
    try {
      await onAttach(id, update);
      const result = await getWritingLibraryUsage(workflowId, workspace);
      if (!mounted.current) return;
      setUsageById(result.items);
      setFeedback(update ? "本书候选与分析已更新。新增内容需检查并确认后才生效。" : "已加入本书候选。请继续兼容检查，再确认实际采用的写法。");
    } catch (failure) {
      if (mounted.current) { setFeedback(""); setError(`导入失败：${failure instanceof Error ? failure.message : String(failure)}`); }
    } finally {
      operation.current = false;
      if (mounted.current) setAttachingId("");
    }
  };

  const remove = async (ids: string[]) => {
    if (operation.current || busy || !ids.length) return;
    const targets = items.filter(item => ids.includes(item.id));
    if (!targets.length) return;
    operation.current = true;
    let deletedCount = 0;
    let missingCount = 0;
    try {
      const confirmed = await dialog.open<boolean>({
        key: `writing-library-delete:${targets.map(item => item.id).join(",")}`,
        title: targets.length === 1 ? "删除这份写法？" : `删除选中的 ${targets.length} 份写法？`,
        description: "会永久删除所选写法库条目的实际文件，包括风格、写法和冲突分析。已经复制到小说里的候选与采用内容继续保留；原始参考资料和蒸馏任务也会保留。",
        render: ({ resolve, cancel }) => <>
          <ul className="mt-4 max-h-48 space-y-2 overflow-y-auto rounded-lg border border-border bg-background/50 p-3 text-sm">
            {targets.map(item => <li key={item.id} className="break-words">{item.name}</li>)}
          </ul>
          <div className="mt-6 flex flex-wrap justify-end gap-2">
            <button data-dialog-autofocus onClick={cancel} className="min-h-11 rounded-lg border border-border px-4 py-2 text-sm">取消</button>
            <button onClick={() => resolve(true)} className="min-h-11 rounded-lg bg-destructive px-4 py-2 text-sm text-destructive-foreground">确认删除 {targets.length} 份写法</button>
          </div>
        </>,
      });
      if (!confirmed || !mounted.current) return;
      setDeleting(true); setError(""); setFeedback(`正在删除 ${targets.length} 份写法…`);
      const failures = [];
      // The API validates up to 200 targets at a time. Apply each completed
      // batch immediately so a later network failure cannot hide prior success.
      for (let offset = 0; offset < targets.length; offset += 200) {
        const result = await deleteWritingLibrary(workflowId, targets.slice(offset, offset + 200).map(item => item.id));
        if (!mounted.current) return;
        const removed = new Set([...result.deleted_ids, ...result.missing_ids]);
        setItems(current => current.filter(item => !removed.has(item.id)));
        setSelected(current => current.filter(id => !removed.has(id)));
        setReadingId(current => removed.has(current) ? "" : current);
        setUsageById(current => Object.fromEntries(Object.entries(current).filter(([id]) => !removed.has(id))));
        for (const id of removed) sessionStorage.removeItem(`xs2-writing-reading:${id}`);
        deletedCount += result.deleted_ids.length;
        missingCount += result.missing_ids.length;
        failures.push(...result.failed);
        if (offset + 200 < targets.length) setFeedback(`正在删除写法…已处理 ${offset + 200}/${targets.length} 份`);
      }
      const messages = [];
      if (deletedCount) messages.push(`已删除 ${deletedCount} 份写法`);
      if (missingCount) messages.push(`${missingCount} 份已不存在，已同步列表`);
      setFeedback(messages.join("；") || "本次没有删除条目。");
      if (failures.length) setError(failures.map(item => `${targets.find(target => target.id === item.id)?.name || item.id}：${item.message}`).join("；") + "。失败条目仍可选择重试。");
    } catch (failure) {
      if (mounted.current) {
        setFeedback(deletedCount || missingCount ? `已删除 ${deletedCount} 份写法，另有 ${missingCount} 份已不存在；剩余条目待核对。` : "");
        setError(`删除未完成：${failure instanceof Error ? failure.message : String(failure)}。请刷新核对后重试。`);
      }
    } finally {
      operation.current = false;
      if (mounted.current) setDeleting(false);
    }
  };

  const notices = <>{feedback && <p role="status" className="rounded-xl border border-primary/25 bg-primary/5 p-3 text-sm text-primary">{feedback}</p>}{error && <p role="alert" className="rounded-xl border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}</>;
  if (readingId) return <div className="space-y-4">
    {notices}
    <div className="flex justify-end"><button disabled={busy} onClick={() => void remove([readingId])} className="flex min-h-10 items-center gap-2 rounded-lg border border-destructive/30 px-3 py-2 text-sm text-destructive disabled:opacity-50"><Trash2 className="h-4 w-4" />{deleting ? "正在删除…" : "删除这份写法"}</button></div>
    <WritingLibraryReader key={readingId} id={readingId} usage={usageById[readingId]} attaching={busy || usageLoading} onBack={() => { if (!operation.current) setReadingId(""); }} onAttach={() => void attach(readingId)} onUpdate={() => void attach(readingId, true)} onConfirm={() => { if (!operation.current) onConfirm(usageById[readingId]?.status === "adopted"); }} />
  </div>;

  const pov = project.values.narrative_pov === "first_person" ? "first_person" : "third_person";
  const genre = (project.values.genre || "").trim();
  return <div className="space-y-5">
    <header>
      <button onClick={onBack} className="mb-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3 w-3" />返回作品</button>
      <p className="text-xs font-semibold tracking-[0.2em] text-primary">共享写法库</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">跨作品复用蒸馏结果</h1>
      <p className="mt-2 text-sm text-muted-foreground">先按题材和视角匹配，再由你决定哪些风格、写法和冲突进入本书。</p>
    </header>
    <div className="rounded-xl border border-primary/25 bg-primary/5 p-4">
      <p className="text-sm leading-7">
        💡 <strong>推荐</strong>：使用「创作流程 → AI 小说顾问」获得个性化写法推荐，一键快速采用。
      </p>
      <p className="mt-2 text-xs leading-6 text-muted-foreground">
        本页面适合高级用户手动浏览和选择写法库。如果您希望 AI 根据作品自动推荐最合适的写法，请使用创作流程中的小说顾问功能。
      </p>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3" aria-label="写法库批量操作">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex min-h-10 cursor-pointer items-center gap-2">
          <input type="checkbox" aria-label="全选写法" checked={allSelected} disabled={busy || !items.length} onChange={event => setSelected(event.target.checked ? items.map(item => item.id) : [])} className="h-4 w-4 accent-primary" />
          全选
        </label>
        <span className="text-muted-foreground">共 {items.length} 份 · 已选 {selected.length} 份</span>
        {selected.length > 0 && <button disabled={busy} onClick={() => setSelected([])} className="min-h-10 px-1 text-primary disabled:opacity-50">清空选择</button>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button disabled={busy} onClick={() => void refresh()} className="flex min-h-10 items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />{loading ? "读取中…" : "刷新写法库"}</button>
        <button disabled={busy || !selected.length} onClick={() => void remove(selected)} className="flex min-h-10 items-center gap-2 rounded-lg border border-destructive/30 px-3 py-2 text-sm text-destructive disabled:opacity-50">{deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}{deleting ? "正在删除…" : `批量删除${selected.length ? `（${selected.length}）` : ""}`}</button>
      </div>
    </div>
    {loading && <p role="status" className="text-sm text-muted-foreground">正在读取写法库…</p>}
    {notices}
    {!loading && !items.length && !error && <div className="rounded-2xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">还没有共享写法。完成一次独立资料蒸馏后，会自动保存到这里。</div>}
    <div className="grid gap-4 md:grid-cols-2">{items.map(item => {
      const match = (item.pov.length === 0 || item.pov.includes(pov)) && (!genre || item.genres.length === 0 || item.genres.some(tag => genre.includes(tag) || tag.includes(genre)));
      const usage = usageById[item.id];
      const attached = !!usage && usage.status !== "available";
      return <article key={item.id} className={`rounded-2xl border bg-card p-5 shadow-sm ${selected.includes(item.id) ? "border-primary/60" : "border-border"}`}>
        <div className="flex items-start justify-between gap-3">
          <label className="flex min-w-0 cursor-pointer items-start gap-3">
            <input type="checkbox" aria-label={`选择写法：${item.name}`} checked={selected.includes(item.id)} disabled={busy} onChange={event => setSelected(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))} className="mt-1 h-4 w-4 shrink-0 accent-primary" />
            <span className="min-w-0"><span className="block break-words font-semibold">{item.name}</span><span className="mt-2 block text-xs text-muted-foreground">{item.genres.join("、") || "未标注题材"} · {item.style_count || 0} 条风格 · {item.candidate_count} 条写法 · {item.conflict_count || 0} 条冲突</span></span>
          </label>
          <button aria-label={`删除写法：${item.name}`} title="删除这份写法" disabled={busy} onClick={() => void remove([item.id])} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"><Trash2 className="h-4 w-4" /></button>
        </div>
        <div className="mt-4 flex items-start gap-2"><span className="shrink-0 rounded-full bg-secondary px-2 py-1 text-xs">{!item.pov.length ? "视角未标注" : match ? "初步匹配" : "需要适配"}</span><p className="text-xs leading-6 text-muted-foreground">{match ? "可作为候选来源，风格、写法与冲突的适用性仍需逐条确认。" : `当前作品是${pov === "first_person" ? "第一" : "第三"}人称，库中视角为 ${item.pov.map(value => value === "first_person" ? "第一人称" : value === "third_person" ? "第三人称" : "其他视角").join("、") || "未标注"}，助手会提示风险。`}</p></div>
        <button disabled={busy} onClick={() => { setReadingId(item.id); setFeedback(""); setError(""); }} className="mt-4 w-full rounded-xl border border-border px-3 py-2.5 text-sm hover:bg-secondary/60 disabled:opacity-50">查看具体写法</button>
        <button disabled={busy || usageLoading || attached} onClick={() => void attach(item.id)} className="mt-4 w-full rounded-xl bg-primary px-3 py-2.5 text-sm text-primary-foreground disabled:opacity-60">{attachingId === item.id ? "正在加入…" : usageLoading ? "采用状态待核对" : usage?.status === "adopted" ? `已采用：风格 ${usage.style_count || 0} · 写法 ${usage.selected_count} · 冲突 ${usage.conflict_count || 0}` : attached ? "已加入本书候选，待确认" : "加入本书候选"}</button>
        {usage?.update_available && <button disabled={busy || usageLoading} onClick={() => void attach(item.id, true)} className="mt-3 text-sm text-primary disabled:opacity-50">更新本书候选与分析</button>}
        {attached && <button disabled={busy} onClick={() => onConfirm(usage.status === "adopted")} className="mt-3 text-sm text-primary disabled:opacity-50">{usage.status === "adopted" ? "查看已采用写法 / 选择新增 →" : "继续兼容检查与采用确认 →"}</button>}
      </article>;
    })}</div>
  </div>;
}
