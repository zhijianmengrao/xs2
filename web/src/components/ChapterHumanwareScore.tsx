/**
 * 章节对话人味评分组件（契约 §3.4 score-chapter 的 UI 接线）
 *
 * 对章节文件内所有引号对白按已保存的 character_voice.md 批量评分；
 * 聚合结构与 HumanwareScoreCard 同构，另含 dialogues_scored（对话段数）。
 * 挂载在读者评估页（ReviewView），按 workspace + chapter 键控重挂载。
 */

import React, { useEffect, useState } from 'react';
import { Heart } from 'lucide-react';
import HumanwareScoreCard, { type HumanwareScore } from './HumanwareScoreCard';
import {
  loadHumanwareHistory, appendHumanwareHistory, clearHumanwareHistory, formatHistoryTime,
  type ChapterScoreHistoryEntry,
} from '../lib/humanwareHistory';

// 契约 §3.4：score-chapter 成功输出 = §3.3 评分结构 + dialogues_scored
interface ChapterScoreResult extends HumanwareScore {
  dialogues_scored: number;
}

interface ChapterHumanwareScoreProps {
  workspaceId: string;
  chapter: string;
}

export default function ChapterHumanwareScore({ workspaceId, chapter }: ChapterHumanwareScoreProps) {
  // 与 CharacterVoiceEditor 一致：后端路由以 books 工作区纯 id 定位，
  // 页面传入的可能是完整相对路径（data/workspaces/books/<id>），取末段归一化。
  const workspaceKey = workspaceId.split('/').filter(Boolean).pop() || workspaceId;
  const chapterFile = `story/${String(chapter).padStart(4, '0')}/chapter.md`;
  const [scoring, setScoring] = useState(false);
  const [result, setResult] = useState<ChapterScoreResult | null>(null);
  const [error, setError] = useState('');
  // 本章评分历史（localStorage 按工作区持久化；父组件以 workspace:chapter 键控重挂载）
  const [history, setHistory] = useState<ChapterScoreHistoryEntry[]>([]);

  useEffect(() => {
    setHistory(loadHumanwareHistory(workspaceKey).filter(
      (item): item is ChapterScoreHistoryEntry => item.kind === 'chapter'));
  }, [workspaceKey]);

  const runScore = async () => {
    if (scoring) return;
    setScoring(true);
    setError('');
    try {
      const response = await fetch('/api/humanware/score-chapter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceKey,
          chapter_file: chapterFile
        })
      });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.status === 'success') {
        setResult(data as ChapterScoreResult);
        setHistory(appendHumanwareHistory(workspaceKey, {
          kind: 'chapter', ts: Date.now(), chapter: String(chapter),
          totalScore: data.total_score, grade: data.grade, dialogues: data.dialogues_scored,
        }).filter((item): item is ChapterScoreHistoryEntry => item.kind === 'chapter'));
      } else {
        // 业务失败（404 章节不存在 / 409 缺 voice 文件或无对白）：
        // 真实包络为 FastAPI {detail}（B17），CLI 直出的 {message} 作兜底
        setResult(null);
        setError(data?.detail || data?.message || '评分失败，请重试');
      }
    } catch {
      setResult(null);
      setError('评分失败：服务不可达，请稍后重试');
    } finally {
      setScoring(false);
    }
  };

  return (
    <section className="rounded-2xl border border-border bg-card p-5" aria-label="章节对话人味评分">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Heart className="h-4 w-4 text-destructive" />
          <h2 className="font-semibold">对话人味评分</h2>
        </div>
        <button
          onClick={runScore}
          disabled={scoring}
          className="rounded-lg border border-primary/30 px-4 py-2 text-sm text-primary disabled:opacity-60"
        >
          {scoring ? '评分中…' : result ? '重新评分' : '评估本章对话'}
        </button>
      </div>
      <p className="mt-2 text-xs leading-6 text-muted-foreground">
        按已保存的 character_voice.md 对本章全部引号对白批量评分；对话归属其前最近的「## 角色名」段落。
      </p>
      {error && (
        <p role="alert" className="mt-3 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs leading-6 text-destructive">
          {error}
        </p>
      )}
      {result && (
        <div className="mt-4">
          <p className="mb-3 text-xs text-muted-foreground">共评分 {result.dialogues_scored} 段对话</p>
          <HumanwareScoreCard score={result} />
        </div>
      )}
      {history.length > 0 && (
        <div className="mt-4" aria-label="章节评分历史记录">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-muted-foreground">历史记录（{history.length}）</p>
            <button
              onClick={() => { clearHumanwareHistory(workspaceKey); setHistory([]); }}
              className="rounded-lg border border-border px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
            >
              清空历史
            </button>
          </div>
          <ul className="mt-2 space-y-1">
            {history.map((item) => (
              <li key={item.ts} className="text-xs text-muted-foreground">
                第 {item.chapter} 章 · {item.totalScore} 分 · {item.grade} · {item.dialogues} 段对话 · {formatHistoryTime(item.ts)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
