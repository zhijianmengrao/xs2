import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

// tsx --test 环境无 localStorage：提供可控的内存实现（可切换为抛异常以模拟受限环境）
class MemoryStorage {
  private map = new Map<string, string>();
  get length() { return this.map.size; }
  getItem(key: string): string | null { return this.map.has(key) ? this.map.get(key)! : null; }
  setItem(key: string, value: string): void { this.map.set(key, String(value)); }
  removeItem(key: string): void { this.map.delete(key); }
  clear(): void { this.map.clear(); }
}

let broken = false;
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  get() {
    if (broken) throw new Error("storage unavailable");
    return storage;
  },
});
const storage = new MemoryStorage();

const {
  loadHumanwareHistory, appendHumanwareHistory, clearHumanwareHistory,
  humanwareHistoryKey, MAX_ENTRIES,
} = await import("./humanwareHistory");

beforeEach(() => {
  broken = false;
  storage.clear();
});

test("append/load roundtrip keeps newest first and isolates workspaces", () => {
  appendHumanwareHistory("demo-voice", { kind: "score", ts: 1, character: "林晚", excerpt: "a", totalScore: 88, grade: "B" });
  appendHumanwareHistory("demo-voice", { kind: "check", ts: 2, character: "林晚", excerpt: "b", matches: false, violationCount: 3 });
  appendHumanwareHistory("other-book", { kind: "chapter", ts: 3, chapter: "1", totalScore: 90, grade: "A", dialogues: 4 });

  const demo = loadHumanwareHistory("demo-voice");
  assert.equal(demo.length, 2);
  assert.equal(demo[0].kind, "check", "newest first");
  assert.equal(demo[1].kind, "score");
  assert.equal(loadHumanwareHistory("other-book").length, 1, "workspace isolation");
  assert.equal(humanwareHistoryKey("demo-voice"), "determinflow.humanware.history.demo-voice");
});

test("history is capped at MAX_ENTRIES and drops the oldest", () => {
  for (let i = 0; i < MAX_ENTRIES + 5; i++) {
    appendHumanwareHistory("demo-voice", { kind: "score", ts: i, character: `角色${i}`, excerpt: "", totalScore: i, grade: "B" });
  }
  const entries = loadHumanwareHistory("demo-voice");
  assert.equal(entries.length, MAX_ENTRIES);
  const scoreEntries = entries.filter((item): item is import("./humanwareHistory").ScoreHistoryEntry => item.kind === "score");
  assert.equal(scoreEntries[0].character, `角色${MAX_ENTRIES + 4}`, "newest kept");
  assert.equal(scoreEntries[scoreEntries.length - 1].character, `角色5`, "oldest beyond cap dropped");
});

test("corrupted or non-array payloads degrade to empty list", () => {
  storage.setItem(humanwareHistoryKey("demo-voice"), "{not json");
  assert.deepEqual(loadHumanwareHistory("demo-voice"), []);
  storage.setItem(humanwareHistoryKey("demo-voice"), '{"kind":"score"}');
  assert.deepEqual(loadHumanwareHistory("demo-voice"), []);
  storage.setItem(humanwareHistoryKey("demo-voice"), '[{"not":"entry"},42]');
  assert.deepEqual(loadHumanwareHistory("demo-voice"), [], "non-entry items filtered");
});

test("clear removes only the workspace history", () => {
  appendHumanwareHistory("a", { kind: "score", ts: 1, character: "x", excerpt: "", totalScore: 1, grade: "A" });
  appendHumanwareHistory("b", { kind: "score", ts: 2, character: "y", excerpt: "", totalScore: 2, grade: "A" });
  clearHumanwareHistory("a");
  assert.deepEqual(loadHumanwareHistory("a"), []);
  assert.equal(loadHumanwareHistory("b").length, 1, "other workspace untouched");
});

test("storage-unavailable environment degrades silently without throwing", () => {
  broken = true;
  assert.deepEqual(loadHumanwareHistory("demo-voice"), []);
  const entries = appendHumanwareHistory("demo-voice", { kind: "score", ts: 1, character: "林晚", excerpt: "", totalScore: 88, grade: "B" });
  assert.equal(entries.length, 1, "in-memory return value still usable for rendering");
  clearHumanwareHistory("demo-voice");
  broken = false;
});
