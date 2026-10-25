/**
 * 角色声音页共享输入控件
 *
 * 从 CharacterVoiceEditor 的三处同构标记抽取（试评/检查/编辑器）：
 * - CharacterSelect：角色下拉（选项来自编辑器「## 角色名」小节解析；
 *   无角色小节时给出空态提示，试评与检查两个区块共用）
 * - ContentTextarea：内容输入（编辑器/试评/检查三处共用，mono 控制等宽字体）
 *
 * DOM 契约（tests/CharacterVoiceEditor.test.ts 按顺序与 aria-label 定位）：
 * 页面内 textarea 顺序必须保持 编辑器 → 试评 → 检查。
 */

import React from 'react';

const selectClass = 'w-full max-w-xs rounded-xl border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20';
const textareaClass = 'w-full rounded-xl border border-border bg-background p-4 text-sm leading-6 focus:outline-none focus:ring-2 focus:ring-primary/20';

interface CharacterSelectProps {
  names: string[];
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
}

export function CharacterSelect({ names, value, onChange, ariaLabel }: CharacterSelectProps) {
  return (
    <div className="space-y-2">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={ariaLabel}
        className={selectClass}
      >
        <option value="">选择角色</option>
        {names.map((name) => (
          <option key={name} value={name}>{name}</option>
        ))}
      </select>
      {names.length === 0 && (
        <p className="text-xs text-muted-foreground">
          当前编辑内容里还没有「## 角色名」小节——请先生成或编写角色声音定义。
        </p>
      )}
    </div>
  );
}

interface ContentTextareaProps {
  value: string;
  onChange: (value: string) => void;
  rows: number;
  placeholder?: string;
  ariaLabel: string;
  mono?: boolean;
}

export function ContentTextarea({ value, onChange, rows, placeholder, ariaLabel, mono }: ContentTextareaProps) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={mono ? `${textareaClass} font-mono` : textareaClass}
      rows={rows}
      placeholder={placeholder}
      aria-label={ariaLabel}
    />
  );
}
