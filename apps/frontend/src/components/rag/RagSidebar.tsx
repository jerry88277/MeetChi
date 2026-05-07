"use client";

import React from "react";
import { ChevronLeft, Plus, MessageSquare } from "lucide-react";

/**
 * RagSidebar — 全螢幕 RagWorkspace 左側邊欄
 *
 * 目前歷史紀錄為空狀態。後續若導入「對話 thread 持久化」API
 * （後端 /api/v1/rag/conversations 尚未實作）再串接。
 */
export function RagSidebar({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex flex-col h-full bg-brand-navy dark:bg-slate-950 text-white shadow-inner">
      <div className="p-4 border-b border-white/10 flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-white/70 hover:text-white transition-colors text-sm"
        >
          <ChevronLeft size={16} /> 返回所有會議
        </button>
      </div>

      <div className="p-4 flex-1 overflow-y-auto mt-2">
        <button
          disabled
          title="多輪對話尚未持久化"
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-brand-cta/60 text-white rounded-xl shadow font-medium mb-6 cursor-not-allowed opacity-60"
        >
          <Plus size={18} /> 新增知識庫對話
        </button>

        <h3 className="text-xs font-semibold text-white/50 mb-3 px-2 uppercase tracking-wide">
          歷史紀錄
        </h3>

        {/* 空狀態：尚未串接 conversation 持久化 API */}
        <div className="px-3 py-6 text-center text-white/40 text-xs flex flex-col items-center gap-2">
          <MessageSquare size={20} className="opacity-50" />
          <span>尚無歷史對話</span>
          <span className="text-white/30 leading-relaxed">
            目前對話僅保留於本次階段
          </span>
        </div>
      </div>
    </div>
  );
}
