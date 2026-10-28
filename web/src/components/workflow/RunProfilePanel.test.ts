import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { Window } from "happy-dom";

const dom = new Window({ url: "http://localhost/" });
for (const name of ["window", "document", "Node", "Text", "HTMLElement", "Element", "Event", "MouseEvent", "navigator", "sessionStorage"]) {
  Object.defineProperty(globalThis, name, { configurable: true, value: name === "window" ? dom : dom[name as keyof Window] });
}
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const React = await import("react");
const { act } = React;
Object.assign(globalThis, { React });
const { createRoot } = await import("react-dom/client");
const { default: RunProfilePanel } = await import("./RunProfilePanel");
import type { RunProfile } from "../../types";

let root: ReturnType<typeof createRoot> | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  document.body.replaceChildren();
});
after(async () => dom.happyDOM.abort());

async function render(element: ReturnType<typeof React.createElement>) {
  root = createRoot(document.body.appendChild(document.createElement("div")));
  await act(async () => root?.render(element));
}

function bodyText() { return document.body.textContent || ""; }

/** R38 实跑重试形态（画像验收基准）：build 2 次尝试（超时→成功）、
 *  character 3 次（530/524/成功）——与后端 test_run_profile.py 同源。 */
const r38ShapeProfile: RunProfile = {
  run_id: "run-99b3bd1b",
  workflow_id: "wf-x",
  status: "completed",
  started_at: "2026-10-27T10:00:00+08:00",
  completed_at: "2026-10-27T12:00:00+08:00",
  wall_seconds: 7200,
  totals: {
    stages: 2, attempts: 5, completed: 2, failed: 3, failure_rate: 0.6,
    stages_with_multiple_attempts: ["build", "character"],
    stages_with_failures: ["build", "character"],
    error_classes: { timeout: 1, http_5xx: 2 },
  },
  stages: [
    {
      node_id: "build", attempts: 2, completed: 1, failed: 1, failure_rate: 0.5,
      automatic_retry_count: 1, output_repair_count: 0,
      duration_seconds: 3000, error_classes: { timeout: 1 },
      attempts_detail: [
        { attempt_number: 1, trigger: "initial", status: "failed",
          error: "stream chunk timed out after 600s", error_class: "timeout",
          duration_seconds: 600 },
        { attempt_number: 2, trigger: "automatic_retry", status: "completed",
          error: "", error_class: "", duration_seconds: 2400 },
      ],
    },
    {
      node_id: "character", attempts: 3, completed: 1, failed: 2, failure_rate: 0.6667,
      automatic_retry_count: 2, output_repair_count: 0,
      duration_seconds: 600, error_classes: { http_5xx: 2 },
      attempts_detail: [
        { attempt_number: 1, trigger: "initial", status: "failed",
          error: "provider returned HTTP 530", error_class: "http_5xx",
          duration_seconds: 120 },
        { attempt_number: 2, trigger: "automatic_retry", status: "failed",
          error: "HTTP 524 upstream timeout", error_class: "http_5xx",
          duration_seconds: 120 },
        { attempt_number: 3, trigger: "automatic_retry", status: "completed",
          error: "", error_class: "", duration_seconds: 360 },
      ],
    },
  ],
};

test("closed panel renders nothing", async () => {
  await render(React.createElement(RunProfilePanel, {
    workflowId: "wf-x", taskId: "task-1", open: false, onClose: () => {},
    fetchProfile: async () => r38ShapeProfile,
  }));
  assert.equal(document.querySelector('[aria-label="任务运行画像"]'), null);
});

test("renders R38 retry shape: totals, per-stage cards, attempt details, error classes", async () => {
  await render(React.createElement(RunProfilePanel, {
    workflowId: "wf-x", taskId: "task-1", open: true, onClose: () => {},
    fetchProfile: async () => r38ShapeProfile,
  }));
  const text = bodyText();
  assert.ok(text.includes("run-99b3bd1b"), "run id shown");
  assert.ok(text.includes("已完成"), "run status shown");
  assert.ok(text.includes("2 时 0 分"), "wall seconds humanized");
  assert.ok(text.includes("总失败率 60%"), "total failure rate shown");
  assert.ok(text.includes("HTTP 5xx ×2"), "aggregated error classes shown");
  assert.ok(text.includes("超时 ×1"), "timeout class shown");
  const stageCards = document.querySelectorAll("[data-node-id]");
  assert.equal(stageCards.length, 2, "one card per stage");
  assert.ok(text.includes("失败率 50%"), "build stage failure rate");
  // 尝试记录默认折叠，展开 build 卡片的 details 后逐尝试明细可见
  const details = stageCards[0].querySelector("details");
  assert.ok(details, "attempt history collapsed by default");
  details!.open = true;
  await act(async () => { /* let DOM update */ });
  const buildText = stageCards[0].textContent || "";
  assert.ok(buildText.includes("第 1 次 · 首次执行"), "attempt trigger label");
  assert.ok(buildText.includes("stream chunk timed out after 600s"), "attempt error text");
  assert.ok(buildText.includes("超时"), "attempt error class badge");
  assert.ok(buildText.includes("10 分 0 秒"), "attempt duration humanized");
});

test("fetch failure surfaces human-readable message (B17 同族：FastAPI detail 已人因化)", async () => {
  await render(React.createElement(RunProfilePanel, {
    workflowId: "wf-x", taskId: "task-1", open: true, onClose: () => {},
    fetchProfile: async () => { throw new Error("运行记录不存在"); },
  }));
  const alert = document.querySelector('[role="alert"]');
  assert.ok(alert, "error surfaced via role=alert");
  assert.ok((alert!.textContent || "").includes("运行记录不存在"));
});

test("repeated node ids in one run get distinct cards and ordinal labels", async () => {
  // 活体暴露的真实形态（xs2-novel-flywheel-character run-cef95ebf）：
  // agent_deep 在同一 run 内执行 4 次，node_id 完全重复。
  const repeated: RunProfile = {
    run_id: "run-cef95ebf", workflow_id: "wf-x", status: "completed",
    wall_seconds: null,
    totals: { stages: 4, attempts: 4, completed: 4, failed: 0, failure_rate: 0,
              stages_with_multiple_attempts: [], stages_with_failures: [],
              error_classes: {} },
    stages: [1, 2, 3, 4].map(() => ({
      node_id: "agent_deep", attempts: 1, completed: 1, failed: 0,
      failure_rate: 0, automatic_retry_count: 0, output_repair_count: 0,
      duration_seconds: 60, error_classes: {},
      attempts_detail: [{ attempt_number: 1, trigger: "initial", status: "completed" }],
    })),
  };
  await render(React.createElement(RunProfilePanel, {
    workflowId: "wf-x", taskId: "task-1", open: true, onClose: () => {},
    fetchProfile: async () => repeated,
  }));
  const cards = document.querySelectorAll("[data-node-id]");
  assert.equal(cards.length, 4, "every repeated stage renders its own card");
  const text = bodyText();
  for (const ordinal of ["#1", "#2", "#3", "#4"]) {
    assert.ok(text.includes(ordinal), `ordinal ${ordinal} shown for duplicate node ids`);
  }
  // 旧 run 的 wall_seconds 为 null（B31 之前）→ 诚实显示 "-"
  assert.ok(text.includes("总耗时 -"), "null wall_seconds stays honest");
});

test("run_id query form passes explicit historical run id to the fetcher (R41 ?run_id=)", async () => {
  let received: string | undefined = "unset";
  await render(React.createElement(RunProfilePanel, {
    workflowId: "wf-x", taskId: "task-1", open: true, onClose: () => {},
    fetchProfile: async (_wf, _task, runId) => {
      received = runId;
      return r38ShapeProfile;
    },
  }));
  const input = document.querySelector<HTMLInputElement>('input[aria-label="按 run_id 查询历史 run"]');
  assert.ok(input, "run_id query input exists");
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, "run-738b7b19");
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  const form = input!.closest("form")!;
  await act(async () => {
    form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  });
  assert.equal(received, "run-738b7b19", "explicit run id forwarded");
});
