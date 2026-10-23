import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  BookOpen,
  ExternalLink,
  Filter,
  Loader2,
  RefreshCw,
  Search,
  Trophy,
} from "lucide-react";
import { createTask, getTask, listTasks, readWorkflowWorkspaceFile, runTask } from "../lib/api";

const MARKET_WORKFLOW = "xs2-novel-flywheel-market-ranking";
const DEFAULT_WORKSPACE = "C:\\xs2\\DeterminFlow\\data\\workspaces\\xs2-novel-workbench";

type RankingWork = {
  ranking_name: string;
  rank: number;
  platform_work_id: string;
  title: string;
  summary?: string;
  category?: string;
  tags?: string[];
  likes?: number;
  space_type?: string;
  detail_url?: string;
};

type Snapshot = {
  source_name: string;
  captured_at: string;
  boundary: string;
  work_count: number;
  rankings: string[];
  works: RankingWork[];
};

function parseLikes(value: number | undefined) {
  if (!value) return "—";
  if (value >= 10000) return `${(value / 10000).toFixed(value >= 100000 ? 0 : 1)} 万`;
  return value.toLocaleString();
}

export default function NovelMarketPage() {
  const [workspace, setWorkspace] = useState(() => localStorage.getItem("xs2-novel-workspace") || DEFAULT_WORKSPACE);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  type MarketTask = { task_id?: string; status?: string } | null;
const [task, setTask] = useState<MarketTask>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ranking, setRanking] = useState("");
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");

  const readLatestSnapshot = useCallback(async () => {
    try {
      const result = await listTasks(MARKET_WORKFLOW, { status: "completed", sort_by: "completed_at", sort_order: "desc", page: 1, page_size: 1 });
      const latest = result.tasks?.[0];
      if (!latest?.task_id) return;
      const file = await readWorkflowWorkspaceFile(MARKET_WORKFLOW, latest.task_id, "market/zhihu-ranking.json");
      setSnapshot(JSON.parse(file.content));
      setTask(latest);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取榜单快照失败");
    }
  }, []);

  useEffect(() => { void readLatestSnapshot(); }, [readLatestSnapshot]);

  const refresh = async () => {
    setBusy(true);
    setError("");
    localStorage.setItem("xs2-novel-workspace", workspace);
    try {
      const created = await createTask(MARKET_WORKFLOW, { top_n: "100" }, undefined, undefined, workspace);
      await runTask(MARKET_WORKFLOW, created.task_id);
      let current: MarketTask = null;
      for (let i = 0; i < 30; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const result = await getTask(MARKET_WORKFLOW, created.task_id);
        current = result.task;
        setTask(current);
        if (["completed", "failed", "stopped", "cancelled"].includes(current?.status ?? "")) break;      }
      if (current?.status === "completed") {
        const file = await readWorkflowWorkspaceFile(MARKET_WORKFLOW, created.task_id, "market/zhihu-ranking.json");
        setSnapshot(JSON.parse(file.content));
      } else if (current?.status !== "completed") {
        setError("榜单抓取未在规定时间内完成");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新榜单失败");
    } finally {
      setBusy(false);
    }
  };

  const rankings = useMemo(() => snapshot?.rankings || [], [snapshot]);
  const categories = useMemo(() => Array.from(new Set((snapshot?.works || []).map((work) => work.category).filter(Boolean) as string[])).sort(), [snapshot]);
  const filteredWorks = useMemo(() => (snapshot?.works || []).filter((work) => {
    const text = `${work.title} ${work.summary || ""} ${(work.tags || []).join(" ")}`.toLowerCase();
    return (!ranking || work.ranking_name === ranking) && (!category || work.category === category) && (!query || text.includes(query.toLowerCase()));
  }), [category, query, ranking, snapshot]);
  const topCategories = useMemo(() => {
    const counts = new Map<string, number>();
    filteredWorks.forEach((work) => counts.set(work.category || "未分类", (counts.get(work.category || "未分类") || 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [filteredWorks]);
  const keywordCounts = useMemo(() => {
    const counts = new Map<string, number>();
    const keywords = ["重生", "穿越", "系统", "悬疑", "脑洞", "甜宠", "复仇", "暗恋", "婚姻", "校园", "豪门", "末世"];
    filteredWorks.forEach((work) => keywords.forEach((keyword) => {
      if (`${work.title} ${work.summary || ""} ${(work.tags || []).join(" ")}`.includes(keyword)) counts.set(keyword, (counts.get(keyword) || 0) + 1);
    }));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [filteredWorks]);

  return (
    <div className="h-full overflow-y-auto bg-background px-5 py-6 lg:px-8">
      <div className="mx-auto max-w-[1500px] space-y-6">
        <section className="relative overflow-hidden rounded-3xl border border-warning/20 bg-gradient-to-br from-primary/90 via-secondary to-background p-7 shadow-2xl shadow-warning/20">
          <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-warning/15 blur-3xl" />
          <div className="relative flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl">
              <div className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-warning"><Trophy className="h-4 w-4" /> NOVEL MARKET</div>
              <h2 className="text-3xl font-semibold tracking-tight text-white lg:text-4xl">市场趋势与榜单样本</h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-warning/75">参考你原项目的市场页面，先保存公开榜单快照，再用筛选、题材分布、热门词和作品明细观察创作方向。市场数据只作为参考证据，不会自动改写正文。</p>
            </div>
            <div className="min-w-[310px] rounded-2xl border border-white/10 bg-black/15 p-4 backdrop-blur">
              <label className="mb-2 block text-xs font-medium text-warning/70">当前作品工作区</label>
              <input value={workspace} onChange={(event) => setWorkspace(event.target.value)} className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white outline-none focus:border-warning/60" />
              <button type="button" onClick={refresh} disabled={busy} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-warning px-4 py-2.5 text-sm font-semibold text-warning transition hover:brightness-110 disabled:cursor-wait disabled:opacity-60">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}{busy ? "正在更新榜单" : "更新当前平台"}</button>
            </div>
          </div>
        </section>

        {error && <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
        {!snapshot ? <section className="rounded-2xl border border-dashed border-border bg-card p-10 text-center"><BookOpen className="mx-auto h-8 w-8 text-muted-foreground/60" /><p className="mt-3 text-sm text-muted-foreground">还没有榜单快照，点击“更新当前平台”开始抓取。</p></section> : <>
          <div className="grid gap-4 md:grid-cols-4"><div className="rounded-2xl border border-border bg-card p-5"><p className="text-xs text-muted-foreground">有效作品</p><p className="mt-2 text-3xl font-semibold text-foreground">{snapshot.work_count}</p><p className="mt-1 text-xs text-muted-foreground">当前公开样本</p></div><div className="rounded-2xl border border-border bg-card p-5"><p className="text-xs text-muted-foreground">榜单数量</p><p className="mt-2 text-3xl font-semibold text-foreground">{rankings.length}</p><p className="mt-1 text-xs text-muted-foreground">覆盖推荐、热度等榜单</p></div><div className="rounded-2xl border border-border bg-card p-5"><p className="text-xs text-muted-foreground">题材分类</p><p className="mt-2 text-3xl font-semibold text-foreground">{categories.length}</p><p className="mt-1 text-xs text-muted-foreground">按榜单标签归纳</p></div><div className="rounded-2xl border border-border bg-card p-5"><p className="text-xs text-muted-foreground">最近抓取</p><p className="mt-2 text-base font-semibold text-foreground">{new Date(snapshot.captured_at).toLocaleString()}</p><p className="mt-1 text-xs text-muted-foreground">{task?.task_id || "本地快照"}</p></div></div>

          <section className="rounded-2xl border border-border bg-card p-5"><div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between"><div className="flex items-center gap-2"><Filter className="h-4 w-4 text-primary" /><h3 className="text-base font-semibold text-foreground">榜单筛选</h3></div><div className="grid gap-2 sm:grid-cols-3"><select value={ranking} onChange={(event) => setRanking(event.target.value)} className="rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none"><option value="">全部榜单</option>{rankings.map((item) => <option key={item} value={item}>{item}</option>)}</select><select value={category} onChange={(event) => setCategory(event.target.value)} className="rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none"><option value="">全部分类</option>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select><div className="flex items-center gap-2 rounded-xl border border-border bg-background px-3"><Search className="h-4 w-4 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题、简介、标签" className="min-w-0 bg-transparent py-2 text-sm outline-none" /></div></div></div></section>

          <div className="grid gap-5 xl:grid-cols-[1fr_1fr]"><section className="rounded-2xl border border-border bg-card p-5"><div className="flex items-center gap-2"><BarChart3 className="h-4 w-4 text-primary" /><h3 className="text-base font-semibold text-foreground">分类市场占比</h3></div><div className="mt-5 space-y-3">{topCategories.slice(0, 8).map(([name, count]) => <div key={name}><div className="mb-1 flex justify-between text-xs"><span className="text-foreground">{name}</span><span className="text-muted-foreground">{count} 部</span></div><div className="h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-gradient-to-r from-warning to-warning" style={{ width: `${Math.max(4, (count / Math.max(1, filteredWorks.length)) * 100)}%` }} /></div></div>)}</div></section><section className="rounded-2xl border border-border bg-card p-5"><div className="flex items-center gap-2"><Search className="h-4 w-4 text-primary" /><h3 className="text-base font-semibold text-foreground">热门词</h3></div><div className="mt-5 flex flex-wrap gap-2">{keywordCounts.map(([word, count]) => <button type="button" key={word} onClick={() => setQuery(word)} className="rounded-full border border-border bg-secondary/60 px-3 py-1.5 text-xs text-foreground transition hover:border-primary/50">{word} <span className="ml-1 text-muted-foreground">{count}</span></button>)}{keywordCounts.length === 0 && <span className="text-sm text-muted-foreground">当前筛选下暂无热门词</span>}</div></section></div>

          <section className="rounded-2xl border border-border bg-card p-5"><div className="flex items-center justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Ranking works</p><h3 className="mt-1 text-lg font-semibold text-foreground">榜单作品 · {filteredWorks.length} 条</h3></div><span className="text-xs text-muted-foreground">{snapshot.source_name}</span></div><div className="mt-4 overflow-x-auto"><table className="w-full min-w-[860px] text-left text-sm"><thead className="border-b border-border text-xs text-muted-foreground"><tr><th className="px-3 py-3">榜内排名</th><th className="px-3 py-3">作品</th><th className="px-3 py-3">榜单</th><th className="px-3 py-3">分类</th><th className="px-3 py-3">热度</th><th className="px-3 py-3">详情</th></tr></thead><tbody>{filteredWorks.map((work) => <tr key={`${work.ranking_name}-${work.rank}-${work.platform_work_id}`} className="border-b border-border/60 last:border-0"><td className="px-3 py-3 font-mono text-xs text-warning">#{work.rank}</td><td className="max-w-[360px] px-3 py-3"><p className="font-medium text-foreground">{work.title}</p><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{work.summary || "暂无简介"}</p></td><td className="px-3 py-3 text-xs text-muted-foreground">{work.ranking_name}</td><td className="px-3 py-3 text-xs text-muted-foreground">{work.category || "未分类"}</td><td className="px-3 py-3 text-xs text-muted-foreground">{parseLikes(work.likes)} 赞</td><td className="px-3 py-3">{work.detail_url ? <a href={work.detail_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">打开 <ExternalLink className="h-3 w-3" /></a> : <span className="text-xs text-muted-foreground">—</span>}</td></tr>)}</tbody></table></div></section>
          <p className="text-xs text-muted-foreground">数据边界：{snapshot.boundary}</p>
        </>}
      </div>
    </div>
  );
}
