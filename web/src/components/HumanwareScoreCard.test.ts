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
const { default: HumanwareScoreCard, HumanwareScoreBadge } = await import("./HumanwareScoreCard");

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

// 契约 docs/humanware-helper-contract.md §3.3 的 score-text 成功载荷样例
const contractScore = {
  total_score: 88,
  grade: "B",
  summary: "总体评价：声音贴合，偶有出戏。",
  detailed_scores: { 声音一致性: 85, 对话自然度: 90, 情感真实度: 80, 行为一致性: 95 },
  issues: [
    { dimension: "声音一致性", type: "voice_break", severity: "medium", message: "句长骤增，偏离句法指纹。" },
  ],
  recommendation: "压缩长句，保持角色惯用节奏。",
};

test("renders contract §3.3 payload: total, grade, four dimensions, issues, recommendation", async () => {
  await render(React.createElement(HumanwareScoreCard, { score: contractScore }));
  const text = bodyText();
  assert.ok(text.includes("88"), "total score shown");
  assert.ok(text.includes("/ 100"), "scale shown");
  assert.ok(text.includes("B"), "grade shown");
  assert.ok(text.includes("总体评价：声音贴合，偶有出戏。"), "summary shown");
  for (const dimension of ["声音一致性", "对话自然度", "情感真实度", "行为一致性"]) {
    assert.ok(text.includes(dimension), `dimension shown: ${dimension}`);
  }
  assert.ok(text.includes("句长骤增，偏离句法指纹。"), "issue message shown");
  assert.ok(text.includes("压缩长句，保持角色惯用节奏。"), "recommendation shown");
});

test("shows at most five issues and notes the overflow count", async () => {
  const issues = Array.from({ length: 7 }, (_, i) => ({
    dimension: "对话自然度",
    type: "voice_break",
    severity: "low",
    message: `问题详情${["一", "二", "三", "四", "五", "六", "七"][i]}`,
  }));
  await render(React.createElement(HumanwareScoreCard, {
    score: { ...contractScore, issues },
  }));
  const text = bodyText();
  for (const label of ["问题详情一", "问题详情二", "问题详情三", "问题详情四", "问题详情五"]) {
    assert.ok(text.includes(label), `first-five issue shown: ${label}`);
  }
  assert.ok(!text.includes("问题详情六"), "sixth issue hidden");
  assert.ok(!text.includes("问题详情七"), "seventh issue hidden");
  assert.ok(text.includes("还有 2 个问题未显示"), "overflow note shown");
});

test("hides the issues and recommendation sections when both are empty", async () => {
  await render(React.createElement(HumanwareScoreCard, {
    score: { ...contractScore, issues: [], recommendation: "" },
  }));
  const text = bodyText();
  assert.ok(!text.includes("发现的问题"), "issues section hidden");
  assert.ok(!text.includes("改进建议"), "recommendation section hidden");
});

test("badge shows the score and fires its click handler", async () => {
  let clicked = false;
  await render(React.createElement(HumanwareScoreBadge, { score: 92, onClick: () => { clicked = true; } }));
  const text = bodyText();
  assert.ok(text.includes("人味 92"), "badge label shown");
  const badge = document.querySelector<HTMLButtonElement>("button");
  assert.ok(badge, "badge is a button");
  await act(async () => badge.click());
  assert.equal(clicked, true, "click handler fired");
});
