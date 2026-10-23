import type { NovelAssistantEntry } from '../lib/api';
import { configurationDisplay, type ConfigurationReceipt } from '../lib/novel-assistant-configuration';

export default function NovelConfigurationSuggestions({ entry, receipt, pendingApproval = false }: {
  entry: NovelAssistantEntry; receipt?: ConfigurationReceipt; pendingApproval?: boolean;
}) {
  if (entry.purpose !== 'configure') return null;
  const order = ['target_word_count', 'narrative_pov', 'conflict_point_count', 'foreshadowing_count', 'conflict_plan_mode', 'words_per_chapter', 'estimated_length', 'genre', 'premise', 'world_direction'];
  const suggestions = [...(entry.suggestions || [])].sort((a, b) => {
    const rank = (key: string) => order.includes(key) ? order.indexOf(key) : order.length;
    return rank(a.key) - rank(b.key);
  });
  return <section className="mt-4 border-t border-border pt-4">
    <h5 className="text-sm font-medium">作品配置建议</h5>
    <p role="status" className="mt-2 text-xs leading-6 text-muted-foreground">
      {receipt ? `已填写 ${receipt.applied.length} 项，保留 ${receipt.preserved.length} 项现有设置。可到作品设置查看和修改。`
        : pendingApproval ? '以下是建议参数，采用方案后填写未确定的设置；你的手动要求持续保留。' : '正在核对当前作品设置…'}世界观方向是规划草稿；开始建立世界观后才会生成正式档案。
    </p>
    {!(entry.suggestions || []).length && <p className="mt-2 text-xs text-muted-foreground">本次没有可填写的参数，现有设置保持原值。</p>}
    <div className="mt-3 space-y-3">{suggestions.map(item => <div key={item.key} className="rounded-lg border border-border bg-background/60 p-3">
      <div className="flex items-center justify-between gap-2"><p className="text-xs font-medium">{item.label}</p>
        <span className={`text-xs ${receipt?.applied.includes(item.key) ? 'text-success' : 'text-muted-foreground'}`}>
          {receipt?.applied.includes(item.key) ? '已填写' : receipt?.preserved.includes(item.key) ? '已保留原设置' : '建议'}</span></div>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7">{configurationDisplay(item.key, item.value)}</p>
      {item.reason && <p className="mt-2 text-xs leading-6 text-muted-foreground">{item.reason}</p>}
    </div>)}</div>
  </section>;
}
