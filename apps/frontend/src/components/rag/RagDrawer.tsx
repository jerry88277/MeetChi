"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { X, MessageSquare, Maximize2 } from "lucide-react";
import { ChatPanel } from "./ChatPanel";
import { RagCitation } from "@/lib/api";
import { useEscape } from "@/hooks/useEscape";

interface RagDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  /** 點 "展開全頁" 切到 RagWorkspace；可選 */
  onExpand?: () => void;
}

/**
 * RagDrawer — 從 Dashboard 任一頁透過 FAB 召喚的快速 RAG 抽屜。
 *
 * 與 RagWorkspace 的差異：
 *  - 全螢幕的 RagWorkspace 有右側 ReferencePanel 可展開原文。
 *  - Drawer 模式空間有限，點引用直接跳到對應會議的 detail view，
 *    並透過 `?t=<start_time>` deep link 自動 seek 到引用時間戳。
 *  - 同時關閉 drawer，讓使用者立即看到完整內文與音訊播放。
 *
 * UX (PR19):
 *  - Esc 鍵可關
 *  - 加 header 標題避免 user 看不出此 drawer 是什麼
 *  - 提供「展開全頁」按鈕統一兩個 RAG 入口的 UX path
 */
export function RagDrawer({ isOpen, onClose, onExpand }: RagDrawerProps) {
  const router = useRouter();
  useEscape(onClose, isOpen);

  const handleCitationClick = (citation: RagCitation) => {
    const t = citation.start_time != null ? `?t=${citation.start_time}` : "";
    router.push(`/dashboard/meetings/${citation.meeting_id}${t}`);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-foreground/20 backdrop-blur-sm z-40 transition-opacity"
        onClick={onClose}
        aria-label="關閉助理"
      />

      {/* Drawer */}
      <div
        className="fixed inset-y-0 right-0 w-[440px] max-w-[90vw] bg-card shadow-2xl flex flex-col z-50 animate-in slide-in-from-right duration-300"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rag-drawer-title"
      >
        {/* Header — 補標題避免 user 看不出 drawer 用途 */}
        <header className="flex items-center justify-between px-4 py-3 border-b border-border bg-card/95 backdrop-blur-sm">
          <div className="flex items-center gap-2 min-w-0">
            <MessageSquare className="w-5 h-5 text-brand-cta shrink-0" />
            <div className="min-w-0">
              <h2 id="rag-drawer-title" className="font-semibold text-foreground text-sm leading-tight">
                ChiMemo
              </h2>
              <p className="text-xs text-muted-foreground leading-tight">跨會議 AI 知識搜尋</p>
            </div>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {onExpand && (
              <button
                onClick={onExpand}
                aria-label="展開全頁"
                title="展開全頁（看完整原文引用）"
                className="p-1.5 rounded-md text-muted-foreground hover:bg-muted transition-colors active:scale-95"
              >
                <Maximize2 size={16} />
              </button>
            )}
            <button
              onClick={onClose}
              aria-label="關閉助理 (Esc)"
              title="關閉 (Esc)"
              className="p-1.5 rounded-md text-muted-foreground hover:bg-muted transition-colors active:scale-95"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-hidden">
          <ChatPanel onCitationClick={handleCitationClick} />
        </div>
      </div>
    </>
  );
}
