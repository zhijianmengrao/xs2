import assert from "node:assert/strict";
import test from "node:test";

import {
  attemptStatusLabel,
  attemptStatusClass,
  errorClassLabel,
  failureRateDeltaClass,
  formatCountDelta,
  formatDurationDelta,
  formatDurationSeconds,
  formatFailureRate,
  formatFailureRateDelta,
  describeStageChanges,
  sortedAttempts,
  stageChangeOf,
  summarizeStageChanges,
} from "./runProfileView";
import type { RunProfileAttemptDetail } from "../../types";

test("error class labels cover the R40 six buckets", () => {
  assert.equal(errorClassLabel("http_5xx"), "HTTP 5xx");
  assert.equal(errorClassLabel("timeout"), "超时");
  assert.equal(errorClassLabel("stream_stall"), "流式停摆");
  assert.equal(errorClassLabel("connection"), "连接错误");
  assert.equal(errorClassLabel("other"), "其他");
  assert.equal(errorClassLabel("mystery_bucket"), "mystery_bucket");
  assert.equal(errorClassLabel(""), "");
});

test("attempt status labels align with NodeFailureRuntimePanel semantics", () => {
  assert.equal(attemptStatusLabel("completed"), "成功");
  assert.equal(attemptStatusLabel("failed"), "失败");
  assert.equal(attemptStatusLabel("retry_waiting"), "等待重试");
  assert.equal(attemptStatusClass("failed"), "text-destructive");
  assert.equal(attemptStatusClass("completed"), "text-success");
  assert.equal(attemptStatusClass(undefined), "text-muted-foreground");
});

test("failure rate formatting: null is dash, 0 is 0%", () => {
  assert.equal(formatFailureRate(null), "-");
  assert.equal(formatFailureRate(undefined), "-");
  assert.equal(formatFailureRate(0), "0%");
  assert.equal(formatFailureRate(0.6), "60%");
  assert.equal(formatFailureRate(1), "100%");
  assert.equal(formatFailureRate(Number.NaN), "-");
});

test("duration formatting: sub-second keeps precision, null is dash", () => {
  assert.equal(formatDurationSeconds(0.071), "0.071 秒");
  assert.equal(formatDurationSeconds(59.4), "59 秒");
  assert.equal(formatDurationSeconds(600), "10 分 0 秒");
  assert.equal(formatDurationSeconds(7265), "2 时 1 分");
  assert.equal(formatDurationSeconds(null), "-");
  assert.equal(formatDurationSeconds(Number.NaN), "-");
});

test("sortedAttempts tolerates missing numbers and keeps numeric order", () => {
  assert.deepEqual(
    sortedAttempts([
      { attempt_number: 3, status: "completed" },
      { attempt_number: 1, status: "failed" },
      { status: "failed" },
      { attempt_number: 2, status: "failed" },
    ]).map((a) => a.attempt_number),
    [1, 2, 3, undefined],
  );
  assert.deepEqual(sortedAttempts(undefined), []);
  assert.deepEqual(
    sortedAttempts("garbage" as unknown as RunProfileAttemptDetail[]),
    [],
  );
});

test("failure rate delta keeps sign, rounds to whole percent, and marks ties", () => {
  assert.equal(formatFailureRateDelta(0.17), "+17%");
  assert.equal(formatFailureRateDelta(-0.17), "-17%");
  assert.equal(formatFailureRateDelta(0), "持平");
  assert.equal(formatFailureRateDelta(0.0001), "持平");  // 舍入后为 0 → 持平
  assert.equal(formatFailureRateDelta(null), "-");
  assert.equal(formatFailureRateDelta(undefined), "-");
  assert.equal(formatFailureRateDelta(Number.NaN), "-");
  // 差值语义：正=退步（红）、负=改善（绿）、持平/无数据中性
  assert.equal(failureRateDeltaClass(0.17), "text-destructive");
  assert.equal(failureRateDeltaClass(-0.17), "text-success");
  assert.equal(failureRateDeltaClass(0), "text-muted-foreground");
  assert.equal(failureRateDeltaClass(null), "text-muted-foreground");
});

test("count delta and duration delta show explicit signs", () => {
  assert.equal(formatCountDelta(3), "+3");
  assert.equal(formatCountDelta(-2), "-2");
  assert.equal(formatCountDelta(0), "0");
  assert.equal(formatCountDelta(null), "-");
  assert.equal(formatDurationDelta(600), "+10 分 0 秒");
  assert.equal(formatDurationDelta(-30), "-30 秒");
  assert.equal(formatDurationDelta(0), "持平");
  assert.equal(formatDurationDelta(null), "-");
});

// ---------- R47 对比视图演进：阶段变化分档 ----------

test("stage change buckets never fake data for incomparable stages", () => {
  assert.equal(stageChangeOf(0.17, true), "regressed");
  assert.equal(stageChangeOf(-0.17, true), "improved");
  assert.equal(stageChangeOf(0, true), "flat");
  // 任一侧无尝试 → 不可比，绝不混进「持平」（持平意味着「比过且没变」）
  assert.equal(stageChangeOf(null, false), "incomparable");
  assert.equal(stageChangeOf(0.2, false), "incomparable");
  assert.equal(stageChangeOf(NaN, true), "incomparable");
  // 四舍五入后为 0 的小差值算持平（展示层与 formatFailureRateDelta 同口径）
  assert.equal(stageChangeOf(0.004, true), "flat");
});

test("change summary orders regressions first and counts every bucket", () => {
  const summary = summarizeStageChanges([
    { node_id: "a", delta_failure_rate: 0.2, comparable: true },
    { node_id: "b", delta_failure_rate: -0.1, comparable: true },
    { node_id: "c", delta_failure_rate: 0, comparable: true },
    { node_id: "d", delta_failure_rate: null, comparable: false },
    { node_id: "e", delta_failure_rate: 0.05, comparable: true },
  ]);
  assert.deepEqual(summary.counts,
    { regressed: 2, improved: 1, flat: 1, incomparable: 1 });
  assert.equal(summary.total, 5);
  // 退步在前（最需要行动），改善次之
  assert.deepEqual(summary.changedNodeIds, ["a", "e", "b"]);
});

test("change summary tolerates missing stages and reports no-change honestly", () => {
  const empty = summarizeStageChanges(undefined);
  assert.equal(empty.total, 0);
  assert.equal(describeStageChanges(empty), "无阶段变化");

  const flat = summarizeStageChanges([
    { node_id: "a", delta_failure_rate: 0, comparable: true },
  ]);
  assert.deepEqual(flat.changedNodeIds, []);
  assert.equal(describeStageChanges(flat), "持平 1");
});

test("describeStageChanges lists only non-zero buckets", () => {
  const summary = summarizeStageChanges([
    { node_id: "a", delta_failure_rate: 0.2, comparable: true },
    { node_id: "b", delta_failure_rate: -0.1, comparable: true },
  ]);
  assert.equal(describeStageChanges(summary), "退步 1 · 改善 1");
});
