import { useRef } from "react";
import MarkdownRenderer from "./MarkdownRenderer";
import { archiveLabel, archiveScalar, parseArchiveJSON, readableArchiveMarkdown } from "../lib/novel-archive";

function ArchiveFields({ value, field = "", depth = 0, reference = false }: { value: unknown; field?: string; depth?: number; reference?: boolean }) {
  if (typeof value === "string") {
    if (field === "excerpt" && /[\uE000-\uF8FF]/.test(value)) return <p className="text-sm leading-7 text-muted-foreground">原始引文含特殊字体编码，暂不能按普通文字展示。可阅读对应的分析说明。</p>;
    const embedded = parseArchiveJSON(value);
    if (embedded.parsed && typeof embedded.value === "object") return <ArchiveFields value={embedded.value} field={field} depth={depth} reference={reference} />;
  }
  if (Array.isArray(value)) {
    if (!value.length) return <p className="text-sm text-muted-foreground">暂无信息</p>;
    return <div className="space-y-5">{value.map((item, index) => {
      if (item && typeof item === "object" && !Array.isArray(item)) {
        const record = item as Record<string, unknown>;
        const nameKey = ["name", "title", "character"].find(key => typeof record[key] === "string");
        const name = nameKey ? record[nameKey] as string : `第 ${index + 1} 项`;
        const fields = Object.fromEntries(Object.entries(record).filter(([key]) => key !== nameKey));
        return <article key={index} className={reference ? "rounded-xl bg-secondary/25 p-5" : "border-b border-border/60 pb-5 last:border-0 last:pb-0"}><h4 className="mb-4 text-lg font-semibold text-foreground">{name}</h4><ArchiveFields value={fields} depth={depth + 1} reference={reference} /></article>;
      }
      return <div key={index} className="flex gap-3 text-sm leading-7"><span className="text-primary/70">•</span><div className="min-w-0 flex-1"><ArchiveFields value={item} field={field} depth={depth + 1} reference={reference} /></div></div>;
    })}</div>;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value).filter(([key]) => !["schema", "text_sha256", "source_sha256", "candidates_sha256", "snapshot_path", "source_start", "source_end", "window_id", "covered_window_ids", "candidate_id"].includes(key));
    if (!entries.length) return <p className="text-sm text-muted-foreground">暂无信息</p>;
    return <dl className="space-y-5">{entries.map(([key, item]) => {
      const embedded = typeof item === "string" ? parseArchiveJSON(item) : null;
      const nested = item !== null && typeof item === "object" || embedded?.parsed && typeof embedded.value === "object";
      return <div key={key} className={nested ? "min-w-0" : `grid min-w-0 gap-1 sm:grid-cols-[7.5rem_minmax(0,1fr)] sm:gap-5 ${typeof item === "string" && item.length > 120 ? "sm:!grid-cols-1" : ""}`}>
        <dt className={nested ? `mb-3 font-semibold ${depth === 0 ? "border-b border-border/60 pb-2 text-base text-primary" : "text-sm"}` : `pt-1 text-sm ${reference ? "font-medium text-accent" : "text-muted-foreground"}`}>{archiveLabel(key)}</dt>
        <dd className="min-w-0"><ArchiveFields value={item} field={key} depth={depth + 1} reference={reference} /></dd>
      </div>;
    })}</dl>;
  }
  return <p className="whitespace-pre-wrap break-words text-[15px] leading-8">{archiveScalar(value, field)}</p>;
}

export default function NovelArchiveContent({ content, structured = false, reference = false }: { content: string; structured?: boolean; reference?: boolean }) {
  const readingRef = useRef<HTMLDivElement>(null);
  const parsed = parseArchiveJSON(content);
  if (parsed.parsed) return <ArchiveFields value={parsed.value} reference={reference} />;
  if (structured) return <p role="alert" className="text-sm text-warning">这部分档案格式不完整，暂时无法展示。请检查对应步骤的生成结果。</p>;
  const markdown = readableArchiveMarkdown(content);
  const headings = markdown.split(/\r?\n/).filter(line => /^##\s/.test(line));
  const headingLevel = headings.length >= 2 ? "h2" : "h3";
  const outline = (headings.length >= 2 ? headings : markdown.split(/\r?\n/).filter(line => /^###\s/.test(line))).map(line => line.replace(/^#{2,3}\s+/, "").replace(/[*`]/g, ""));
  return <div ref={readingRef} className="novel-reading min-w-0">
    {content.length > 2500 && outline.length >= 2 && <label className="mb-6 flex flex-wrap items-center gap-3 rounded-lg bg-secondary/30 px-3 py-2 text-xs text-muted-foreground">快速定位<select aria-label="定位档案内容" defaultValue="" onChange={event => { const section = readingRef.current?.querySelectorAll(headingLevel)[Number(event.target.value)]; section?.scrollIntoView({ behavior: "smooth", block: "start" }); }} className="min-w-0 max-w-full rounded-md border border-border bg-card px-2 py-1.5 text-sm text-foreground"><option value="" disabled>选择章节或主题</option>{outline.map((heading, index) => <option key={index} value={index}>{heading}</option>)}</select></label>}
    <MarkdownRenderer content={markdown} className="break-words text-[15px] [&_p]:leading-8 [&_p]:my-4 [&_li]:leading-7 [&_h1]:text-2xl [&_h2]:text-xl [&_h2]:mt-9 [&_h2]:scroll-mt-6 [&_h3]:text-lg [&_h3]:mt-7 [&_h3]:scroll-mt-6 [&_h4]:text-base [&_table]:block [&_table]:overflow-x-auto [&_td]:min-w-[8rem] [&_td]:align-top [&_th]:whitespace-nowrap" />
  </div>;
}
