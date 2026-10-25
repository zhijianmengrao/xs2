const BASE_URL = "/api";

// FastAPI 错误包络为 {"detail": ...}；字符串 detail 是人话拒因，直接外显，
// 其余形状（非 JSON / detail 非字符串）保留原文以便排查（B17 同族人因化）。
function describeErrorBody(body: string): string {
  if (!body) return "";
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed?.detail === "string" && parsed.detail.trim()) return parsed.detail.trim();
  } catch { /* 非 JSON 体按原文返回 */ }
  return body;
}

export async function request<T>(
  url: string,
  options?: RequestInit,
): Promise<T> {
  const headers = new Headers(options?.headers);
  if (options?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.text();
    console.error(`API Error ${response.status}: ${error}`);
    throw new Error(
      `API Error ${response.status}: ${describeErrorBody(error) || response.statusText}`,
    );
  }

  const text = await response.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    console.error(`API JSON parse error for ${url}:`, text);
    throw new Error(`Invalid JSON response from ${url}`);
  }
}
