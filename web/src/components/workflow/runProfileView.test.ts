import assert from "node:assert/strict";
import test from "node:test";

import {
  attemptStatusLabel,
  attemptStatusClass,
  errorClassLabel,
  formatDurationSeconds,
  formatFailureRate,
  sortedAttempts,
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
