"use client";

import React from "react";
import { X, ExternalLink, Calendar, Users, FileType, Quote } from "lucide-react";
import { useRouter } from "next/navigation";
import { RagCitation } from "@/lib/api";

interface ReferencePanelProps {
  citation: RagCitation;
  onClose: () => void;
}

const formatTime = (seconds?: number | null) => {
  if (seconds == null) return "--:--";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

export function ReferencePanel({ citation, onClose }: ReferencePanelProps) {
  const router = useRouter();

  const handleOpenInNewTab = () => {
    const t = citation.start_time != null ? `?t=${citation.start_time}` : "";
    router.push(`/dashboard/meetings/${citation.meeting_id}${t}`);
  };

  return (
    <div className="flex flex-col h-full bg-card">
      <div className="p-4 border-b border-border flex items-center justify-between sticky top-0 bg-card/95 backdrop-blur-sm z-10">
        <h3 className="font-bold text-foreground flex items-center gap-2">
          <FileType size={18} className="text-brand-cta" /> 原文對照區
        </h3>
        <div className="flex items-center gap-1">
          <button
            onClick={handleOpenInNewTab}
            className="p-1.5 text-muted-foreground hover:bg-muted rounded-md transition-colors"
            title="前往會議詳情"
            aria-label="前往會議詳情"
          >
            <ExternalLink size={16} />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 text-muted-foreground hover:bg-muted rounded-md transition-colors"
            title="關閉面板"
            aria-label="關閉面板"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5 md:p-6">
        <div className="mb-6 border-b border-border pb-5">
          <h1 className="text-xl font-bold text-foreground mb-4 leading-snug">
            {citation.meeting_title}
          </h1>
          <div className="space-y-2.5">
             <div className="flex items-center gap-2.5 text-sm text-muted-foreground">
                <Calendar size={15} /> 相關會議
             </div>
             <div className="flex items-center gap-2.5 text-sm text-muted-foreground">
                <Users size={15} /> 講者：{citation.speaker || "未知 (或文字區塊)"}
             </div>
          </div>
        </div>

        <div>
          <h3 className="flex items-center gap-2 text-foreground mt-4 mb-4 font-bold">
            <Quote size={16} className="text-brand-cta" /> 搜尋到的相關段落
          </h3>

          <div className="space-y-4">
            <div className="bg-brand-cta/5 p-4 rounded-xl border border-brand-cta/20 shadow-sm relative overflow-hidden">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-brand-cta rounded-l-xl"></div>
              <div className="flex items-baseline gap-2 mb-1.5 pl-3">
                <span className="font-bold text-brand-cta text-sm">{citation.speaker || "片段"}</span>
                <span className="text-xs text-muted-foreground">{formatTime(citation.start_time)} - {formatTime(citation.end_time)}</span>
              </div>
              <p className="text-foreground/90 text-[15px] leading-relaxed pl-3 whitespace-pre-wrap">
                {citation.content}
              </p>
            </div>
            {citation.similarity > 0 && (
              <div className="text-right text-xs text-muted-foreground mt-2">
                搜尋相似度吻合：{(citation.similarity * 100).toFixed(1)}%
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
