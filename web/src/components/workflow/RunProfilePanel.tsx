/**
 * RunProfilePanel - 任务运行画像抽屉（R41；R43 加跨 run 对比）
 *
 * 消费 GET /api/workflows/{wf}/tasks/{task}/run-profile（R40 落地），
 * 渲染每阶段尝试/失败/错误分类卡片；支持按 run_id 查任意历史 run
 * （R41 ?run_id=）；打开对比开关后额外请求 ?compare=true（R43）并在每张
 * 阶段卡显示「与上一次 run 对比」列。只读：画像端点不建目录不写状态
 * （B26/B28 静态钉测守卫）。
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, X } from "lucide-react";
import { getTaskRunProfile } from "../../lib/api";
import type { RunProfile, RunProfileComparisonStage, RunProfileStage } from "../../types";
import { formatAttemptTrigger } from "./nodeFailureUtils";
import {
  attemptStatusClass,
  attemptStatusLabel,
  errorClassBadgeClass,
  errorClassLabel,
  failureRateDeltaClass,
  formatCountDelta,
  formatDurationDelta,
  formatDurationSeconds,
  formatFailureRate,
  formatFailureRateDelta,
  formatProfileTime,
  sortedAttempts,
} from "./runProfileView";

export type RunProfileFetcher =
  (workflowId: string, taskId: string, runId?: string, compare?: boolean) => Promise<RunProfile>;

interface RunProfilePanelProps {
  workflowId: string;
  taskId: string;
  open: boolean;
  onClose: () => void;
  /** 测试注入；缺省走 api.getTaskRunProfile */
  fetchProfile?: RunProfileFetcher;
}

const RUN_STATUS_LABELS: Record<string, string> = {
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  stopped: "已停止",
  retry_waiting: "等待重试",
};

const RUN_STATUS_CLASSES: Record<string, string> = {
  running: "bg-info/10 text-info border-info/20",
  completed: "bg-success/10 text-success border-success/20",
  failed: "bg-destructive/10 text-destructive border-destructive/20",
  stopped: "bg-warning/10 text-warning border-warning/20",
  retry_waiting: "bg-warning/10 text-warning border-warning/20",
};

function ErrorClassBadges({ classes }: { classes: Record<string, number> | undefined }) {
  const entries = Object.entries(classes || {});
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([cls, count]) => (
        <span
          key={cls}
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${errorClassBadgeClass(cls)}`}
        >
          {errorClassLabel(cls)} ×{count}
        </span>
      ))}
    </div>
  );
}

function ComparisonLine({ comparison, duplicate }: {
  comparison: RunProfileComparisonStage;
  /** node_id 在本 run 内重复时，对比行是「该节点合计」而非单次执行 */
  duplicate: boolean;
}) {
  const note = duplicate ? "该节点合计" : "对比";
  if (!comparison.comparable) {
    return (
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground"
           aria-label={`阶段 ${comparison.node_id} 对比`}>
        <span className="text-muted-foreground">{note} 不可比（上一次 run 无该阶段尝试）</span>
        <span>上次尝试 {comparison.attempts_previous}</span>
      </div>
    );
  }
  return (
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground"
         aria-label={`阶段 ${comparison.node_id} 对比`}>
      <span>
        {note} 失败率{" "}
        <span className={failureRateDeltaClass(comparison.delta_failure_rate)}>
          {formatFailureRateDelta(comparison.delta_failure_rate)}
        </span>
        （上次 {formatFailureRate(comparison.failure_rate_previous)}）
      </span>
      <span>
        尝试{" "}
        <span className="text-foreground">
          {comparison.delta_attempts === 0 ? "持平" : formatCountDelta(comparison.delta_attempts)}
        </span>
        （上次 {comparison.attempts_previous}）
      </span>
    </div>
  );
}

function StageCard({ stage, ordinal, duplicate, comparison }: {
  stage: RunProfileStage;
  /** 同类节点的出现序号（1 起），仅在 node_id 重复时展示 */
  ordinal: number;
  duplicate: boolean;
  /** 该 node_id 的跨 run 对比（?compare=true 且存在上一次 run 时） */
  comparison?: RunProfileComparisonStage;
}) {
  const attempts = sortedAttempts(stage.attempts_detail);
  return (
    <div className="rounded-xl border border-primary/10 bg-card p-3" data-node-id={stage.node_id}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-foreground font-mono truncate" title={stage.node_id}>
          {stage.node_id}
          {duplicate && (
            <span className="ml-1.5 text-xs font-normal text-muted-foreground">#{ordinal}</span>
          )}
        </span>
        <span className={`text-xs shrink-0 ${stage.failed > 0 ? "text-destructive" : "text-success"}`}>
          失败率 {formatFailureRate(stage.failure_rate)}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>尝试 {stage.attempts}</span>
        <span>成功 {stage.completed}</span>
        <span>失败 {stage.failed}</span>
        {typeof stage.automatic_retry_count === "number" && stage.automatic_retry_count > 0 && (
          <span>自动重试 {stage.automatic_retry_count}</span>
        )}
        <span>阶段耗时 {formatDurationSeconds(stage.duration_seconds)}</span>
      </div>
      {comparison && <ComparisonLine comparison={comparison} duplicate={duplicate} />}
      <div className="mt-2">
        <ErrorClassBadges classes={stage.error_classes} />
      </div>
      {attempts.length > 0 && (
        <details className="mt-2 border-t border-primary/10 pt-2">
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
            尝试记录 ({attempts.length})
          </summary>
          <ol className="mt-2 space-y-2" aria-label={`阶段 ${stage.node_id} 尝试列表`}>
            {attempts.map((attempt, index) => (
              <li
                key={`${stage.node_id}-${attempt.attempt_number ?? index}`}
                className="border-b border-border pb-2 last:border-b-0 last:pb-0"
              >
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-medium text-foreground">
                    第 {attempt.attempt_number ?? index + 1} 次 · {formatAttemptTrigger(attempt.trigger)}
                  </span>
                  <span className={attemptStatusClass(attempt.status)}>
                    {attemptStatusLabel(attempt.status)}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span>耗时 {formatDurationSeconds(attempt.duration_seconds)}</span>
                  {attempt.error_class && (
                    <span className={`rounded-full border px-1.5 ${errorClassBadgeClass(attempt.error_class)}`}>
                      {errorClassLabel(attempt.error_class)}
                    </span>
                  )}
                </div>
                {attempt.error && (
                  <p className="mt-1 text-xs text-destructive whitespace-pre-wrap break-all">{attempt.error}</p>
                )}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

export default function RunProfilePanel({
  workflowId, taskId, open, onClose, fetchProfile,
}: RunProfilePanelProps) {
  const load = fetchProfile ?? getTaskRunProfile;
  const [profile, setProfile] = useState<RunProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [runQuery, setRunQuery] = useState("");
  const [compareEnabled, setCompareEnabled] = useState(false);

  const fetchRun = useCallback(async (runId?: string, compare?: boolean) => {
    setLoading(true);
    setError("");
    try {
      setProfile(await load(workflowId, taskId, runId, compare));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载运行画像失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }, [load, workflowId, taskId]);

  useEffect(() => {
    if (open) void fetchRun();
  }, [open, fetchRun]);

  // 切换对比开关时重新取「当前正在看的那个 run」（不是最新 run）：用户可能在
  // 查历史 run 的过程中打开对比，跳回最新会丢掉他选中的上下文。
  const handleCompareToggle = useCallback((next: boolean) => {
    setCompareEnabled(next);
    void fetchRun(profile?.run_id || undefined, next);
  }, [fetchRun, profile?.run_id]);

  if (!open) return null;

  const totals = profile?.totals;
  const stages = profile?.stages || [];
  const comparison = profile?.comparison || null;
  const statusLabel = RUN_STATUS_LABELS[profile?.status || ""] || profile?.status || "-";
  const statusClass = RUN_STATUS_CLASSES[profile?.status || ""] || "bg-muted text-muted-foreground border-border/20";
  // 同一 node_id 在本 run 可执行多次，对比行按 node_id 汇总（后端同口径）
  const comparisonByNode = new Map<string, RunProfileComparisonStage>(
    (comparison?.stages || []).map((item) => [item.node_id, item]));

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="任务运行画像">
      <div className="absolute inset-0 bg-background/60" onClick={onClose} aria-hidden="true" />
      <div className="absolute inset-y-0 right-0 flex w-[440px] max-w-full flex-col border-l border-primary/10 bg-background shadow-xl">
        <div className="flex items-center justify-between gap-2 border-b border-primary/10 px-4 py-3">
          <h2 className="text-sm font-medium text-foreground">运行画像</h2>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => void fetchRun(runQuery.trim() || undefined, compareEnabled)}
              disabled={loading}
              aria-label="刷新运行画像"
              className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-card transition-colors disabled:opacity-50 cursor-pointer min-h-[36px] min-w-[36px] flex items-center justify-center"
            >
              <RefreshCw size={14} className={loading ? "animate-spin motion-reduce:animate-none" : ""} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭运行画像"
              className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-card transition-colors cursor-pointer min-h-[36px] min-w-[36px] flex items-center justify-center"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="px-4 py-3 border-b border-primary/10 space-y-2">
          <div className="flex items-center gap-2 text-xs">
            <span className="font-mono text-muted-foreground">{profile?.run_id || "-"}</span>
            <span className={`rounded-full border px-2 py-0.5 ${statusClass}`}>{statusLabel}</span>
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>开始 {formatProfileTime(profile?.started_at)}</span>
            <span>结束 {formatProfileTime(profile?.completed_at)}</span>
            <span>总耗时 {formatDurationSeconds(profile?.wall_seconds)}</span>
          </div>
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void fetchRun(runQuery.trim() || undefined, compareEnabled);
            }}
          >
            <input
              type="text"
              value={runQuery}
              onChange={(e) => setRunQuery(e.target.value)}
              placeholder="按 run_id 查历史 run，如 run-99b3bd1b"
              aria-label="按 run_id 查询历史 run"
              className="flex-1 px-3 py-1.5 rounded-lg bg-card border border-primary/10 text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:border-primary/40 transition-colors"
            />
            <button
              type="submit"
              disabled={loading || !runQuery.trim()}
              className="px-3 py-1.5 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer min-h-[36px]"
            >
              查询
            </button>
          </form>
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={compareEnabled}
              onChange={(e) => handleCompareToggle(e.target.checked)}
              aria-label="与上一次 run 对比"
              className="accent-primary cursor-pointer"
            />
            与上一次 run 对比
          </label>
          {error && <p className="text-xs text-destructive break-all" role="alert">{error}</p>}
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3" aria-label="运行画像内容">
          {loading && !profile ? (
            <div className="flex items-center justify-center py-16 text-sm text-muted-foreground" role="status">
              <Loader2 size={18} className="animate-spin motion-reduce:animate-none mr-2" aria-hidden="true" />
              加载运行画像...
            </div>
          ) : !profile ? (
            <p className="py-16 text-center text-sm text-muted-foreground">暂无画像数据</p>
          ) : (
            <>
              <div className="rounded-xl border border-primary/10 bg-card p-3">
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-foreground">
                  <span>阶段 {totals?.stages ?? stages.length}</span>
                  <span>尝试 {totals?.attempts ?? 0}</span>
                  <span className="text-success">成功 {totals?.completed ?? 0}</span>
                  <span className="text-destructive">失败 {totals?.failed ?? 0}</span>
                  <span>总失败率 {formatFailureRate(totals?.failure_rate)}</span>
                </div>
                <div className="mt-2">
                  <ErrorClassBadges classes={totals?.error_classes} />
                </div>
              </div>
              {compareEnabled && (
                comparison ? (
                  <div className="rounded-xl border border-primary/10 bg-card p-3"
                       aria-label="与上一次 run 对比">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-foreground">
                      <span className="font-mono text-muted-foreground">{comparison.previous_run_id}</span>
                      <span>上次 {RUN_STATUS_LABELS[comparison.previous_status] || comparison.previous_status || "-"}</span>
                      <span>总失败率{" "}
                        <span className={failureRateDeltaClass(comparison.totals.delta_failure_rate)}>
                          {formatFailureRateDelta(comparison.totals.delta_failure_rate)}
                        </span>
                      </span>
                      <span>尝试{" "}
                        <span className="text-foreground">
                          {comparison.totals.delta_attempts === 0
                            ? "持平" : formatCountDelta(comparison.totals.delta_attempts)}
                        </span>
                      </span>
                      <span>总耗时{" "}
                        <span className={failureRateDeltaClass(comparison.delta_wall_seconds)}>
                          {formatDurationDelta(comparison.delta_wall_seconds)}
                        </span>
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      差值口径：本次 − 上一次；正值=退步，负值=改善。
                    </p>
                  </div>
                ) : (
                  <p className="rounded-xl border border-primary/10 bg-card p-3 text-xs text-muted-foreground"
                     data-comparison-empty="true">
                    该 run 之前没有更早的 run 记录，无可对比对象。
                  </p>
                )
              )}
              {stages.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">该 run 无阶段执行记录</p>
              ) : (
                stages.map((stage, index) => {
                  // 同一 node_id 可在一个 run 内多次执行（如 agent_deep 循环 N 次），
                  // index+node_id 保证 key 唯一；重复时卡片头标 `#n` 便于逐次区分。
                  const ordinal = stages.slice(0, index + 1)
                    .filter((s) => s.node_id === stage.node_id).length;
                  const duplicate = stages.filter((s) => s.node_id === stage.node_id).length > 1;
                  return (
                    <StageCard
                      key={`${stage.node_id}-${index}`}
                      stage={stage}
                      ordinal={ordinal}
                      duplicate={duplicate}
                      comparison={compareEnabled
                        ? comparisonByNode.get(stage.node_id) : undefined}
                    />
                  );
                })
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
