/**
 * 运行画像的展示映射（R41）——纯函数，供 RunProfilePanel 与测试共用。
 *
 * 错误分类是后端 run_profile.py 的关键词启发式（R40 六桶），此处只做
 * 展示映射（文案/徽章色），不构成失败原因判定。
 */
import type { RunProfileAttemptDetail } from "../../types";

export const ERROR_CLASS_LABELS: Record<string, string> = {
  http_5xx: "HTTP 5xx",
  timeout: "超时",
  stream_stall: "流式停摆",
  connection: "连接错误",
  other: "其他",
};

export const ERROR_CLASS_BADGE_CLASSES: Record<string, string> = {
  http_5xx: "bg-destructive/10 text-destructive border-destructive/20",
  timeout: "bg-destructive/10 text-destructive border-destructive/20",
  stream_stall: "bg-warning/10 text-warning border-warning/20",
  connection: "bg-warning/10 text-warning border-warning/20",
  other: "bg-muted text-muted-foreground border-border/30",
};

/** 尝试状态 → 文案（与 NodeFailureRuntimePanel 同款语义） */
export const ATTEMPT_STATUS_LABELS: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  retry_waiting: "等待重试",
  completed: "成功",
  success: "成功",
  failed: "失败",
  failure: "失败",
  skipped: "已跳过",
};

export const ATTEMPT_STATUS_CLASSES: Record<string, string> = {
  completed: "text-success",
  success: "text-success",
  running: "text-info",
  retry_waiting: "text-warning",
  failed: "text-destructive",
  failure: "text-destructive",
  skipped: "text-muted-foreground",
};

export function attemptStatusLabel(status: string | undefined): string {
  return ATTEMPT_STATUS_LABELS[status || ""] || status || "未知";
}

export function attemptStatusClass(status: string | undefined): string {
  return ATTEMPT_STATUS_CLASSES[status || ""] || "text-muted-foreground";
}

export function errorClassLabel(errorClass: string | undefined): string {
  return ERROR_CLASS_LABELS[errorClass || ""] || errorClass || "";
}

export function errorClassBadgeClass(errorClass: string | undefined): string {
  return ERROR_CLASS_BADGE_CLASSES[errorClass || ""] || ERROR_CLASS_BADGE_CLASSES.other;
}

/** 0.6 → "60%"；null/非有限数 → "-"（无尝试的空 run） */
export function formatFailureRate(rate: number | null | undefined): string {
  if (rate == null || !Number.isFinite(rate)) return "-";
  return `${Math.round(rate * 100)}%`;
}

/** 秒数 → 人话时长；null → "-"。B31 前的旧 run wall_seconds 为 null。 */
export function formatDurationSeconds(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "-";
  if (seconds < 1) return `${seconds} 秒`;
  if (seconds < 60) return `${Math.round(seconds)} 秒`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes} 分 ${remainder} 秒`;
  return `${Math.floor(minutes / 60)} 时 ${minutes % 60} 分`;
}

export function formatProfileTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString("zh-CN");
}

/** 尝试明细按 attempt_number 升序（后端已按执行顺序，这里只做数值容错） */
export function sortedAttempts(attempts: RunProfileAttemptDetail[] | undefined): RunProfileAttemptDetail[] {
  if (!Array.isArray(attempts)) return [];
  return [...attempts].sort(
    (a, b) => (a.attempt_number ?? Number.MAX_SAFE_INTEGER) - (b.attempt_number ?? Number.MAX_SAFE_INTEGER),
  );
}

/** 失败率差值 → "+17%" / "-17%" / "持平"；null（不可比或无数据）→ "-"。
 *  差值语义来自后端：current - previous，正值=退步、负值=改善。 */
export function formatFailureRateDelta(delta: number | null | undefined): string {
  if (delta == null || !Number.isFinite(delta)) return "-";
  const pct = Math.round(delta * 100);
  if (pct === 0) return "持平";
  return `${pct > 0 ? "+" : ""}${pct}%`;
}

/** 差值色调：退步红、改善绿、持平/不可比中性（不是失败原因判定，只是排序视觉）。 */
export function failureRateDeltaClass(delta: number | null | undefined): string {
  if (delta == null || !Number.isFinite(delta) || Math.round(delta * 100) === 0) {
    return "text-muted-foreground";
  }
  return delta > 0 ? "text-destructive" : "text-success";
}

/** 整数差值（尝试数/失败数）→ "+3" / "-2" / "0"；null → "-" */
export function formatCountDelta(delta: number | null | undefined): string {
  if (delta == null || !Number.isFinite(delta)) return "-";
  if (delta === 0) return "0";
  return `${delta > 0 ? "+" : ""}${delta}`;
}

/** 秒数差值 → "+10 分 0 秒" / "-30 秒" / "持平"；null → "-" */
export function formatDurationDelta(delta: number | null | undefined): string {
  if (delta == null || !Number.isFinite(delta)) return "-";
  if (delta === 0) return "持平";
  const magnitude = formatDurationSeconds(Math.abs(delta));
  return `${delta > 0 ? "+" : "-"}${magnitude}`;
}
