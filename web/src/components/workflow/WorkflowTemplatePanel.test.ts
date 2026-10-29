/**
 * 工作流模板列表的「全失败」徽标（R54）。
 *
 * 三条命题：
 * 1. `health.all_failed` 为真时渲染徽标，文案里的 N 来自 `consecutive_failed`；
 * 2. 门槛用后端给的 `required` 而不是前端写死——后端改门槛时文案要跟着变；
 * 3. 没有 health / 没有达成门槛 / 根本没有运行记录时都不渲染徽标。
 *    最后一条尤其重要：`run_count === 0` 是「没有证据」，把它标成告警会让
 *    每个新建的工作流一出生就是红的。
 */
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
const { WorkflowTemplatePanel } = await import("./WorkflowPageParts");
import type { WorkflowHealth, WorkflowSummary } from "../../types";

let root: ReturnType<typeof createRoot> | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  document.body.replaceChildren();
});
after(async () => dom.happyDOM.abort());

async function renderPanel(workflows: WorkflowSummary[]) {
  root = createRoot(document.body.appendChild(document.createElement("div")));
  await act(async () => root?.render(React.createElement(WorkflowTemplatePanel, {
    workflows,
    loading: false,
    errorMessage: null,
    onDismissError: () => {},
    onCreate: () => {},
    onView: () => {},
    onDelete: () => {},
  })));
  return document.body.textContent ?? "";
}

function health(overrides: Partial<WorkflowHealth>): WorkflowHealth {
  return {
    run_count: 5,
    latest_run_id: "run-e",
    latest_status: "failed",
    latest_started_at: "2026-10-05T00:00:00+08:00",
    consecutive_failed: 3,
    required: 3,
    all_failed: true,
    ...overrides,
  };
}

function summary(overrides: Partial<WorkflowSummary> = {}): WorkflowSummary {
  return {
    workflow_id: "wf-a",
    name: "示例工作流",
    node_count: 4,
    version: 2,
    created_at: "2026-10-01T00:00:00+08:00",
    updated_at: "2026-10-05T00:00:00+08:00",
    status: "idle",
    ...overrides,
  };
}

test("renders the badge with the actual streak length", async () => {
  const text = await renderPanel([summary({ health: health({ consecutive_failed: 4 }) })]);
  assert.match(text, /连续 4 次全失败/);
});

test("badge wording follows the backend streak, not a hardcoded N", async () => {
  // 门槛若被后端改成 5，而连续失败是 5，文案必须说 5。
  const text = await renderPanel([summary({
    health: health({ consecutive_failed: 5, required: 5 }),
  })]);
  assert.match(text, /连续 5 次全失败/);
  assert.doesNotMatch(text, /连续 3 次全失败/);
});

test("no badge when all_failed is false", async () => {
  const text = await renderPanel([summary({
    health: health({ all_failed: false, consecutive_failed: 1 }),
  })]);
  assert.doesNotMatch(text, /全失败/);
});

test("no badge when the workflow has no runs at all", async () => {
  // 空 workflow 不是「全失败」，是「没有证据」。
  const text = await renderPanel([summary({
    health: health({
      run_count: 0, latest_run_id: null, latest_status: null,
      latest_started_at: null, consecutive_failed: 0, all_failed: false,
    }),
  })]);
  assert.doesNotMatch(text, /全失败/);
});

test("no badge when health is absent (with_health not requested)", async () => {
  // 列表响应不带 health 块时也不能崩，更不能凭空渲染告警。
  const text = await renderPanel([summary()]);
  assert.doesNotMatch(text, /全失败/);
  assert.match(text, /示例工作流/);
});
