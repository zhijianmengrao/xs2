/**
 * 角色声音编辑器组件
 *
 * 功能：
 * 1. 显示和编辑 character_voice.md
 * 2. 从参考小说提取角色声音
 * 3. 从 character_profiles.md 生成模板
 * 4. 实时保存编辑内容
 */

import React, { useCallback, useState, useEffect, useMemo } from 'react';
import { Users, Wand2, FileText, CheckCircle, AlertCircle, Save, RefreshCw, Heart, MessageCircle, XCircle } from 'lucide-react';
import HumanwareScoreCard, { type HumanwareScore } from './HumanwareScoreCard';
import { CharacterSelect, ContentTextarea } from './CharacterVoiceInputs';

// 契约 §3.5：check-dialogue 成功输出（violations 可为空数组，suggestion 可为空串）
interface DialogueCheckResult {
  matches: boolean;
  character: string;
  violations: Array<{ rule: string; detail: string }>;
  suggestion: string;
}

interface HumanwareStatus {
  voice_file_exists: boolean;
  profiles_file_exists: boolean;
  humanware_enabled: boolean;
  character_count: number;
}

interface CharacterVoiceEditorProps {
  workspaceId: string;
}

export default function CharacterVoiceEditor({ workspaceId }: CharacterVoiceEditorProps) {
  // 后端 humanware 路由以 books 工作区纯 id 为路径参数；页面传入的可能是
  // 完整相对路径（data/workspaces/books/<id>），这里归一化为最后一段。
  const workspaceKey = workspaceId.split('/').filter(Boolean).pop() || workspaceId;
  const [content, setContent] = useState<string>('');
  const [status, setStatus] = useState<HumanwareStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  // 试评（score-content）：角色名从当前编辑器内容的「## 角色名」小节解析；
  // 评分按已保存的 character_voice.md 执行（编辑后需先保存）。
  const [scoreCharacter, setScoreCharacter] = useState('');
  const [scoreText, setScoreText] = useState('');
  const [scoring, setScoring] = useState(false);
  const [scoreResult, setScoreResult] = useState<HumanwareScore | null>(null);
  const [scoredFor, setScoredFor] = useState('');

  // 对话检查（check-dialogue，契约 §3.5）：同一份角色解析，判定符合性并给偏离点
  const [checkCharacter, setCheckCharacter] = useState('');
  const [checkText, setCheckText] = useState('');
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<DialogueCheckResult | null>(null);

  const characterNames = useMemo(() => {
    const names: string[] = [];
    for (const line of content.split('\n')) {
      const matched = line.match(/^##\s+(.+?)\s*$/);
      if (matched) names.push(matched[1]);
    }
    return names;
  }, [content]);

  const showMessage = useCallback((type: 'success' | 'error' | 'info', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 3000);
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const response = await fetch(`/api/humanware/status/${workspaceKey}`);
      if (response.ok) {
        const data = await response.json();
        setStatus(data);
      }
    } catch (error) {
      console.error('加载状态失败:', error);
    }
  }, [workspaceKey]);

  const loadContent = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/humanware/voice-file/${workspaceKey}`);
      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success') {
          setContent(data.content || '');
        } else {
          setContent('');
        }
      }
    } catch (error) {
      console.error('加载内容失败:', error);
      showMessage('error', '加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [workspaceKey, showMessage]);

  // 加载当前状态
  useEffect(() => {
    loadStatus();
    loadContent();
  }, [workspaceKey, loadStatus, loadContent]);

  const saveContent = async () => {
    setSaving(true);
    try {
      // 保存到文件系统（humanware 自有端点，做工作区校验与写锁）
      const response = await fetch(`/api/humanware/voice-file/${workspaceKey}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceKey,
          content
        })
      });

      if (response.ok) {
        showMessage('success', '保存成功');
        await loadStatus(); // 重新加载状态
      } else {
        showMessage('error', '保存失败');
      }
    } catch (error) {
      console.error('保存失败:', error);
      showMessage('error', '保存失败，请重试');
    } finally {
      setSaving(false);
    }
  };

  const generateFromProfiles = async () => {
    if (!status?.profiles_file_exists) {
      showMessage('error', '请先创建 character_profiles.md');
      return;
    }

    setGenerating(true);
    try {
      const response = await fetch('/api/humanware/generate-voice-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceKey,
          from_profiles: true
        })
      });

      if (response.ok) {
        const data = await response.json();
        showMessage('success', data.message);
        await loadContent();
        await loadStatus();
      } else {
        showMessage('error', '生成失败');
      }
    } catch (error) {
      console.error('生成失败:', error);
      showMessage('error', '生成失败，请重试');
    } finally {
      setGenerating(false);
    }
  };

  const runScore = async () => {
    if (!scoreCharacter || !scoreText.trim()) return;
    setScoring(true);
    try {
      const response = await fetch('/api/humanware/score-content', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceKey,
          character: scoreCharacter,
          content: scoreText
        })
      });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.status === 'success') {
        setScoreResult(data as HumanwareScore);
        setScoredFor(scoreCharacter);
      } else {
        // 业务失败（409 角色未定义等）：FastAPI 错误包络为 {detail}（B17 实测），
        // CLI 直出的 {message} 形状作兜底
        showMessage('error', data?.detail || data?.message || '评分失败，请重试');
      }
    } catch (error) {
      console.error('评分失败:', error);
      showMessage('error', '评分失败，请重试');
    } finally {
      setScoring(false);
    }
  };

  const runCheck = async () => {
    if (!checkCharacter || !checkText.trim()) return;
    setChecking(true);
    try {
      const response = await fetch('/api/humanware/check-dialogue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceKey,
          character: checkCharacter,
          dialogue: checkText
        })
      });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.status === 'success') {
        setCheckResult({
          matches: data.matches === true,
          character: typeof data.character === 'string' && data.character ? data.character : checkCharacter,
          violations: Array.isArray(data.violations)
            ? data.violations.filter((item: { rule?: unknown; detail?: unknown }) =>
                typeof item?.rule === 'string' && typeof item?.detail === 'string')
            : [],
          suggestion: typeof data.suggestion === 'string' ? data.suggestion : ''
        });
      } else {
        // 业务失败（409 角色未定义等）：真实包络为 FastAPI {detail}（B17）
        setCheckResult(null);
        showMessage('error', data?.detail || data?.message || '检查失败，请重试');
      }
    } catch (error) {
      console.error('检查失败:', error);
      showMessage('error', '检查失败：服务不可达，请稍后重试');
    } finally {
      setChecking(false);
    }
  };

  const cardClass = 'rounded-2xl border border-border bg-card shadow-sm';
  const buttonClass = 'inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors';
  const primaryButtonClass = `${buttonClass} bg-primary text-primary-foreground hover:bg-primary/90`;
  const secondaryButtonClass = `${buttonClass} border border-border bg-background hover:bg-accent`;

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">加载中...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 消息提示 */}
      {message && (
        <div className={`rounded-xl border p-4 ${
          message.type === 'success' ? 'border-success/20 bg-success/10 text-success' :
          message.type === 'error' ? 'border-destructive/20 bg-destructive/10 text-destructive' :
          'border-primary/20 bg-primary/10 text-primary'
        }`}>
          <div className="flex items-center gap-2">
            {message.type === 'success' ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
            <span className="text-sm">{message.text}</span>
          </div>
        </div>
      )}

      {/* 状态卡片 */}
      <section className={`${cardClass} p-5`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">角色声音锚点</h2>
          </div>
          <div className="flex gap-2">
            <button
              onClick={generateFromProfiles}
              disabled={generating}
              title={status?.profiles_file_exists ? undefined : '请先在「创作流程 → 创建角色」生成角色档案（character_profiles.md）'}
              className={secondaryButtonClass}
            >
              <Wand2 className="h-4 w-4" />
              {generating ? '生成中...' : '从角色档案生成'}
            </button>
            <button
              onClick={saveContent}
              disabled={saving}
              className={primaryButtonClass}
            >
              <Save className="h-4 w-4" />
              {saving ? '保存中...' : '保存'}
            </button>
          </div>
        </div>

        {!status?.profiles_file_exists && (
          <p role="status" className="mt-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs leading-6 text-warning">
            尚未创建角色档案：请先到「创作流程」运行「创建角色」步骤生成 character_profiles.md，
            然后回到这里点击「从角色档案生成」。
          </p>
        )}

        <div className="mt-4 flex gap-6 text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            <span>状态: {status?.voice_file_exists ? '已创建' : '未创建'}</span>
          </div>
          {status?.voice_file_exists && (
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              <span>角色数量: {status.character_count}</span>
            </div>
          )}
        </div>

        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          角色声音锚点定义每个角色的独特说话方式、认知模式和情绪表达，确保AI生成的对话和内心独白具有人味。
        </p>
      </section>

      {/* 编辑器 */}
      <section className={`${cardClass} p-5`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold">编辑内容</h3>
          <div className="flex gap-2 text-xs text-muted-foreground">
            <span>{content.length} 字符</span>
            <span>·</span>
            <span>{content.split('\n').length} 行</span>
          </div>
        </div>

        <ContentTextarea
          value={content}
          onChange={setContent}
          rows={30}
          ariaLabel="角色声音锚点编辑器"
          mono
          placeholder="# 角色声音锚点&#10;&#10;## 角色名&#10;&#10;### 核心声音定位&#10;- **表达方式**: ...&#10;&#10;### 句法指纹&#10;- **平均句长**: ...&#10;&#10;..."
        />

        <div className="mt-4 text-xs text-muted-foreground">
          <p>提示：</p>
          <ul className="mt-2 ml-4 list-disc space-y-1">
            <li>为每个主要角色定义独特的说话方式</li>
            <li>包含句法指纹、口头禅、停顿模式、认知偏差等</li>
            <li>列出该角色绝不会使用的表达方式</li>
            <li>保存后，写作agent会自动遵守这些定义</li>
          </ul>
        </div>
      </section>

      {/* 试评（人味评分） */}
      <section className={`${cardClass} p-5`} aria-label="人味评分试评">
        <div className="flex items-center gap-2">
          <Heart className="h-5 w-5 text-destructive" />
          <h3 className="text-sm font-semibold">试评一段内容（人味评分）</h3>
        </div>
        <p className="mt-2 text-xs leading-6 text-muted-foreground">
          选择角色并粘贴一段对话或内心独白进行试评。评分按<strong>已保存</strong>的
          character_voice.md 执行——编辑器改动后请先保存再评分。
        </p>

        <div className="mt-4 space-y-3">
          <CharacterSelect
            names={characterNames}
            value={scoreCharacter}
            onChange={setScoreCharacter}
            ariaLabel="选择试评角色"
          />

          <ContentTextarea
            value={scoreText}
            onChange={setScoreText}
            rows={6}
            ariaLabel="待评分内容"
            placeholder="粘贴待评分的对话或内心独白…"
          />

          <div>
            <button
              onClick={runScore}
              disabled={!scoreCharacter || !scoreText.trim() || scoring}
              className={primaryButtonClass}
            >
              <Heart className="h-4 w-4" />
              {scoring ? '评分中...' : '开始评分'}
            </button>
          </div>
        </div>

        {scoreResult && (
          <div className="mt-6">
            <p className="mb-3 text-xs text-muted-foreground">{scoredFor} 的评分结果</p>
            <HumanwareScoreCard score={scoreResult} />
          </div>
        )}
      </section>

      {/* 对话检查（check-dialogue） */}
      <section className={`${cardClass} p-5`} aria-label="对话声音检查">
        <div className="flex items-center gap-2">
          <MessageCircle className="h-5 w-5 text-primary" />
          <h3 className="text-sm font-semibold">检查一段对话（声音符合性）</h3>
        </div>
        <p className="mt-2 text-xs leading-6 text-muted-foreground">
          判断一段对话是否符合所选角色的声音定义，并列出偏离点与修改建议。
          检查按<strong>已保存</strong>的 character_voice.md 执行——编辑器改动后请先保存再检查。
        </p>

        <div className="mt-4 space-y-3">
          <CharacterSelect
            names={characterNames}
            value={checkCharacter}
            onChange={setCheckCharacter}
            ariaLabel="选择检查角色"
          />

          <ContentTextarea
            value={checkText}
            onChange={setCheckText}
            rows={4}
            ariaLabel="待检查对话"
            placeholder="粘贴待检查的对话…"
          />

          <div>
            <button
              onClick={runCheck}
              disabled={!checkCharacter || !checkText.trim() || checking}
              className={primaryButtonClass}
            >
              <MessageCircle className="h-4 w-4" />
              {checking ? '检查中...' : '检查对话'}
            </button>
          </div>
        </div>

        {checkResult && (
          <div className="mt-6 space-y-3" aria-label="对话检查结果">
            {checkResult.matches ? (
              <p className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
                <CheckCircle className="h-4 w-4" />
                符合「{checkResult.character}」的声音定义
              </p>
            ) : (
              <p className="flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
                <XCircle className="h-4 w-4" />
                偏离「{checkResult.character}」的声音定义
              </p>
            )}

            {checkResult.violations.length > 0 && (
              <div className="space-y-2">
                {checkResult.violations.map((violation, index) => (
                  <div key={index} className="rounded-lg bg-muted/50 p-3">
                    <div className="text-xs font-semibold text-muted-foreground">{violation.rule}</div>
                    <div className="mt-1 text-sm">{violation.detail}</div>
                  </div>
                ))}
              </div>
            )}

            {checkResult.suggestion && (
              <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
                <div className="text-sm font-semibold text-primary">修改建议</div>
                <p className="mt-1 text-sm text-primary/80">{checkResult.suggestion}</p>
              </div>
            )}
          </div>
        )}
      </section>

      {/* 使用说明 */}
      <section className={`${cardClass} p-5 text-sm leading-7`}>
        <h2 className="font-semibold">如何使用角色声音功能？</h2>
        <div className="mt-3 space-y-3 text-muted-foreground">
          <p>
            <strong>1. 首次创建：</strong>
            点击"从角色档案生成"按钮，系统会为 character_profiles.md 中的每个角色创建声音模板。
          </p>
          <p>
            <strong>2. 完善内容：</strong>
            编辑生成的模板，为每个角色补充认知偏差、情绪表达模式、禁止说的话等细节。
          </p>
          <p>
            <strong>3. 自动生效：</strong>
            保存后，所有写作agent（对话、内心、动作）会自动遵守角色声音定义，确保内容有人味。
          </p>
          <p>
            <strong>4. 持续迭代：</strong>
            根据生成的章节反馈，不断完善角色声音定义，提升人味质量。
          </p>
        </div>
      </section>
    </div>
  );
}
