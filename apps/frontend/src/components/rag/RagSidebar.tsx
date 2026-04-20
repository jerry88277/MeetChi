"use client";

import React from "react";
import { ChevronLeft, Plus, MessageSquare } from "lucide-react";

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
        <button className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-brand-cta text-white rounded-xl shadow hover:bg-brand-cta/90 transition-all font-medium mb-6">
          <Plus size={18} /> 新增知識庫對話
        </button>

        <h3 className="text-xs font-semibold text-white/50 mb-3 px-2 uppercase tracking-wide">
          歷史紀錄
        </h3>

        <div className="space-y-1">
          <button className="w-full flex flex-col text-left px-3 py-2 rounded-lg bg-white/10 text-white cursor-default">
            <span className="text-sm font-medium flex items-center gap-2">
               <MessageSquare size={14} className="text-brand-highlight" /> 產品架構規劃與討論
            </span>
            <span className="text-xs text-white/50 mt-1 pl-6">剛才</span>
          </button>
          <button className="w-full flex flex-col text-left px-3 py-2 rounded-lg hover:bg-white/5 text-white/70 transition-colors">
            <span className="text-sm font-medium">關於行銷週會的重點提問</span>
            <span className="text-xs text-white/40 mt-1 pl-6">昨天</span>
          </button>
        </div>
      </div>
    </div>
  );
}
