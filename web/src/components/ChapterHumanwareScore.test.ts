import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { Window } from "happy-dom";

const dom = new Window({ url: "http://localhost/" });
for (const name of ["window", "document", "Node", "Text", "HTMLElement", "Element", "Event", "MouseEvent", "navigator", "sessionStorage", "localStorage"]) {
  Object.defineProperty(globalThis, name, { configurable: true, value: name === "window" ? dom : dom[name as keyof Window] });
}
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const React = await import("react");
const { act } = React;
Object.assign(globalThis, { React });
const { createRoot } = await import("react-dom/client");
const { default: ChapterHumanwareScore } = await import("./ChapterHumanwareScore");

let root: ReturnType<typeof createRoot> | undefined;
const originalFetch = globalThis.fetch;
const calls: Array<{ url: string; init?: RequestInit }> = [];
let scoreStatus = 200;
let scoreBody: Record<string, unknown> = {
  status: "success", total_score: 82, grade: "B", summary: "本章对话评分汇总",
  detailed_scores: { 声音一致性: 80, 对话自然度: 85, 情感真实度: 78, 行为一致性: 85 },
  issues: [], recommendation: "保持对话节奏", dialogues_scored: 12,
};
// 挂起开关：置 true 后下一次 score-chapter 请求保持在途，供手动放行
let holdFetch = false;
let resolveHeld: ((value: Response) => void) | undefined;

const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  document.body.replaceChildren();
  calls.length = 0;
  scoreStatus = 200;
  scoreBody = {
    status: "success", total_score: 82, grade: "B", summary: "本章对话评分汇总",
    detailed_scores: { 声音一致性: 80, 对话自然度: 85, 情感真实度: 78, 行为一致性: 85 },
    issues: [], recommendation: "保持对话节奏", dialogues_scored: 12,
  };
  holdFetch = false;
  resolveHeld = undefined;
  globalThis.fetch = originalFetch;
  dom.localStorage.clear();
});
after(async () => dom.happyDOM.abort());

function scoreButton() {
  const target = [...document.querySelectorAll<HTMLButtonElement>("button")].find(item => /评估本章对话|重新评分|评分中/.test(item.textContent || ""));
  assert.ok(target, "Missing score button");
  return target;
}
async function click(target: HTMLElement) { await act(async () => target.click()); }

async function mount(workspaceId = "data/workspaces/books/demo-voice", chapter = "0001") {
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.includes("/api/humanware/score-chapter")) {
      if (holdFetch) return new Promise<Response>(resolve => { resolveHeld = resolve; });
      return response(scoreBody, scoreStatus);
    }
    throw new Error(`Unexpected request: ${url}`);
  };
  root = createRoot(document.body.appendChild(document.createElement("div")));
  await act(async () => root?.render(React.createElement(ChapterHumanwareScore, { workspaceId, chapter })));
}

test("renders the section without issuing any request on mount", async () => {
  await mount();
  assert.ok((document.body.textContent || "").includes("对话人味评分"), "section title shown");
  assert.ok((document.body.textContent || "").includes("character_voice.md"), "voice-file dependency explained");
  assert.equal(calls.length, 0, "no request before user clicks");
});

test("click posts score-chapter with normalized workspace id and zero-padded chapter file", async () => {
  await mount("data/workspaces/books/demo-voice", "1");
  await click(scoreButton());
  const call = calls.find(c => c.url.includes("/api/humanware/score-chapter"));
  assert.ok(call, "score-chapter endpoint called");
  assert.equal(call.init?.method, "POST");
  const body = JSON.parse(String(call.init?.body));
  assert.equal(body.workspace_id, "demo-voice");
  assert.equal(body.chapter_file, "story/0001/chapter.md");
});

test("success renders dialogue count and the score card", async () => {
  await mount();
  await click(scoreButton());
  const text = document.body.textContent || "";
  assert.ok(text.includes("共评分 12 段对话"), "dialogues_scored shown");
  assert.ok(text.includes("82"), "total score shown");
  assert.ok(text.includes("/ 100"), "out of 100 shown");
  assert.ok(text.includes("对话自然度") && text.includes("行为一致性"), "dimension rows shown");
  assert.ok(text.includes("本章对话评分汇总"), "summary shown");
  assert.ok(/重新评分/.test(scoreButton().textContent || ""), "button switches to re-score label");
});

test("404 surfaces the FastAPI detail message and keeps the card hidden", async () => {
  scoreStatus = 404;
  // B17 同源回归锚：真实服务的业务失败包络是 {"detail": <CLI message>}
  scoreBody = { detail: "章节文件不存在: story/0001/chapter.md" };
  await mount();
  await click(scoreButton());
  const text = document.body.textContent || "";
  assert.ok(text.includes("章节文件不存在"), "CLI message surfaced");
  assert.ok(!text.includes("共评分"), "score result stays hidden");
});

test("409 without quotable dialogue surfaces the CLI message", async () => {
  scoreStatus = 409;
  scoreBody = { detail: "story/0001/chapter.md 中没有可评分的对话内容（未识别到引号对白）" };
  await mount();
  await click(scoreButton());
  const text = document.body.textContent || "";
  assert.ok(text.includes("没有可评分的对话内容"), "CLI message surfaced");
});

test("button stays disabled while a score request is in flight", async () => {
  holdFetch = true;
  await mount();
  await click(scoreButton());
  const busy = scoreButton();
  assert.equal(busy.disabled, true, "disabled while scoring");
  assert.ok(/评分中/.test(busy.textContent || ""), "busy label shown");
  await act(async () => resolveHeld?.(response(scoreBody)));
  assert.equal(scoreButton().disabled, false, "re-enabled after completion");
});

test("network failure surfaces a readable message without the card", async () => {
  globalThis.fetch = async () => { throw new Error("boom"); };
  root = createRoot(document.body.appendChild(document.createElement("div")));
  await act(async () => root?.render(React.createElement(ChapterHumanwareScore, { workspaceId: "demo-voice", chapter: "0001" })));
  await click(scoreButton());
  const text = document.body.textContent || "";
  assert.ok(text.includes("服务不可达"), "network failure message shown");
  assert.ok(!text.includes("共评分"), "no stale result shown");
});

// ===== 历史记录（localStorage 持久化）=====

test("successful chapter score appends a history entry that persists and clears on demand", async () => {
  await mount("data/workspaces/books/demo-voice", "1");
  await click(scoreButton());
  let text = document.body.textContent || "";
  assert.ok(text.includes("历史记录（1）"), "history section shown");
  assert.ok(text.includes("第 1 章 · 82 分 · B · 12 段对话"), "chapter entry details shown");

  // 卸载重挂（同工作区同章）：历史仍在
  await act(async () => root?.unmount());
  document.body.replaceChildren();
  calls.length = 0;
  await mount("data/workspaces/books/demo-voice", "1");
  text = document.body.textContent || "";
  assert.ok(text.includes("历史记录（1）"), "history persisted across remount");

  await click(button("清空历史"));
  text = document.body.textContent || "";
  assert.ok(!text.includes("历史记录（1）"), "history cleared");
});

function button(label: string) {
  const target = [...document.querySelectorAll<HTMLButtonElement>("button")].find(item => item.textContent?.includes(label));
  assert.ok(target, `Missing button: ${label}`);
  return target;
}
