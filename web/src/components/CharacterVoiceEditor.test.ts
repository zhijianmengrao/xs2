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

test("generate button is disabled when profiles are missing", async () => {
  statusBody = { voice_file_exists: false, profiles_file_exists: false, humanware_enabled: false, character_count: 0 };
  await mount();
  const generateButton = button("从角色档案生成");
  assert.equal((generateButton as HTMLButtonElement).disabled, true);
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
