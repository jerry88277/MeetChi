"use client";

import React from 'react';
import {
    ChevronRight,
    FileText,
    CheckCircle2,
    Loader2,
    AlertCircle,
    RefreshCw,
    Trash2,
    Download,
    ChevronDown,
} from 'lucide-react';
import type { Meeting } from '@/types/meeting';
import { exportAsTxt, exportAsSrt, exportAsJson } from '@/lib/export';

interface DetailViewProps {
    meeting: Meeting | null;
    onBack: () => void;
    onRegenerateSummary?: (meetingId: string) => void;
    isRegenerating?: boolean;
    onDelete?: (meetingId: string) => void;
    isDeleting?: boolean;
}

export const DetailView = ({ meeting, onBack, onRegenerateSummary, isRegenerating = false, onDelete, isDeleting = false }: DetailViewProps) => {
    if (!meeting) return null;

    const canRegenerate = meeting.status !== 'processing' && onRegenerateSummary;
    const needsSummary = !meeting.summary || meeting.status === 'failed';

    return (
        <div className="h-full flex flex-col bg-card">
            <div className="border-b border-border px-6 py-4 flex items-center gap-4 bg-card sticky top-0 z-10">
                <button onClick={onBack} className="p-2 hover:bg-muted rounded-full text-muted-foreground transition-colors">
                    <ChevronRight size={24} className="rotate-180" />
                </button>
                <div className="flex-1">
                    <h2 className="text-xl font-bold text-foreground">{meeting.title}</h2>
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                        <span>{meeting.date}</span>
                        <span className="w-1 h-1 rounded-full bg-border"></span>
                        <span>{meeting.duration}</span>
                    </div>
                </div>
                {/* Export dropdown */}
                <div className="relative group">
                    <button
                        className="flex items-center gap-1 px-3 py-2 text-sm text-muted-foreground hover:text-brand-cta hover:bg-brand-cta/10 rounded-lg transition-colors"
                        title="匯出"
                    >
                        <Download size={18} />
                        <span className="hidden sm:inline">匯出</span>
                        <ChevronDown size={14} />
                    </button>
                    <div className="absolute right-0 top-full mt-1 w-40 bg-card border border-border rounded-xl shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-20">
                        <button onClick={() => exportAsTxt(meeting)} className="w-full px-4 py-2.5 text-sm text-left text-foreground/70 hover:bg-brand-cta/10 hover:text-brand-cta rounded-t-xl transition-colors">
                            📄 TXT 純文字
                        </button>
                        <button onClick={() => exportAsSrt(meeting)} disabled={meeting.transcript.length === 0} className="w-full px-4 py-2.5 text-sm text-left text-foreground/70 hover:bg-brand-cta/10 hover:text-brand-cta transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                            🎬 SRT 字幕
                        </button>
                        <button onClick={() => exportAsJson(meeting)} className="w-full px-4 py-2.5 text-sm text-left text-foreground/70 hover:bg-brand-cta/10 hover:text-brand-cta rounded-b-xl transition-colors">
                            📋 JSON 結構化
                        </button>
                    </div>
                </div>
                {/* Delete button */}
                {onDelete && (
                    <button
                        onClick={() => onDelete(meeting.id)}
                        disabled={isDeleting}
                        className="p-2 text-status-error/60 hover:text-status-error hover:bg-status-error/10 rounded-full transition-colors disabled:opacity-50"
                        title="刪除會議"
                    >
                        {isDeleting ? <Loader2 size={20} className="animate-spin" /> : <Trash2 size={20} />}
                    </button>
                )}
            </div>

            <div className="flex-1 overflow-hidden flex flex-col md:flex-row">
                <div className="flex-1 overflow-y-auto p-6 md:p-8 border-r border-border bg-surface">
                    <div className="max-w-3xl mx-auto space-y-8">
                        <section>
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                                    <FileText size={16} /> 會議摘要
                                </h3>
                                {canRegenerate && (
                                    <button
                                        onClick={() => onRegenerateSummary(meeting.id)}
                                        disabled={isRegenerating}
                                        className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-brand-cta bg-brand-cta/10 rounded-lg hover:bg-brand-cta/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                    >
                                        {isRegenerating ? (
                                            <>
                                                <Loader2 size={12} className="animate-spin" />
                                                生成中...
                                            </>
                                        ) : (
                                            <>
                                                <RefreshCw size={12} />
                                                {needsSummary ? '生成摘要' : '重新生成'}
                                            </>
                                        )}
                                    </button>
                                )}
                            </div>
                            <div className="bg-card p-6 rounded-xl border border-border shadow-sm leading-relaxed text-foreground/80">
                                {meeting.status === 'pending' ? (
                                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                                        <FileText className="h-8 w-8 text-status-warning mb-2" />
                                        <p>等待處理</p>
                                        <p className="text-xs mt-1">音檔已上傳，排隊等待 AI 轉錄中...</p>
                                    </div>
                                ) : meeting.status === 'processing' ? (
                                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                                        <Loader2 className="h-8 w-8 animate-spin text-brand-cta mb-2" />
                                        <p>AI 正在轉錄與生成摘要中</p>
                                        <p className="text-xs mt-1">2 小時音檔約需 10-20 分鐘</p>
                                    </div>
                                ) : meeting.status === 'failed' ? (
                                    <div className="flex flex-col items-center justify-center py-8 text-status-error">
                                        <AlertCircle className="h-8 w-8 mb-2" />
                                        <p>摘要生成失敗</p>
                                        <p className="text-xs mt-1">請點擊「重新生成」按鈕重試</p>
                                    </div>
                                ) : meeting.summary ? (
                                    meeting.summary
                                ) : (
                                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                                        <FileText className="h-8 w-8 mb-2" />
                                        <p>尚無摘要</p>
                                        <p className="text-xs mt-1">點擊「生成摘要」開始</p>
                                    </div>
                                )}
                            </div>
                        </section>

                        <section>
                            <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4 flex items-center gap-2">
                                <CheckCircle2 size={16} /> 待辦事項 (Action Items)
                            </h3>
                            <div className="space-y-3">
                                {meeting.actionItems && meeting.actionItems.length > 0 ? (
                                    meeting.actionItems.map(item => (
                                        <div key={item.id} className="flex items-start gap-3 bg-card p-4 rounded-xl border border-border shadow-sm hover:shadow-md transition-shadow">
                                            <div className="mt-1 w-5 h-5 rounded border-2 border-border cursor-pointer hover:border-brand-cta transition-colors"></div>
                                            <div className="flex-1">
                                                <p className="text-foreground font-medium">{item.text}</p>
                                                <div className="flex items-center gap-3 mt-2 text-xs">
                                                    <span className="bg-brand-cta/15 text-brand-cta px-2 py-0.5 rounded font-medium">{item.assignee}</span>
                                                    <span className="text-muted-foreground">Due: {item.due}</span>
                                                </div>
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    <p className="text-muted-foreground text-sm italic ml-2">無待辦事項或尚未生成。</p>
                                )}
                            </div>
                        </section>
                    </div>
                </div>

                <div className="md:w-[400px] lg:w-[480px] flex flex-col bg-card">
                    <div className="p-4 border-b border-border bg-card">
                        <h3 className="font-bold text-foreground">逐字稿紀錄</h3>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-6">
                        {meeting.transcript && meeting.transcript.length > 0 ? (
                            meeting.transcript.map((line, idx) => (
                                <div key={idx} className="group flex gap-4">
                                    <div className="w-12 text-xs text-muted-foreground font-mono pt-1 text-right flex-shrink-0 group-hover:text-brand-cta cursor-pointer transition-colors">
                                        {line.time}
                                    </div>
                                    <div>
                                        <div className="text-xs font-bold text-foreground mb-1">{line.speaker}</div>
                                        <p className="text-foreground/70 text-sm leading-relaxed hover:bg-brand-highlight/10 rounded px-1 -ml-1 transition-colors cursor-pointer">
                                            {line.text}
                                        </p>
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div className="text-center py-10 text-muted-foreground">
                                <p>尚無逐字稿內容</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
