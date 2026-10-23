/**
 * 角色声音编辑器组件
 *
 * 功能：
 * 1. 显示和编辑 character_voice.md
 * 2. 从参考小说提取角色声音
 * 3. 从 character_profiles.md 生成模板
 * 4. 实时保存编辑内容
 */

import React, { useCallback, useState, useEffect } from 'react';
import { Users, Wand2, FileText, CheckCircle, AlertCircle, Save, RefreshCw } from 'lucide-react';

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
              disabled={generating || !status?.profiles_file_exists}
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

        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className="w-full rounded-xl border border-border bg-background p-4 font-mono text-sm leading-6 focus:outline-none focus:ring-2 focus:ring-primary/20"
          rows={30}
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
