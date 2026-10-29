/**
 * 任务列表的连续退步标注（R51）。
 *
 * 三条命题：
 * 1. 默认不请求趋势（`with_trend` 不出现）——它是 opt-in，打开要多扫一遍 runs/；
 * 2. 打开开关后请求带 `with_trend=true` 与 `baseline_limit`；
 * 3. 只有 `regressing` 渲染徽章。`insufficient` 是「判不了」，显示成徽章会
 *    把「没有足够历史」读成「有问题」。
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
const { default: TaskHistoryPanel } = await import("./TaskHistoryPanel");
import type { TaskListFetcher } from "./TaskHistoryPanel";
import type { WorkflowTask } from "../../types";

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

function task(overrides: Partial<WorkflowTask>): WorkflowTask {
  return {
    task_id: "task-1",
    workflow_id: "wf-x",
    name: "示例任务",
    status: "completed",
    current_node_id: null,
    run_id: "run-c",
    created_at: "2026-10-03T00:00:00+08:00",
    started_at: "2026-10-03T00:00:00+08:00",
    completed_at: "2026-10-03T01:00:00+08:00",
    node_states: {},
    ...overrides,
  };
}

const regressingTasks = [
  task({
    task_id: "task-1",
    trend: {
      run_id: "run-c", trend: "regressing", consecutive_required: 2,
      points_considered: 4, comparisons: 2, delta_failure_rate: 0.2,
    },
  }),
  task({
    task_id: "task-2", name: "历史不足的任务",
    trend: {
      run_id: "run-b", trend: "insufficient", consecutive_required: 2,
      points_considered: 2, comparisons: 1, delta_failure_rate: 0.2,
    },
  }),
];

function makeFetcher() {
  const calls: Record<string, unknown>[] = [];
  const fetcher: TaskListFetcher = async (_workflowId, params) => {
    calls.push(params);
    // 只有带 with_trend 的请求才返回趋势块——不带的响应里没有 trend 键。
    const tasks: WorkflowTask[] = params.with_trend
      ? regressingTasks
      : regressingTasks.map(({ trend, ...rest }) => { void trend; return rest; });
    return { tasks, total: tasks.length };
  };
  return { fetcher, calls };
}

test("trend is opt-in: the default request carries no with_trend", async () => {
  const { fetcher, calls } = makeFetcher();
  await render(React.createElement(TaskHistoryPanel, {
    workflowId: "wf-x", onTaskClick: () => {}, fetchTasks: fetcher,
  }));
  assert.equal(calls.length, 1);
  assert.equal(calls[0].with_trend, undefined, "默认请求不应带 with_trend");
  assert.equal(document.querySelectorAll("[data-trend]").length, 0);
});

test("toggling the checkbox requests trends with a baseline limit", async () => {
  const { fetcher, calls } = makeFetcher();
  await render(React.createElement(TaskHistoryPanel, {
    workflowId: "wf-x", onTaskClick: () => {}, fetchTasks: fetcher,
  }));
  const checkbox = document.querySelector<HTMLInputElement>(
    'input[aria-label="标注连续退步"]');
  assert.ok(checkbox, "缺少「标注连续退步」开关");
  await act(async () => { checkbox!.click(); });

  const trendCall = calls[calls.length - 1];
  assert.equal(trendCall.with_trend, true);
  assert.equal(trendCall.baseline_limit, 5);
});

test("only regressing is badged; insufficient is not a verdict", async () => {
  // 第一个任务（regressing）并排和第二个（insufficient）一起验：只验「有徽章」
  // 会让「凡是趋势都挂徽章」这种退步绿灯。
  const { fetcher } = makeFetcher();
  await render(React.createElement(TaskHistoryPanel, {
    workflowId: "wf-x", onTaskClick: () => {}, fetchTasks: fetcher,
  }));
  const checkbox = document.querySelector<HTMLInputElement>(
    'input[aria-label="标注连续退步"]');
  await act(async () => { checkbox!.click(); });

  const badges = document.querySelectorAll("[data-trend]");
  assert.equal(badges.length, 1, "只有 regressing 该挂徽章");
  assert.equal(badges[0].getAttribute("data-trend"), "regressing");
  assert.ok((badges[0].textContent || "").includes("连续退步"));
});
