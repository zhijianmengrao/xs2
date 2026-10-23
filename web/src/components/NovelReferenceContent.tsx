import { useState } from "react";
import { archiveLabel, archiveScalar, parseArchiveJSON, readableArchiveMarkdown } from "../lib/novel-archive";
import NovelArchiveContent from "./NovelArchiveContent";

/** Format existing Markdown records without changing or summarizing their text. */
function ReferenceBody({ content }: { content: string }) {
  const blocks: Array<{ label?: string; body: string }> = [];
  for (const line of content.split(/\r?\n/)) {
    const field = line.match(/^\s*-\s+([^：:]{1,36})[：:]\s*(.*)$/);
    if (field) blocks.push({ label: field[1].replace(/[*`]/g, '').trim(), body: field[2] });
    else if (blocks.length && blocks[blocks.length - 1].label && line.trim() && !/^[-*>#]/.test(line)) blocks[blocks.length - 1].body += "\n" + line;
    else if (blocks.length && !blocks[blocks.length - 1].label) blocks[blocks.length - 1].body += "\n" + line;
    else blocks.push({ body: line });
  }
  return <div className="space-y-4">{blocks.filter(block => block.body.trim()).map((block, index) => block.label ? <div key={index} className={`grid gap-1.5 sm:grid-cols-[7rem_minmax(0,1fr)] sm:gap-5 ${block.body.length > 120 ? "sm:!grid-cols-1" : ""}`}>
    <p className="pt-1 text-sm font-medium text-accent">{archiveLabel(block.label)}</p>
    <div className="min-w-0"><NovelArchiveContent content={archiveScalar(block.body, block.label)} /></div>
  </div> : <NovelArchiveContent key={index} content={block.body} />)}</div>;
}

export default function NovelReferenceContent({ content }: { content: string }) {
  const [selected, setSelected] = useState(0);
  if (parseArchiveJSON(content).parsed) return <NovelArchiveContent content={content} reference />;
  const markdown = readableArchiveMarkdown(content);
  const parts = markdown.split(/^##\s+(.+)\s*$/m);
  const records = parts.length > 2 ? Array.from({ length: (parts.length - 1) / 2 }, (_, index) => ({ title: parts[index * 2 + 1], body: parts[index * 2 + 2] })) : [{ title: "", body: markdown }];
  const record = records[selected] || records[0];
  const sections = record.body.split(/^(#{3,4})\s+(.+)\s*$/m);
  return <div className="min-w-0 space-y-6">
    {records.length > 1 && <label className="flex flex-wrap items-center gap-3 border-b border-border/60 pb-4 text-sm text-muted-foreground">查看条目<select aria-label="选择档案条目" value={selected} onChange={event => setSelected(Number(event.target.value))} className="max-w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground">{records.map((item, index) => <option key={index} value={index}>{item.title}</option>)}</select><span className="text-xs">共 {records.length} 项</span></label>}
    {record.title && <h2 className="text-xl font-semibold leading-8">{record.title}</h2>}
    <ReferenceBody content={sections[0]} />
    {Array.from({ length: (sections.length - 1) / 3 }, (_, index) => {
      const depth = sections[index * 3 + 1];
      return <section key={index} className={depth === "###" ? "border-t border-border/60 pt-6" : "rounded-xl bg-secondary/25 px-4 py-4 sm:px-5"}><h3 className={`mb-4 font-semibold ${depth === "###" ? "text-base text-foreground" : "text-sm text-primary"}`}>{sections[index * 3 + 2]}</h3><ReferenceBody content={sections[index * 3 + 3]} /></section>;
    })}
  </div>;
}
