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

/** 阶段变化方向（R47 对比视图演进）。
 *  regressed = 失败率变高；improved = 变低；flat = 有可比数据但没变；
 *  incomparable = 任一侧无尝试（「无数据」不等于 0%，单列一档不混入 flat）。 */
export type StageChange = "regressed" | "improved" | "flat" | "incomparable";

export function stageChangeOf(delta: number | null | undefined, comparable: boolean): StageChange {
  if (!comparable || delta == null || !Number.isFinite(delta)) return "incomparable";
  const pct = Math.round(delta * 100);
  if (pct > 0) return "regressed";
  if (pct < 0) return "improved";
  return "flat";
}

export const STAGE_CHANGE_LABELS: Record<StageChange, string> = {
  regressed: "退步",
  improved: "改善",
  flat: "持平",
  incomparable: "不可比",
};

/** 分组顺序：先看退步（最需要行动），再看改善，最后持平/不可比。 */
const STAGE_CHANGE_ORDER: StageChange[] = ["regressed", "improved", "flat", "incomparable"];

export interface StageChangeSummary {
  counts: Record<StageChange, number>;
  /** 有变化的阶段 node_id（退步在前、改善次之），供「只看变化」过滤 */
  changedNodeIds: string[];
  total: number;
}

/** 把逐阶段对比汇成一句话的摘要（纯函数，供顶部块与测试共用）。 */
export function summarizeStageChanges(
  stages: Array<{ node_id: string; delta_failure_rate?: number | null; comparable: boolean }> | undefined,
): StageChangeSummary {
  const counts: Record<StageChange, number> = {
    regressed: 0, improved: 0, flat: 0, incomparable: 0,
  };
  const changedNodeIds: string[] = [];
  const list = Array.isArray(stages) ? stages : [];

  for (const stage of list) {
    const change = stageChangeOf(stage.delta_failure_rate, stage.comparable);
    counts[change] += 1;
    if (change === "regressed" || change === "improved") changedNodeIds.push(stage.node_id);
  }
  // 变化列表按方向排序（退步在前），同方向内保持后端给的顺序（已按失败数降序）
  const ordered = STAGE_CHANGE_ORDER.flatMap((change) =>
    change === "regressed" || change === "improved"
      ? list.filter((s) => stageChangeOf(s.delta_failure_rate, s.comparable) === change)
        .map((s) => s.node_id)
      : [],
  );
  return { counts, changedNodeIds: ordered.length ? ordered : changedNodeIds, total: list.length };
}

/** 摘要一句话：只列非零档，全零时明说「无阶段变化」。 */
export function describeStageChanges(summary: StageChangeSummary): string {
  const parts = STAGE_CHANGE_ORDER
    .filter((change) => summary.counts[change] > 0)
    .map((change) => `${STAGE_CHANGE_LABELS[change]} ${summary.counts[change]}`);
  if (parts.length === 0) return "无阶段变化";
  return parts.join(" · ");
}

/** 趋势文案（R50 抽屉 + R51 列表徽章共用一处，避免两处漂移）。
 *
 *  `insufficient` 自成一档：「没有足够历史」不等于「稳定」，混进 stable
 *  会把「判不了」显示成「没问题」。 */
export const TREND_LABELS: Record<string, string> = {
  regressing: "连续退步",
  improving: "连续改善",
  stable: "有涨有跌 / 持平",
  insufficient: "历史不足",
};

export const TREND_CLASSES: Record<string, string> = {
  regressing: "bg-destructive/10 text-destructive border-destructive/20",
  improving: "bg-success/10 text-success border-success/20",
  stable: "bg-muted text-muted-foreground border-border/20",
  insufficient: "bg-muted text-muted-foreground border-border/20",
};

export function trendLabel(trend: string | undefined): string {
  return TREND_LABELS[trend || ""] || trend || "";
}

export function trendClass(trend: string | undefined): string {
  return TREND_CLASSES[trend || ""] || TREND_CLASSES.insufficient;
}

/** 列表徽章要不要显示：只有「连续退步」值得在列表里警示。
 *
 *  为什么不在列表上显示 improving/stable：列表是扫描界面，每个任务都挂一个
 *  「稳定」徽章只是噪声。真正需要一眼看到的是「这个 workflow 在持续变坏」。
 *  insufficient 同理不显示——它是「判不了」，不是结论。 */
export function shouldFlagTrend(trend: string | undefined): boolean {
  return trend === "regressing";
}
