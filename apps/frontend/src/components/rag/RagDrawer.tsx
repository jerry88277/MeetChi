"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { ChatPanel } from "./ChatPanel";
import { RagCitation } from "@/lib/api";

interface RagDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * RagDrawer — 從 Dashboard 任一頁透過 FAB 召喚的快速 RAG 抽屜。
 *
 * 與 RagWorkspace 的差異：
 *  - 全螢幕的 RagWorkspace 有右側 ReferencePanel 可展開原文。
 *  - Drawer 模式空間有限，點引用直接跳到對應會議的 detail view，
 *    並透過 `?t=<start_time>` deep link 自動 seek 到引用時間戳。
 *  - 同時關閉 drawer，讓使用者立即看到完整內文與音訊播放。
 */
export function RagDrawer({ isOpen, onClose }: RagDrawerProps) {
  const router = useRouter();

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
        className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed inset-y-0 right-0 w-[440px] max-w-[90vw] bg-white dark:bg-slate-950 shadow-2xl flex flex-col z-50 animate-in slide-in-from-right duration-300">
        {/* Drawer 內專屬關閉按鈕 — ChatPanel 本身不承擔 drawer 控制 */}
        <button
          onClick={onClose}
          aria-label="關閉助理"
          className="absolute top-3 right-3 z-10 p-1.5 rounded-md text-muted-foreground hover:bg-surface dark:hover:bg-slate-800 transition-colors"
        >
          <X size={18} />
        </button>
        <ChatPanel onCitationClick={handleCitationClick} />
      </div>
    </>
  );
}
