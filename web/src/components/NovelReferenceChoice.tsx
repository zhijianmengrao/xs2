import type { ReferenceChoice } from "../lib/api";

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
const scopeNames: Record<string, string> = { short_full: "短篇全文", serial_opening: "长篇开局", serial_chapter: "长篇章节", serial_arc: "长篇卷级", general: "通用" };
const layerNames: Record<string, string> = { language: "语言表达", structure: "叙事结构", narrative_lens: "叙事视角", dialogue: "对话", imagery: "意象", theme: "主题", character: "人物写法" };
export function ReferenceEvidence({ value }: { value: unknown }) {
  const items = Array.isArray(value) ? value.filter(item => item && typeof item === "object") as Record<string, unknown>[] : [];
  return items.length ? <details className="mt-6 border-t border-border/60 pt-4"><summary className="cursor-pointer text-sm font-medium">分析依据 · {items.length} 处</summary><div className="mt-4 space-y-5">{items.map((item, i) => <div key={i}><p className="text-sm leading-7">{referenceText(item.reason) || "样本证据"}</p>{referenceText(item.excerpt) && (/[\ue000-\uf8ff]/.test(referenceText(item.excerpt)) ? <p className="mt-2 text-xs text-muted-foreground">原文含特殊字体编码，保留分析说明；引文暂不展示。</p> : <blockquote className="mt-2 border-l-2 border-primary/30 pl-4 text-sm leading-7 text-muted-foreground">{referenceText(item.excerpt)}</blockquote>)}</div>)}</div></details> : null;
}
function Field({ label, value }: {label: string; value: unknown}) {
  const text = referenceText(value);
  return text ? <div className="grid gap-2 sm:grid-cols-[7rem_minmax(0,1fr)] sm:gap-5"><p className="text-sm font-medium text-accent">{label}</p><p className="whitespace-pre-wrap text-[15px] leading-8">{text}</p></div> : null;
}
export default function NovelReferenceChoice({ choice }: {choice: ReferenceChoice}) {
  const scopes = (Array.isArray(choice.application_scope) ? choice.application_scope : [choice.application_scope || "general"]).map(value => scopeNames[String(value)] || "需结合本书判断");
  return <div className="space-y-6">
    <p className="text-xs text-muted-foreground">{choice.kind === "style" ? layerNames[referenceText(choice.layer)] || "文风特点" : "冲突递进参考"} · {scopes.join("、")}</p>
    <h2 className="text-xl font-semibold leading-8">{referenceTitle(choice.title)}</h2>
    {choice.kind === "style" ? <><Field label="样本中的表现" value={choice.rule || choice.title} /><Field label="怎样参考" value={choice.transfer_guidance || "尚未提供迁移说明，可由写法顾问分析适配方式。"} /></> : <>
      <p className="text-sm leading-7 text-muted-foreground">下面是参考样本的推进过程。采用前要转成本书的目标与处境；原作事件不会直接带入正文。</p>
      <div className="space-y-5 border-l-2 border-primary/20 pl-5">{[["人物目标", choice.goal], ["提前埋下的隐患", choice.foreshadowing], ["遇到阻碍", choice.obstacle], ["尝试解决", choice.attempt || choice.resolution], ["付出代价", choice.cost], ["引出下一层问题", choice.next_obstacle], ["伏笔与结果回收", choice.payoff]].map(([label, value], i) => referenceText(value) && <div key={i}><p className="text-sm font-medium text-primary">{i + 1}. {String(label)}</p><p className="mt-2 whitespace-pre-wrap text-[15px] leading-8">{referenceText(value)}</p></div>)}</div>
      <Field label="为什么会递进" value={choice.causal_link} /><Field label="迁移方法" value={choice.transfer_guidance} />
    </>}
    <section className="space-y-3 border-t border-border/60 pt-5"><h3 className="font-semibold">适用条件与边界</h3><Field label="样本范围" value={scopes} /><Field label="使用边界" value={choice.limits || choice.constraints} /><Field label="适配提示" value={choice.adaptation_guidance} /><Field label="需要留意" value={choice.risk_flags} />{choice.requires_adaptation && <p className="text-sm leading-7 text-warning">需要确认本书的适配方法，单独勾选不会立即生效。</p>}</section>
    <ReferenceEvidence value={choice.evidence} />
    {!!choice.confidence && <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">分析信息</summary><p className="mt-2 leading-6">分析把握：{({high: "较高", medium: "中等", low: "暂定"} as Record<string, string>)[referenceText(choice.confidence)] || "待判断"} · 结论仅覆盖样本范围</p></details>}
  </div>;
}
