/**
 * 人味工具（score-content / check-dialogue / score-chapter）历史记录持久化
 *
 * 设计（R32 收官轮，最小实现）：
 * - 存储：localStorage（纯前端、零后端改动、随浏览器留存）；
 *   读写全部 try/catch——隐私模式/配额/禁用存储时静默降级为无历史，不影响主功能。
 * - 作用域：按工作区 key 隔离（determinflow.humanware.history.<workspaceKey>）。
 * - 容量：最多 MAX_ENTRIES 条，超出丢弃最旧（append 后截尾）。
 */

export interface ScoreHistoryEntry {
  kind: 'score';
  ts: number;
  character: string;
  excerpt: string;
  totalScore: number;
  grade: string;
}

export interface CheckHistoryEntry {
  kind: 'check';
  ts: number;
  character: string;
  excerpt: string;
  matches: boolean;
  violationCount: number;
}

export interface ChapterScoreHistoryEntry {
  kind: 'chapter';
  ts: number;
  chapter: string;
  totalScore: number;
  grade: string;
  dialogues: number;
}

export type HumanwareHistoryEntry =
  | ScoreHistoryEntry
  | CheckHistoryEntry
  | ChapterScoreHistoryEntry;

const PREFIX = 'determinflow.humanware.history.';
export const MAX_ENTRIES = 20;

export function humanwareHistoryKey(workspaceKey: string): string {
  return `${PREFIX}${workspaceKey}`;
}

function safeStorage(): Storage | null {
  try {
    const storage = globalThis.localStorage;
    // 访问 localStorage 本身可能在受限环境抛异常；再探测一次 setItem 可写性
    const probe = `${PREFIX}probe`;
    storage.setItem(probe, '1');
    storage.removeItem(probe);
    return storage;
  } catch {
    return null;
  }
}

export function loadHumanwareHistory(workspaceKey: string): HumanwareHistoryEntry[] {
  const storage = safeStorage();
  if (!storage) return [];
  try {
    const raw = storage.getItem(humanwareHistoryKey(workspaceKey));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is HumanwareHistoryEntry =>
      typeof item === 'object' && item !== null && 'kind' in item && 'ts' in item);
  } catch {
    return [];
  }
}

export function appendHumanwareHistory(
  workspaceKey: string,
  entry: HumanwareHistoryEntry,
): HumanwareHistoryEntry[] {
  const next = [entry, ...loadHumanwareHistory(workspaceKey)].slice(0, MAX_ENTRIES);
  const storage = safeStorage();
  if (storage) {
    try {
      storage.setItem(humanwareHistoryKey(workspaceKey), JSON.stringify(next));
    } catch {
      // 写失败（配额等）静默丢弃，内存返回值仍可用于本次渲染
    }
  }
  return next;
}

export function clearHumanwareHistory(workspaceKey: string): void {
  const storage = safeStorage();
  if (!storage) return;
  try {
    storage.removeItem(humanwareHistoryKey(workspaceKey));
  } catch {
    // 忽略
  }
}

export function formatHistoryTime(ts: number): string {
  const date = new Date(ts);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
