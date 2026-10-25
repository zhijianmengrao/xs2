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
const { CharacterSelect, ContentTextarea } = await import("./CharacterVoiceInputs");

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

test("CharacterSelect renders the placeholder plus one option per parsed name", async () => {
  await render(React.createElement(CharacterSelect, {
    names: ["林晚", "沈砚"], value: "", onChange: () => {}, ariaLabel: "选择试评角色",
  }));
  const select = document.querySelector<HTMLSelectElement>("select[aria-label='选择试评角色']");
  assert.ok(select, "select rendered with aria-label");
  const options = [...select.options].map(option => option.value);
  assert.deepEqual(options, ["", "林晚", "沈砚"]);
  assert.equal(select.options[0].textContent, "选择角色");
});

test("CharacterSelect reports the chosen name via onChange", async () => {
  let chosen = "";
  await render(React.createElement(CharacterSelect, {
    names: ["林晚"], value: "", onChange: (value: string) => { chosen = value; }, ariaLabel: "选择检查角色",
  }));
  const select = document.querySelector<HTMLSelectElement>("select[aria-label='选择检查角色']");
  assert.ok(select);
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value")?.set;
    setter?.call(select, "林晚");
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
  assert.equal(chosen, "林晚");
});

test("CharacterSelect shows the empty-state hint only when no character sections exist", async () => {
  await render(React.createElement(CharacterSelect, {
    names: [], value: "", onChange: () => {}, ariaLabel: "选择试评角色",
  }));
  let text = document.body.textContent || "";
  assert.ok(text.includes("还没有「## 角色名」小节"), "hint shown when empty");

  await act(async () => root?.unmount());
  document.body.replaceChildren();
  await render(React.createElement(CharacterSelect, {
    names: ["林晚"], value: "", onChange: () => {}, ariaLabel: "选择试评角色",
  }));
  text = document.body.textContent || "";
  assert.ok(!text.includes("还没有「## 角色名」小节"), "hint hidden when names exist");
});

test("ContentTextarea renders value, rows, placeholder and reports edits", async () => {
  let value = "";
  await render(React.createElement(ContentTextarea, {
    value, onChange: (next: string) => { value = next; },
    rows: 6, placeholder: "粘贴待评分的对话…", ariaLabel: "待评分内容",
  }));
  const textarea = document.querySelector<HTMLTextAreaElement>("textarea[aria-label='待评分内容']");
  assert.ok(textarea, "textarea rendered with aria-label");
  // happy-dom 的 rows 反映为字符串属性值
  assert.equal(Number(textarea.getAttribute("rows")), 6);
  assert.equal(textarea.placeholder, "粘贴待评分的对话…");
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(textarea, "「测试」");
    textarea.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  assert.equal(value, "「测试」");
});

test("ContentTextarea mono flag adds the monospace class, default does not", async () => {
  await render(React.createElement(ContentTextarea, {
    value: "", onChange: () => {}, rows: 30, ariaLabel: "编辑器", mono: true,
  }));
  const mono = document.querySelector<HTMLTextAreaElement>("textarea[aria-label='编辑器']");
  assert.ok(mono?.className.includes("font-mono"), "mono adds font-mono");

  await render(React.createElement(ContentTextarea, {
    value: "", onChange: () => {}, rows: 4, ariaLabel: "待检查对话",
  }));
  const plain = document.querySelector<HTMLTextAreaElement>("textarea[aria-label='待检查对话']");
  assert.ok(plain && !plain.className.includes("font-mono"), "default has no font-mono");
});
