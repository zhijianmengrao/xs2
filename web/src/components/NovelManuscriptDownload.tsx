import { useRef, useState } from "react";
import { Download } from "lucide-react";

export default function NovelManuscriptDownload({ title, workspace, previous = false }: { title: string; workspace: string; previous?: boolean }) {
  const guard = useRef(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const download = async () => {
    if (guard.current) return;
    guard.current = true; setBusy(true); setFeedback("正在准备下载…");
    try {
      const filename = `${title.replace(/[<>:"/\\|?*]/g, "_") || "小说成品"}.md`;
      const query = new URLSearchParams({ workflow_id: "xs2-novel-flywheel-export", workspace, filename });
      const url = `/api/novel-console/export/download?${query}`;
      const response = await fetch(url, { method: "HEAD" });
      if (!response.ok) throw new Error(response.status === 404 ? "尚未生成成品，请先完成导出。" : `下载失败（${response.status}），请重试。`);
      const link = document.createElement("a"); link.href = url; link.download = filename;
      document.body.appendChild(link); link.click(); link.remove();
      setFeedback(`已发起下载：${filename}。请在浏览器下载列表查看。`);
    } catch (failure) { setFeedback(failure instanceof Error ? failure.message : "下载失败，请重试。"); }
    finally { guard.current = false; setBusy(false); }
  };
  return <div className="mt-4"><button disabled={busy} onClick={() => void download()} className="flex items-center gap-2 rounded-xl border border-success/40 px-4 py-2.5 text-sm font-medium text-success disabled:opacity-60"><Download className="h-4 w-4" />{busy ? "正在准备下载…" : previous ? "下载上次导出" : "下载小说成品"}</button>{feedback && <p role="status" className="mt-2 text-xs leading-6 text-muted-foreground">{feedback}</p>}</div>;
}
