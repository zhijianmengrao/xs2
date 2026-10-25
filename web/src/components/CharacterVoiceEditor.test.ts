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
const { default: CharacterVoiceEditor } = await import("./CharacterVoiceEditor");

let root: ReturnType<typeof createRoot> | undefined;
const originalFetch = globalThis.fetch;
const calls: Array<{ url: string; init?: RequestInit }> = [];
let statusBody: Record<string, unknown> = {
  voice_file_exists: false, profiles_file_exists: true, humanware_enabled: false, character_count: 0,
};
let voiceBody: { status: string; content?: string | null } = { status: "not_found", content: null };
let generateStatus = 200;
let saveStatus = 200;
let scoreStatus = 200;
let scoreBody: Record<string, unknown> = {
  status: "success", total_score: 88, grade: "B", summary: "总体评价",
  detailed_scores: { 声音一致性: 85, 对话自然度: 90, 情感真实度: 80, 行为一致性: 95 },
  issues: [], recommendation: "改进建议",
};

const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  document.body.replaceChildren();
  calls.length = 0;
  statusBody = { voice_file_exists: false, profiles_file_exists: true, humanware_enabled: false, character_count: 0 };
  voiceBody = { status: "not_found", content: null };
  generateStatus = 200;
  saveStatus = 200;
  scoreStatus = 200;
  scoreBody = {
    status: "success", total_score: 88, grade: "B", summary: "总体评价",
    detailed_scores: { 声音一致性: 85, 对话自然度: 90, 情感真实度: 80, 行为一致性: 95 },
    issues: [], recommendation: "改进建议",
  };
  globalThis.fetch = originalFetch;
});
after(async () => dom.happyDOM.abort());

function button(label: string) {
  const target = [...document.querySelectorAll<HTMLButtonElement>("button")].find(item => item.textContent?.includes(label));
  assert.ok(target, `Missing button: ${label}`);
  return target;
}
async function click(target: HTMLElement) { await act(async () => target.click()); }

async function mount(workspaceId = "data/workspaces/books/demo-voice") {
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.includes("/api/humanware/status/")) return response(statusBody);
    if (url.includes("/api/humanware/voice-file/")) {
      if (init?.method === "PUT") {
        return response({ status: "success", message: "保存成功" }, saveStatus);
      }
      return response(voiceBody);
    }
    if (url.includes("/api/humanware/generate-voice-file")) return response(
      { status: "success", message: "已生成 1 个角色声音模板", character_count: 1 }, generateStatus,
    );
    if (url.includes("/api/humanware/score-content")) return response(scoreBody, scoreStatus);
    throw new Error(`Unexpected request: ${url}`);
  };
  root = createRoot(document.body.appendChild(document.createElement("div")));
  await act(async () => root?.render(React.createElement(CharacterVoiceEditor, { workspaceId })));
}

test("workspaceId full relative path is normalized to the bare id for all API calls", async () => {
  await mount("data/workspaces/books/demo-voice");
  const statusCall = calls.find(c => c.url.includes("/api/humanware/status/"));
  assert.ok(statusCall, "status endpoint called");
  assert.ok(statusCall.url.endsWith("/api/humanware/status/demo-voice"), `got ${statusCall.url}`);
  const voiceCall = calls.find(c => c.url.includes("/api/humanware/voice-file/") && !c.init?.method);
  assert.ok(voiceCall, "voice-file endpoint called");
  assert.ok(voiceCall.url.endsWith("/api/humanware/voice-file/demo-voice"), `got ${voiceCall.url}`);
});

test("renders 未创建 state and enables generate when profiles exist", async () => {
  await mount();
  const statusText = [...document.querySelectorAll("span")].map(el => el.textContent || "").join(" ");
  assert.ok(statusText.includes("未创建"));
  const generateButton = button("从角色档案生成");
  assert.equal((generateButton as HTMLButtonElement).disabled, false);
});

test("generate button posts workspace_id with the bare id", async () => {
  await mount();
  await click(button("从角色档案生成"));
  const generateCall = calls.find(c => c.url.includes("/generate-voice-file"));
  assert.ok(generateCall, "generate endpoint called");
  assert.equal(generateCall.init?.method, "POST");
  const body = JSON.parse(String(generateCall.init?.body));
  assert.equal(body.workspace_id, "demo-voice");
  assert.equal(body.from_profiles, true);
});

test("generate button stays clickable without profiles and shows guidance on click", async () => {
  statusBody = { voice_file_exists: false, profiles_file_exists: false, humanware_enabled: false, character_count: 0 };
  await mount();
  const generateButton = button("从角色档案生成");
  // 无档案时不再禁用，点击应给出引导提示
  assert.equal((generateButton as HTMLButtonElement).disabled, false);
  await click(generateButton);
  const messages = [...document.querySelectorAll("span")].map(el => el.textContent || "").join(" ");
  assert.ok(messages.includes("character_profiles.md"), "guidance message shown");
  // 未生成前不应调用生成端点
  assert.ok(!calls.some(c => c.url.includes("/generate-voice-file")), "no generate call without profiles");
});

test("save posts PUT with normalized workspace_id and content, then reloads status", async () => {
  await mount();
  const editor = document.querySelector<HTMLTextAreaElement>("textarea");
  assert.ok(editor, "editor textarea present");
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(editor, "# 角色声音锚点\n\n## 林晚\n");
    editor.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await click(button("保存"));
  const saveCall = calls.find(c => c.url.includes("/api/humanware/voice-file/") && c.init?.method === "PUT");
  assert.ok(saveCall, "PUT save called");
  assert.ok(saveCall.url.endsWith("/api/humanware/voice-file/demo-voice"), `got ${saveCall.url}`);
  const body = JSON.parse(String(saveCall.init?.body));
  assert.equal(body.workspace_id, "demo-voice");
  assert.match(body.content, /林晚/);
  // 保存成功后应重新加载状态
  const statusCallsAfter = calls.filter(c => c.url.includes("/api/humanware/status/"));
  assert.ok(statusCallsAfter.length >= 2, "status reloaded after save");
});

test("failed save surfaces 保存失败 message", async () => {
  saveStatus = 500;
  await mount();
  await click(button("保存"));
  const messages = [...document.querySelectorAll("span")].map(el => el.textContent || "").join(" ");
  assert.ok(messages.includes("保存失败"));
});

test("voice file content is loaded into the editor when present", async () => {
  voiceBody = { status: "success", content: "# 角色声音锚点\n\n## 林晚\n\n### 核心声音定位\n" };
  await mount();
  const editor = document.querySelector<HTMLTextAreaElement>("textarea");
  assert.ok(editor);
  assert.match(editor.value, /林晚/);
});

// ===== 试评（score-content → HumanwareScoreCard）=====

const VOICE_WITH_NAMES = "# 角色声音锚点\n\n## 林晚\n\n### 核心声音定位\n- **表达方式**: 冷静克制\n\n## 沈砚\n\n### 核心声音定位\n- **表达方式**: 热络外放\n";

function characterSelect() {
  const el = document.querySelector<HTMLSelectElement>("select[aria-label='选择试评角色']");
  assert.ok(el, "character select present");
  return el;
}

async function chooseCharacter(name: string) {
  const el = characterSelect();
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value")?.set;
    setter?.call(el, name);
    el.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
}

async function setScoreText(value: string) {
  const el = document.querySelectorAll<HTMLTextAreaElement>("textarea")[1];
  assert.ok(el, "score textarea present");
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(el, value);
    el.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
}

test("score section lists characters parsed from the voice content", async () => {
  voiceBody = { status: "success", content: VOICE_WITH_NAMES };
  await mount();
  const options = [...characterSelect().options].map(option => option.value);
  assert.ok(options.includes("林晚"), `got ${JSON.stringify(options)}`);
  assert.ok(options.includes("沈砚"), `got ${JSON.stringify(options)}`);
});

test("score button stays disabled until both character and text are provided", async () => {
  voiceBody = { status: "success", content: VOICE_WITH_NAMES };
  await mount();
  const scoreButton = button("开始评分");
  assert.equal((scoreButton as HTMLButtonElement).disabled, true, "disabled without input");
  await chooseCharacter("林晚");
  assert.equal((button("开始评分") as HTMLButtonElement).disabled, true, "still disabled without text");
  await setScoreText("「你到底想说什么？」");
  assert.equal((button("开始评分") as HTMLButtonElement).disabled, false, "enabled with both");
  // 双保险：空输入下点击也不应发出请求
  assert.ok(!calls.some(c => c.url.includes("/score-content")), "no score call");
});

test("score flow posts score-content with normalized id and renders the score card", async () => {
  voiceBody = { status: "success", content: VOICE_WITH_NAMES };
  await mount();
  await chooseCharacter("林晚");
  await setScoreText("「你到底想说什么？」林晚把笔放下。");
  await click(button("开始评分"));
  const scoreCall = calls.find(c => c.url.includes("/api/humanware/score-content"));
  assert.ok(scoreCall, "score endpoint called");
  assert.equal(scoreCall.init?.method, "POST");
  const body = JSON.parse(String(scoreCall.init?.body));
  assert.equal(body.workspace_id, "demo-voice");
  assert.equal(body.character, "林晚");
  assert.match(body.content, /想说什么/);
  const text = document.body.textContent || "";
  assert.ok(text.includes("林晚 的评分结果"), "scored-for caption shown");
  assert.ok(text.includes("88"), "total score shown");
  assert.ok(text.includes("/ 100"), "out of 100 shown");
  assert.ok(text.includes("声音一致性") && text.includes("行为一致性"), "dimension rows shown");
  assert.ok(text.includes("改进建议"), "recommendation section shown");
});

test("score 409 surfaces the CLI message and keeps the card hidden", async () => {
  voiceBody = { status: "success", content: VOICE_WITH_NAMES };
  scoreStatus = 409;
  scoreBody = { status: "error", message: "角色 林晚 未在 character_voice.md 中定义", code: 409 };
  await mount();
  await chooseCharacter("林晚");
  await setScoreText("「测试」");
  await click(button("开始评分"));
  const scoreCall = calls.find(c => c.url.includes("/api/humanware/score-content"));
  assert.ok(scoreCall, "score endpoint called");
  const text = document.body.textContent || "";
  assert.ok(text.includes("未在 character_voice.md 中定义"), "CLI message surfaced");
  assert.ok(!text.includes("的评分结果"), "score card stays hidden");
});

test("score section explains when no character sections exist yet", async () => {
  await mount();
  const text = document.body.textContent || "";
  assert.ok(text.includes("还没有「## 角色名」小节"), "empty-state hint shown");
  assert.equal((button("开始评分") as HTMLButtonElement).disabled, true, "disabled without characters");
});
