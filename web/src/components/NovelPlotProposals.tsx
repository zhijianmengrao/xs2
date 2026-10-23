import { useRef, useState } from 'react';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { applyNovelPlotPlan, type NovelAssistantEntry } from '../lib/api';
import { outlineChapterImpacts, type OutlineImpactInventory } from '../lib/novel-outline-impact';

const labels = {goal:'本章目标',conflict:'阻力与利益关系',choice:'人物选择',turning_point:'转折',cost:'代价与后果',reveal:'信息变化',payoff:'期待与兑现',hook:'收束与后续',time_advance:'世界时间推进'};
export default function NovelPlotProposals({entry,workspace,workflowId,impactInventory,disabled=false,onApplied}: {entry:NovelAssistantEntry;workspace:string;workflowId:string;impactInventory:OutlineImpactInventory;disabled?:boolean;onApplied:()=>void}) {
  const [selected,setSelected]=useState('');
  const [applying,setApplying]=useState(false);
  const [feedback,setFeedback]=useState('');
  const [localReceipts,setLocalReceipts]=useState<Record<string,boolean>>({});
  const guard=useRef(false);
  const options=entry.plot_options || [];
  const option=options.find(item=>item.id===selected);
  const proposedImpacts=option ? outlineChapterImpacts(
    option.chapters.map(plan=>({chapter:String(Number(plan.chapter)).padStart(4,'0'),type:'updated' as const})),
    impactInventory,
  ) : [];
  const downstreamImpacts=proposedImpacts.filter(item=>item.type==='downstream');
  const impactStatus=(impact:typeof proposedImpacts[number])=>{
    if(impact.type==='downstream'){
      const status=[
        impact.hasPlan?'已有章节方案需检查因果、人物动机和伏笔':'',
        impact.hasDraft?'已有正文保留，需检查前后衔接':'',
        impact.hasConfirmedArchive?'已确认档案保留，返修后需重新审核':'',
      ].filter(Boolean);
      return status.length?status.join('；'):'建议检查与本章方案的衔接';
    }
    const status=[
      impact.hasPlan?'会替换现有章节方案':'会新增章节方案',
      impact.hasDraft?'已有正文不会覆盖，需人工核对并决定是否返修':'尚无正文',
      impact.hasConfirmedArchive?'已确认档案会保留，正文返修后需重新审核':'尚无确认档案',
    ];
    return status.join('；');
  };
  const apply=async()=>{
    if(!option || applying || disabled || guard.current)return;
    guard.current=true;setApplying(true);setFeedback('正在核对前文并采用方案…');
    try {
      const result=await applyNovelPlotPlan({workflow_id:workflowId,workspace,entry_id:entry.id,option_id:option.id});
      setLocalReceipts(current=>({...current,[option.id]:true}));
      const downstream=downstreamImpacts.length
        ? ` 第 ${downstreamImpacts.map(item=>Number(item.chapter)).join('、')} 章等后续已有内容需复核。`
        : '';
      setFeedback(`${result.already_applied?'此前已采用':'已采用'}「${result.title}」，已加入第 ${result.chapters.map(Number).join('、')} 章计划，后续创作会读取。已写正文与确认档案未被覆盖。${downstream}`);
      setSelected('');onApplied();window.dispatchEvent(new CustomEvent('novel-artifacts-updated',{detail:{workspace}}));
    }catch(error){setFeedback(error instanceof Error?`未采用：${error.message}`:'采用失败，请重试。');}
    finally{guard.current=false;setApplying(false);}
  };
  if(!options.length)return null;
  return <section className="mt-5 space-y-3 border-t border-border pt-4"><h4 className="text-sm font-semibold">候选剧情方案</h4><p className="text-xs leading-6 text-muted-foreground">讨论不会修改小说。先查看影响与章节计划，再选择采用；已写正文请走返修流程。</p>
    {options.map(item=>{const applied=!!entry.plot_receipts?.[item.id] || !!localReceipts[item.id];return <div key={item.id} className="rounded-xl border border-border bg-background/40 p-4"><div className="flex items-center justify-between gap-2"><strong className="text-sm">{item.title}</strong><span className={`shrink-0 text-xs ${applied?'text-success':'text-muted-foreground'}`}>{applied?<><CheckCircle2 className="mr-1 inline h-3.5 w-3.5"/>已采用</>:'尚未采用'}</span></div><p className="mt-2 text-sm leading-7">{item.reason}</p><p className="mt-2 text-xs text-muted-foreground">影响第 {item.chapters.map(p=>Number(p.chapter)).join('、')} 章 · 推荐分 {item.score}（模型判断）</p><button disabled={disabled || applying || applied} onClick={()=>setSelected(item.id)} className="mt-3 rounded-lg border border-primary/40 px-3 py-2 text-sm text-primary disabled:opacity-50">{applied?'此方案已进入章节计划':'查看修改并采用'}</button></div>})}
    {option && <div role="dialog" aria-label="查看剧情方案" className="rounded-xl border border-primary/40 bg-background p-4"><h4 className="font-semibold">{option.title} · 修改预览</h4>{option.chapters.map(plan=><section key={plan.chapter} className="mt-4 border-t border-border pt-4"><h5 className="font-medium">第 {Number(plan.chapter)} 章 · {plan.title}</h5><dl className="mt-3 space-y-3">{Object.entries(labels).filter(([key])=>!!plan[key as keyof typeof labels]).map(([key,label])=><div key={key}><dt className="text-xs text-primary">{label}</dt><dd className="mt-1 whitespace-pre-wrap text-sm leading-7">{plan[key as keyof typeof labels]}</dd></div>)}</dl><details className="mt-3 text-sm"><summary className="cursor-pointer text-primary">前文依据与使用方式</summary>{plan.setup.map((anchor,i)=><div key={i} className="mt-3 border-l-2 border-primary/40 pl-3"><p className="text-muted-foreground">“{anchor.quote}”</p><p className="mt-1 leading-7">{anchor.use}</p></div>)}</details></section>)}{option.new_info?.length>0 && <p className="mt-4 text-sm leading-7 text-warning">新增设计：{option.new_info.join('；')}。采用后进入待写计划。</p>}{option.risks?.map((risk,i)=><p key={i} className="mt-2 text-sm leading-7 text-warning">风险：{risk}</p>)}<div className="mt-4 rounded-lg border border-border bg-secondary/20 p-3"><p className="text-sm font-medium">采用后的影响范围</p><ul className="mt-2 space-y-2">{proposedImpacts.map(impact=><li key={`${impact.chapter}-${impact.type}`} className="text-xs leading-6"><strong>第 {Number(impact.chapter)} 章 · {impact.type==='downstream'?'后续章节待复核':'章节方案将调整'}</strong><span className="block text-muted-foreground">{impactStatus(impact)}</span></li>)}</ul><p className="mt-2 text-xs leading-5 text-muted-foreground">采用只更新大纲与章节方案，不会覆盖正文、已确认档案或已采用写法；你可以先检查影响，再确认采用。</p></div><div className="mt-4 flex gap-2"><button disabled={applying || disabled} onClick={()=>void apply()} className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">{applying?<><Loader2 className="mr-1 inline h-4 w-4 animate-spin"/>正在采用…</>:'确认采用到章节计划'}</button><button disabled={applying} onClick={()=>setSelected('')} className="rounded-lg border border-border px-3 py-2 text-sm">继续讨论</button></div></div>}
    {feedback && <p role="status" className="text-sm leading-7 text-primary">{feedback}</p>}
  </section>;
}
