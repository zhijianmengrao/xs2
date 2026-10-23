/**
 * Pure helpers for rendering novel reference choices.
 *
 * Kept in their own module so the component file stays Fast-Refresh safe
 * (react-refresh/only-export-components).
 */

export function referenceText(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(referenceText).filter(Boolean).join("；");
  if (value && typeof value === "object") return Object.values(value).map(referenceText).filter(Boolean).join("；");
  return "";
}

export function referenceTitle(value: unknown): string {
  const first = referenceText(value).replace(/^#+\s*/, "").split(/[。；;，,\n]/)[0];
  return first.length > 38 ? first.slice(0, 38) + "…" : first || "分析条目";
}
