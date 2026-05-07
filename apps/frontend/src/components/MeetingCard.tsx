"use client";

import React from 'react';
import {
    Calendar,
    Clock,
    ChevronRight,
    FileText,
    Loader2,
    AlertCircle,
} from 'lucide-react';
import type { Meeting } from '@/types/meeting';

interface MeetingCardProps {
    meeting: Meeting;
    onClick: (meeting: Meeting) => void;
}

const STATUS_CONFIG = {
    completed: {
        color: 'bg-status-success/15 text-status-success',
        border: 'border-l-status-success',
        label: '已完成',
        desc: '',
    },
    processing: {
        color: 'bg-status-warning/15 text-status-warning',
        border: 'border-l-status-warning',
        label: 'AI 處理中',
        desc: '正在轉錄音檔並生成摘要',
    },
    failed: {
        color: 'bg-status-error/15 text-status-error',
        border: 'border-l-status-error',
        label: '處理失敗',
        desc: '點擊重試',
    },
    pending: {
        color: 'bg-muted text-muted-foreground',
        border: 'border-l-muted-foreground',
        label: '等待處理',
        desc: '已上傳，排隊中',
    },
};

export const MeetingCard = ({ meeting, onClick }: MeetingCardProps) => {
    const config = STATUS_CONFIG[meeting.status];

    return (
        <div
            onClick={() => onClick(meeting)}
            className={`group bg-card border border-border rounded-xl p-5 cursor-pointer hover:shadow-lg hover:border-brand-cta/30 transition-all duration-300 border-l-4 ${config.border}`}
        >
            <div className="flex justify-between items-start mb-3 gap-3">
                <div className="flex-1 min-w-0">
                    <h3 className="font-bold text-foreground group-hover:text-brand-cta transition-colors break-words">
                        {meeting.title}
                    </h3>
                    <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground flex-wrap">
                        <span className="flex items-center gap-1 font-mono text-[11px] bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded" title="Meeting ID">ID: {meeting.id}</span>
                        <span className="flex items-center gap-1"><Calendar size={14} /> {meeting.date}</span>
                        <span className="flex items-center gap-1"><Clock size={14} /> {meeting.duration}</span>
                    </div>
                </div>
                <div className="flex flex-col items-end flex-shrink-0">
                    <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${config.color}`}>
                        {meeting.status === 'processing' && <Loader2 size={12} className="inline mr-1 animate-spin" />}
                        {config.label}
                    </span>
                    {config.desc && (
                        <span className="text-[10px] text-muted-foreground mt-1">{config.desc}</span>
                    )}
                </div>
            </div>

            <p className="text-muted-foreground text-sm line-clamp-2 leading-relaxed">
                {meeting.status === 'pending'
                    ? '⏳ 音檔已上傳，等待 AI 開始處理...'
                    : meeting.status === 'processing'
                        ? '⏳ AI 正在分析會議內容，請稍候...'
                        : meeting.status === 'failed'
                            ? '❌ 處理失敗，請點擊查看詳情並重試'
                            : meeting.summary || '暫無摘要'}
            </p>

            <div className="mt-4 pt-3 border-t border-border flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {meeting.status === 'completed' && meeting.transcript.length > 0 && (
                        <span className="flex items-center gap-1"><FileText size={12} /> {meeting.transcript.length} 段落</span>
                    )}
                    {meeting.status === 'processing' && (
                        <span className="flex items-center gap-1 text-status-warning"><Loader2 size={12} className="animate-spin" /> 處理中</span>
                    )}
                    {meeting.status === 'failed' && (
                        <span className="flex items-center gap-1 text-status-error"><AlertCircle size={12} /> 需要重試</span>
                    )}
                </div>
                <div className="text-brand-cta text-sm font-medium flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    查看詳情 <ChevronRight size={16} />
                </div>
            </div>
        </div>
    );
};
