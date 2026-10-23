import { createContext, useContext, useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { SlidersHorizontal } from "lucide-react";
import { defaultNovelPreferences, effectiveNovelMotion, normalizeNovelPreferences, NOVEL_UI_KEY, readNovelPreferences, type NovelPreferences } from "../lib/novel-workbench-preferences";

const Context = createContext({ preferences: defaultNovelPreferences, reduced: false, update: (patch: Partial<NovelPreferences>) => { void patch; } });
export function useNovelPreferences() { return useContext(Context); }
export function NovelWorkbenchProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState(() => readNovelPreferences(localStorage));
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => { const query = window.matchMedia("(prefers-reduced-motion: reduce)"); const change = () => setReduced(query.matches); query.addEventListener("change", change); return () => query.removeEventListener("change", change); }, []);
  useEffect(() => { try { localStorage.setItem(NOVEL_UI_KEY, JSON.stringify(preferences)); } catch { /* Preferences still apply in this session. */ } }, [preferences]);
  return <Context.Provider value={{ preferences, reduced, update: patch => setPreferences(current => normalizeNovelPreferences({ ...current, ...patch })) }}>{children}</Context.Provider>;
}

export function NovelWorkbenchSurface({ children }: { children: ReactNode }) {
  const { preferences, reduced } = useNovelPreferences();
  return <div className="novel-workbench h-full overflow-hidden bg-background text-foreground" data-novel-theme={preferences.theme} data-motion={effectiveNovelMotion(preferences.motion, reduced)} style={{ "--novel-font-size": `${preferences.fontSize}px`, "--novel-line-height": preferences.lineHeight, "--novel-reading-width": `${preferences.readingWidth}ch` } as CSSProperties}>{children}</div>;
}

export function NovelDisplaySettings() {
  const { preferences, reduced, update } = useNovelPreferences();
  return <details className="novel-display-settings relative"><summary title="调整工作台显示" className="flex cursor-pointer list-none items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs hover:bg-secondary"><SlidersHorizontal className="h-4 w-4" /><span className="hidden sm:inline">显示设置</span></summary><div className="absolute right-0 top-full z-40 mt-2 w-[min(310px,90vw)] space-y-4 rounded-xl border border-border bg-card p-4 shadow-2xl"><p className="text-sm font-semibold">工作台显示</p><label className="block text-xs">主题<select aria-label="工作台主题" value={preferences.theme} onChange={event => update({ theme: event.target.value as NovelPreferences["theme"] })} className="mt-2 w-full rounded-lg border border-border bg-background p-2 text-sm"><option value="eva">初号机 · 紫绿</option><option value="quiet">专注 · 深色</option><option value="paper">阅读 · 浅色</option></select></label><label className="block text-xs">动态效果<select aria-label="工作台动态效果" value={preferences.motion} onChange={event => update({ motion: event.target.value as NovelPreferences["motion"] })} className="mt-2 w-full rounded-lg border border-border bg-background p-2 text-sm"><option value="off">关闭</option><option value="light">轻量（默认）</option><option value="full">完整</option></select></label><p className="text-xs leading-6 text-muted-foreground">仅影响小说工作台，偏好会保存在本设备。{reduced ? "系统已开启减少动态效果，本页当前关闭动画。" : "动画只提示当前操作和任务状态。"}</p></div></details>;
}

export function NovelReadingSettings() {
  const { preferences, update } = useNovelPreferences();
  const control = "rounded-lg border border-border bg-background px-2 py-1.5 text-xs";
  return <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-border px-5 py-3 text-xs text-muted-foreground" aria-label="阅读设置">
    <label className="flex items-center gap-2">字号<select aria-label="阅读字号" value={preferences.fontSize} onChange={event => update({ fontSize: Number(event.target.value) })} className={control}>{[16,17,18,20,22].map(size => <option key={size} value={size}>{size}</option>)}</select></label>
    <label className="flex items-center gap-2">行距<select aria-label="阅读行距" value={preferences.lineHeight} onChange={event => update({ lineHeight: Number(event.target.value) })} className={control}>{[1.7,1.9,2.1,2.3].map(size => <option key={size} value={size}>{size}</option>)}</select></label>
    <label className="flex items-center gap-2">栏宽<select aria-label="阅读栏宽" value={preferences.readingWidth} onChange={event => update({ readingWidth: Number(event.target.value) })} className={control}><option value={62}>窄</option><option value={76}>标准</option><option value={94}>宽</option></select></label><span className="ml-auto">阅读偏好自动记忆</span>
  </div>;
}

export function NovelUnitMotif() {
  return <div className="novel-unit-motif" aria-hidden="true"><svg viewBox="0 0 170 205" fill="none"><path d="M75 28 83 3 93 28 121 44 133 88 111 119 119 166 147 192 94 187 80 204 62 185 21 192 48 164 49 119 31 89 45 45Z" /><path d="m45 45 37 39 39-40M49 119l32 17 30-17M48 164l33-28 38 30M31 89l50 16 52-17M82 3v81M62 185l19-49 13 51" /><path className="novel-motif-accent" d="m56 90 17 6m15 0 19-6M80 106v17" /></svg><span>UNIT 01</span></div>;
}
