"use client";

import React, { useState } from "react";
import { ChevronRight, MessageSquare, Sparkles } from "lucide-react";
import { Panel, Group, Separator } from "react-resizable-panels";
import { ChatPanel } from "./ChatPanel";
import { ReferencePanel } from "./ReferencePanel";
import { RagCitation } from "@/lib/api";
import { useEscape } from "@/hooks/useEscape";

interface RagWorkspaceProps {
  onBack: () => void;
}

/**
 * RagWorkspace — ChiMemo 工作區
 *
 * 重設計（2026-05-10 / DDG conformity audit）：
 *  - 套用標準頁面 header (sticky)，含 back chevron + 標題 + AI badge
 *    與 DashboardView / DetailView / SettingsView 的 header pattern 對齊
 *  - 拿掉舊的全螢幕 dark-navy RagSidebar 左側欄（功能僅有空狀態歷史紀錄
 *    與 back，全域 Sidebar 已提供更好替代）
 *  - 全部色彩改為 DDG semantic token（bg-card / bg-surface / border-border）
 *    對齊 docs/design/DDG-CHIMEI.md
 *  - 雙 pane：ChatPanel (主) + ReferencePanel (右側，點引用才出現)
 *  - Esc：有引用 → 收 reference panel；沒引用 → 返回 dashboard
 */
export function RagWorkspace({ onBack }: RagWorkspaceProps) {
  const [activeCitation, setActiveCitation] = useState<RagCitation | null>(null);

  useEscape(() => {
    if (activeCitation) setActiveCitation(null);
    else onBack();
  });

  return (
    <div className="h-full flex flex-col bg-card">
      {/* Sticky header — 對齊 DetailView 與其他頁面 header pattern */}
      <div className="border-b border-border px-6 py-4 flex items-center gap-4 bg-card sticky top-0 z-10">
        <button
          onClick={onBack}
          className="p-2 hover:bg-muted rounded-full text-muted-foreground transition-colors"
          aria-label="返回"
          title="返回 (Esc)"
        >
          <ChevronRight size={24} className="rotate-180" />
        </button>
        <div className="flex-1 flex items-center gap-3 min-w-0">
          <div className="bg-brand-cta/10 p-2 rounded-lg">
            <MessageSquare size={20} className="text-brand-cta" />
          </div>
          <div className="min-w-0">
            <h2 className="text-xl font-bold text-foreground">ChiMemo</h2>
            <p className="text-xs text-muted-foreground">AI 跨會議知識搜尋；點引用標籤展開原文</p>
          </div>
        </div>
        <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-brand-green/10 text-status-success border border-brand-green/30">
          <Sparkles size={12} /> AI 模式啟用
        </span>
      </div>

      {/* Body — 雙 pane resizable layout */}
      <div className="flex-1 overflow-hidden bg-surface">
        <Group orientation="horizontal" className="w-full h-full">
          <Panel id="rag-chat" className="bg-surface h-full flex flex-col" defaultSize={activeCitation ? 60 : 100} minSize={30}>
            <ChatPanel onCitationClick={(citation) => setActiveCitation(citation)} />
          </Panel>

          {activeCitation && (
            <>
              <Separator
                id="rag-sep"
                className="w-1 bg-border hover:bg-brand-cta transition-colors duration-200 cursor-col-resize active:bg-brand-cta"
              />
              <Panel
                id="rag-reference"
                defaultSize={40}
                minSize={25}
                collapsible
                className="border-l border-border bg-card h-full flex flex-col"
              >
                <ReferencePanel
                  citation={activeCitation}
                  onClose={() => setActiveCitation(null)}
                />
              </Panel>
            </>
          )}
        </Group>
      </div>
    </div>
  );
}
