import assert from "node:assert/strict";
import { test } from "node:test";
import { request } from "./http-client";

// B17 同族人因化锚：request 抛错的 message 必须把 FastAPI {"detail": "..."}
// 解成人话拒因（无花括号原文），其余形状保留原文以便排查。
const jsonResponse = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const textResponse = (body: string, status: number) => new Response(body, { status });

async function withFetch(mock: typeof fetch, run: () => Promise<void>) {
  const original = globalThis.fetch;
  globalThis.fetch = mock;
  try {
    await run();
  } finally {
    globalThis.fetch = original;
  }
}

test("4xx FastAPI string detail is surfaced as the human message", async () => {
  await withFetch(
    (async () => jsonResponse({ detail: "还没有读者评估，请先运行模拟读者。" }, 409)) as typeof fetch,
    async () => {
      await assert.rejects(request("/novel/reader-report"), (error: unknown) => {
        assert.ok(error instanceof Error, "throws Error");
        assert.equal(error.message, "API Error 409: 还没有读者评估，请先运行模拟读者。");
        return true;
      });
    },
  );
});

test("non-JSON error bodies keep their raw text", async () => {
  await withFetch(
    (async () => textResponse("internal traceback", 500)) as typeof fetch,
    async () => {
      await assert.rejects(request("/anything"), (error: unknown) => {
        assert.ok(error instanceof Error, "throws Error");
        assert.equal(error.message, "API Error 500: internal traceback");
        return true;
      });
    },
  );
});

test("non-string detail keeps the raw JSON for troubleshooting", async () => {
  await withFetch(
    (async () => jsonResponse({ detail: { internal: "secret" } }, 500)) as typeof fetch,
    async () => {
      await assert.rejects(request("/anything"), (error: unknown) => {
        assert.ok(error instanceof Error, "throws Error");
        assert.equal(error.message, 'API Error 500: {"detail":{"internal":"secret"}}');
        return true;
      });
    },
  );
});

test("4xx non-JSON body is kept as-is", async () => {
  await withFetch(
    (async () => textResponse("Bad Request", 400)) as typeof fetch,
    async () => {
      await assert.rejects(request("/anything"), (error: unknown) => {
        assert.ok(error instanceof Error, "throws Error");
        assert.equal(error.message, "API Error 400: Bad Request");
        return true;
      });
    },
  );
});

test("successful responses parse JSON and empty bodies resolve to undefined", async () => {
  await withFetch(
    (async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/empty")) return new Response("", { status: 200 });
      return jsonResponse({ value: 42 });
    }) as typeof fetch,
    async () => {
      assert.deepEqual(await request<{ value: number }>("/data"), { value: 42 });
      assert.equal(await request("/empty"), undefined);
    },
  );
});
