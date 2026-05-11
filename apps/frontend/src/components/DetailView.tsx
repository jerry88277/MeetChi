"use client";

import React, { useState, useEffect } from 'react';
import {
    ChevronRight,
    FileText,
    CheckCircle2,
    Loader2,
    AlertCircle,
    AlertTriangle,
    RefreshCw,
    Trash2,
    Download,
    ChevronDown,
    Edit2,
    Check,
    X,
    Target,
    Zap,
    MessageSquareQuote,
} from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import type { Meeting } from '@/types/meeting';
import { exportAsTxt, exportAsSrt, exportAsJson } from '@/lib/export';
import { api } from '@/lib/api';
import type { TemplateDTO, SummaryVersionDTO, SpeakerMappingDTO } from '@/lib/api';

interface DetailViewProps {
    meeting: Meeting | null;
    onBack: () => void;
    onRegenerateSummary?: (meetingId: string, templateName?: string) => void;
    onRegenerateTranscript?: (meetingId: string, templateName?: string) => void;
    isRegenerating?: boolean;
    onDelete?: (meetingId: string) => void;
    isDeleting?: boolean;
}

/**
 * DetailView — PR23 (Sprint 2b) 重設計：單欄垂直 IA，依 PR20 tokens + PR21 schema 新欄位。
 * 顆粒度由大→小排序：
 *   Section 1: TL;DR（一句話結論卡，brand-cta accent）
 *   Section 2: 結論三欄（🎯決策 ⚡待辦 ⚠️風險）
 *   Section 3: 完整摘要 + 版本歷史
 *   Section 4: 精選引言（meeting.keyQuotes）
 *   Section 5: 完整逐字稿（預設折疊；含 speaker legend + audio player）
 *
 * 關鍵保留行為：
 *   - Phase 8.1.3 講者編輯（內嵌於 transcript section）
 *   - Phase D version history / audio playback / ?t= deeplink 自動跳秒
 *   - regenerate / template selector / export / delete
 */
export const DetailView = ({ meeting, onBack, onRegenerateSummary, onRegenerateTranscript, isRegenerating = false, onDelete, isDeleting = false }: DetailViewProps) => {
    const searchParams = useSearchParams();
    const [templates, setTemplates] = useState<TemplateDTO[]>([]);
    const [selectedTemplate, setSelectedTemplate] = useState('general');
    const [showTemplateSelector, setShowTemplateSelector] = useState(false);
    const [summaryVersions, setSummaryVersions] = useState<SummaryVersionDTO[]>([]);
    const [showVersions, setShowVersions] = useState(false);
    // PR23：逐字稿預設折疊
    const [showTranscript, setShowTranscript] = useState(false);
    // P1 a11y：export dropdown state-driven 讓鍵盤可存取（取代 group:hover）
    const [showExportMenu, setShowExportMenu] = useState(false);

    // Phase 8.1.3: Speaker editing state
    const [editingSpeakerId, setEditingSpeakerId] = useState<string | null>(null);
    const [editName, setEditName] = useState('');
    const [editRole, setEditRole] = useState('');
    const [isSavingSpeaker, setIsSavingSpeaker] = useState(false);

    // Phase D: Audio playback state
    const [audioUrl, setAudioUrl] = useState<string | null>(null);
    const audioRef = React.useRef<HTMLAudioElement | null>(null);

    useEffect(() => {
        api.getTemplates()
            .then(setTemplates)
            .catch(() => {/* graceful — selector just won't show */});
    }, []);

    useEffect(() => {
        if (meeting?.id) {
            api.getSummaryVersions(meeting.id)
                .then(setSummaryVersions)
                .catch(() => setSummaryVersions([]));

            api.getAudioPlaybackUrl(meeting.id)
                .then(res => {
                    if (res.audio_url) setAudioUrl(res.audio_url);
                })
                .catch(err => console.error("Failed to fetch audio playback url", err));
        }
    }, [meeting?.id, meeting?.summary]);

    const handleStartEditSpeaker = (speakerId: string) => {
        if (!meeting) return;
        const mapping = meeting.speakerMappings?.[speakerId];
        setEditingSpeakerId(speakerId);
        setEditName(mapping?.display_name || speakerId);
        setEditRole(mapping?.role || '');
    };

    const handleSaveSpeaker = async () => {
        if (!meeting || !editingSpeakerId) return;
        setIsSavingSpeaker(true);
        try {
            const updatedMappings: Record<string, SpeakerMappingDTO> = {};
            if (meeting.speakerMappings) {
                for (const [id, m] of Object.entries(meeting.speakerMappings)) {
                    updatedMappings[id] = { display_name: m.display_name, role: m.role, color: m.color };
                }
            }
            updatedMappings[editingSpeakerId] = {
                display_name: editName.trim() || editingSpeakerId,
                role: editRole.trim(),
                color: meeting.speakerMappings?.[editingSpeakerId]?.color,
            };
            await api.updateSpeakerMappings(meeting.id, updatedMappings);
            window.location.reload();
        } catch (err) {
            console.error('Failed to update speaker:', err);
        } finally {
            setIsSavingSpeaker(false);
        }
    };

    const handleRestoreVersion = async (versionId: string) => {
        if (!meeting) return;
        try {
            await api.restoreSummaryVersion(meeting.id, versionId);
            window.location.reload();
        } catch (err) {
            console.error('Failed to restore version:', err);
        }
    };

    const parseTimeToSeconds = (timeStr: string): number => {
        if (!timeStr) return 0;
        const parts = timeStr.trim().split(',')[0].split(':');
        let seconds = 0;
        if (parts.length === 3) {
            seconds = parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseFloat(parts[2]);
        } else if (parts.length === 2) {
            seconds = parseInt(parts[0]) * 60 + parseFloat(parts[1]);
        }
        return seconds;
    };

    const handleTimestampClick = (timeStr: string) => {
        if (!audioRef.current) return;
        // 跳到指定時間時自動展開逐字稿（如果是從 quote 點過來）
        if (!showTranscript) setShowTranscript(true);
        audioRef.current.currentTime = parseTimeToSeconds(timeStr);
        audioRef.current.play().catch(e => console.error("Playback failed:", e));
    };

    useEffect(() => {
        const timestamp = searchParams.get('t');
        if (timestamp && audioRef.current && audioUrl) {
            const timeNum = parseFloat(timestamp);
            if (!isNaN(timeNum)) {
                audioRef.current.currentTime = timeNum;
                audioRef.current.play().catch(e => console.error("Auto playback failed:", e));
            }
        }
    }, [searchParams, audioUrl]);

    if (!meeting) return null;

    const canRegenerate = meeting.status !== 'processing' && onRegenerateSummary;
    const needsSummary = !meeting.summary || meeting.status === 'failed';

    const getSpeakerDisplay = (speakerId: string) => {
        const mapping = meeting.speakerMappings?.[speakerId];
        return {
            name: mapping?.display_name || speakerId,
            color: mapping?.color || 'var(--brand-cta)',
            role: mapping?.role || '',
        };
    };

    const decisions = meeting.decisions ?? [];
    const risks = meeting.risks ?? [];
    const actionItems = meeting.actionItems ?? [];
    const keyQuotes = meeting.keyQuotes ?? [];
    const isCompleted = meeting.status === 'completed';

    return (
        <div className="h-full flex flex-col bg-card">
            {/* Sticky header */}
            <div className="border-b border-border px-6 py-4 flex items-center gap-4 bg-card sticky top-0 z-10">
                <button onClick={onBack} className="p-2 hover:bg-muted rounded-full text-muted-foreground transition-colors">
                    <ChevronRight size={24} className="rotate-180" />
                </button>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                        <h2 className="text-xl font-bold text-foreground truncate">{meeting.title}</h2>
                        {meeting.isConfidential && (
                            <span className="shrink-0 text-xs font-semibold px-2 py-0.5 rounded-md bg-status-error/10 text-status-error border border-status-error/20" title="機密會議：後續 Phase 將鎖複製/截圖警示/浮水印">
                                🔒 機密
                            </span>
                        )}
                    </div>
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                        <span>{meeting.date}</span>
                        <span className="w-1 h-1 rounded-full bg-border"></span>
                        <span>{meeting.duration}</span>
                    </div>
                </div>
                {/* Regenerate + template */}
                {canRegenerate && (
                    <div className="hidden md:flex items-center gap-2">
                        {templates.length > 0 && (
                            <div className="relative">
                                <button
                                    onClick={() => setShowTemplateSelector(!showTemplateSelector)}
                                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-muted-foreground bg-muted/50 rounded-lg hover:bg-muted transition-colors border border-border"
                                >
                                    <FileText size={11} />
                                    <span className="max-w-[100px] truncate">
                                        {templates.find(t => t.name === selectedTemplate)?.display_name || '一般會議'}
                                    </span>
                                    <ChevronDown size={12} />
                                </button>
                                {showTemplateSelector && (
                                    <div className="absolute right-0 top-full mt-1 w-56 max-h-60 overflow-y-auto bg-card border border-border rounded-xl shadow-lg z-30">
                                        {templates.filter(t => t.is_active).map(t => (
                                            <button
                                                key={t.id}
                                                onClick={() => { setSelectedTemplate(t.name); setShowTemplateSelector(false); }}
                                                className={`w-full px-4 py-2.5 text-sm text-left flex items-center gap-2 transition-colors ${
                                                    selectedTemplate === t.name
                                                        ? 'bg-brand-cta/10 text-brand-cta'
                                                        : 'text-foreground/70 hover:bg-muted'
                                                }`}
                                            >
                                                <span className="flex-1 truncate">{t.display_name}</span>
                                                <span className="text-[10px] text-muted-foreground px-1.5 py-0.5 bg-muted rounded">{t.category}</span>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                        <button
                            onClick={() => onRegenerateSummary(meeting.id, selectedTemplate)}
                            disabled={isRegenerating}
                            className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-brand-cta bg-brand-cta/10 rounded-lg hover:bg-brand-cta/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            {isRegenerating ? (
                                <><Loader2 size={12} className="animate-spin" />生成中...</>
                            ) : (
                                <><RefreshCw size={12} />{needsSummary ? '生成摘要' : '重新生成'}</>
                            )}
                        </button>
                    </div>
                )}
                {/* Export — state-driven menu，鍵盤 + click outside 可關 */}
                <div className="relative">
                    <button
                        type="button"
                        onClick={() => setShowExportMenu(v => !v)}
                        aria-haspopup="menu"
                        aria-expanded={showExportMenu}
                        aria-label="匯出選單"
                        className="flex items-center gap-1 px-3 py-2 text-sm text-muted-foreground hover:text-brand-cta hover:bg-brand-cta/10 rounded-lg transition-colors"
                        title="匯出"
                    >
                        <Download size={18} />
                        <span className="hidden sm:inline">匯出</span>
                        <ChevronDown size={14} className={`transition-transform ${showExportMenu ? 'rotate-180' : ''}`} />
                    </button>
                    {showExportMenu && (
                        <>
                            {/* click outside backdrop */}
                            <div
                                aria-hidden="true"
                                onClick={() => setShowExportMenu(false)}
                                className="fixed inset-0 z-10"
                            />
                            <div role="menu" className="absolute right-0 top-full mt-1 w-40 bg-card border border-border rounded-xl shadow-lg z-20">
                                <button
                                    role="menuitem"
                                    onClick={() => { exportAsTxt(meeting); setShowExportMenu(false); }}
                                    className="w-full px-4 py-2.5 text-sm text-left text-foreground/70 hover:bg-brand-cta/10 hover:text-brand-cta rounded-t-xl transition-colors"
                                >
                                    📄 TXT 純文字
                                </button>
                                <button
                                    role="menuitem"
                                    onClick={() => { exportAsSrt(meeting); setShowExportMenu(false); }}
                                    disabled={meeting.transcript.length === 0}
                                    className="w-full px-4 py-2.5 text-sm text-left text-foreground/70 hover:bg-brand-cta/10 hover:text-brand-cta transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                                >
                                    🎬 SRT 字幕
                                </button>
                                <button
                                    role="menuitem"
                                    onClick={() => { exportAsJson(meeting); setShowExportMenu(false); }}
                                    className="w-full px-4 py-2.5 text-sm text-left text-foreground/70 hover:bg-brand-cta/10 hover:text-brand-cta rounded-b-xl transition-colors"
                                >
                                    📋 JSON 結構化
                                </button>
                            </div>
                        </>
                    )}
                </div>
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

            {/* Single-column scroll body — RWD widening:
                  mobile/md: max-w-3xl 保持 reading layout（行長 60-80 字符最佳）
                  xl (≥1280): max-w-5xl  — 1920×1080 的 sweet spot
                  2xl (≥1536): max-w-6xl — 4K / ultrawide 也能填滿但不貼邊 */}
            <div className="flex-1 overflow-y-auto bg-surface">
                <div className="max-w-3xl xl:max-w-5xl 2xl:max-w-6xl mx-auto px-4 sm:px-6 md:px-8 py-6 md:py-8 space-y-6 pb-32">

                    {/* === Non-completed states (pending / processing / failed) === */}
                    {meeting.status === 'pending' && (
                        <section className="bg-card p-8 rounded-xl border border-dashed border-status-warning/40 shadow-sm">
                            <div className="flex flex-col items-center justify-center text-center">
                                <div className="relative mb-6">
                                    <div className="absolute -inset-4 bg-status-warning/10 rounded-full animate-pulse"></div>
                                    <div className="relative bg-status-warning/20 p-4 rounded-full">
                                        <FileText className="h-10 w-10 text-status-warning" />
                                    </div>
                                </div>
                                <h4 className="text-xl font-bold text-foreground mb-2">已進入排程佇列</h4>
                                <p className="text-sm text-muted-foreground max-w-md">
                                    系統正在調度運算資源。一旦準備就緒，會自動開始進行語音轉錄，請保持此頁面開啟或稍後回來查看。
                                </p>
                                <div className="mt-8 w-full max-w-sm flex items-center gap-2">
                                    <div className="h-2 w-1/3 bg-status-warning/60 rounded animate-pulse"></div>
                                    <div className="h-2 w-1/3 bg-muted rounded"></div>
                                    <div className="h-2 w-1/3 bg-muted rounded"></div>
                                </div>
                                <p className="text-xs text-muted-foreground mt-2 font-mono">Status: QUEUED</p>
                            </div>
                        </section>
                    )}

                    {meeting.status === 'processing' && (
                        <section className="bg-card p-6 rounded-xl border border-border shadow-sm">
                            <div className="flex items-center gap-4 mb-6">
                                <div className="relative">
                                    <div className="absolute -inset-2 bg-brand-cta/20 rounded-full animate-ping"></div>
                                    <div className="relative bg-brand-cta/10 p-3 rounded-full">
                                        <Loader2 className="h-6 w-6 animate-spin text-brand-cta" />
                                    </div>
                                </div>
                                <div>
                                    <h4 className="text-lg font-bold text-foreground">AI 正在轉錄與生成摘要中...</h4>
                                    <p className="text-sm text-muted-foreground mt-1 flex items-center gap-2">
                                        <span className="w-2 h-2 rounded-full bg-status-warning animate-pulse"></span>
                                        <span>依音檔長度可能需要 1~10 分鐘，請稍候。</span>
                                    </p>
                                </div>
                            </div>
                            <div className="space-y-3">
                                <div className="h-4 bg-muted/80 rounded-md animate-pulse w-3/4"></div>
                                <div className="h-4 bg-muted/80 rounded-md animate-pulse w-full"></div>
                                <div className="h-4 bg-muted/80 rounded-md animate-pulse w-5/6"></div>
                                <div className="h-4 bg-muted/60 rounded-md animate-pulse w-2/3"></div>
                                <div className="h-4 bg-muted/40 rounded-md animate-pulse w-1/2"></div>
                            </div>
                        </section>
                    )}

                    {meeting.status === 'failed' && (
                        <section className="bg-card p-8 rounded-xl border border-status-error/30 shadow-sm">
                            <div className="flex flex-col items-center justify-center text-center text-status-error">
                                <AlertCircle className="h-10 w-10 mb-4" />
                                <p className="text-lg font-semibold mb-1">處理失敗</p>
                                <p className="text-sm text-foreground/70 mb-6 max-w-sm">
                                    系統在生成紀錄的過程中遇到了問題，這可能是後端資源繁忙或轉錄模型錯誤所致。
                                </p>
                                <div className="flex flex-col sm:flex-row items-center gap-3 w-full max-w-md">
                                    {onRegenerateTranscript && (
                                        <button
                                            onClick={() => onRegenerateTranscript(meeting.id, selectedTemplate)}
                                            disabled={isRegenerating}
                                            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-card border border-border hover:border-brand-cta text-foreground hover:text-brand-cta rounded-xl shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed group"
                                        >
                                            {isRegenerating ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} className="group-hover:rotate-180 transition-transform duration-500" />}
                                            <span>1. 重新從頭轉錄</span>
                                        </button>
                                    )}
                                    {onRegenerateSummary && meeting.transcript && meeting.transcript.length > 0 && (
                                        <button
                                            onClick={() => onRegenerateSummary(meeting.id, selectedTemplate)}
                                            disabled={isRegenerating}
                                            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-brand-cta text-white hover:bg-brand-cta/90 rounded-xl shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed group"
                                        >
                                            {isRegenerating ? <Loader2 size={16} className="animate-spin text-white/70" /> : <RefreshCw size={16} className="group-hover:rotate-180 transition-transform duration-500" />}
                                            <span>2. 僅重新生成摘要</span>
                                        </button>
                                    )}
                                </div>
                            </div>
                        </section>
                    )}

                    {/* === Section 1: TL;DR — 顆粒最大 === */}
                    {isCompleted && meeting.tldr && (
                        <section
                            className="relative bg-gradient-to-br from-brand-cta/5 via-card to-brand-azure/5 border border-brand-cta/20 border-l-4 border-l-brand-cta p-6 rounded-xl shadow-sm"
                            aria-label="TL;DR"
                        >
                            <p className="text-[11px] uppercase tracking-[0.2em] font-bold text-brand-cta mb-3">
                                TL;DR
                            </p>
                            <p className="text-lg md:text-xl font-medium text-foreground leading-relaxed">
                                {meeting.tldr}
                            </p>
                        </section>
                    )}

                    {/* === Section 2: 結論三欄（決策 / 待辦 / 風險） === */}
                    {isCompleted && (decisions.length > 0 || actionItems.length > 0 || risks.length > 0) && (
                        <section>
                            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">
                                結論摘要
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                <ConclusionCard
                                    icon={<Target size={16} />}
                                    title="核心決策"
                                    count={decisions.length}
                                    items={decisions}
                                    accentColor="text-status-success"
                                    bgColor="bg-status-success/5"
                                    borderColor="border-status-success/20"
                                    emptyText="本次無重大決策"
                                />
                                <ConclusionCard
                                    icon={<Zap size={16} />}
                                    title="待辦"
                                    count={actionItems.length}
                                    items={actionItems.map(a => a.assignee && a.assignee !== '待分配' ? `${a.text} — ${a.assignee}` : a.text)}
                                    accentColor="text-brand-orange"
                                    bgColor="bg-brand-orange/5"
                                    borderColor="border-brand-orange/20"
                                    emptyText="無待辦事項"
                                />
                                <ConclusionCard
                                    icon={<AlertTriangle size={16} />}
                                    title="風險"
                                    count={risks.length}
                                    items={risks}
                                    accentColor="text-status-error"
                                    bgColor="bg-status-error/5"
                                    borderColor="border-status-error/20"
                                    emptyText="未識別出風險"
                                />
                            </div>
                        </section>
                    )}

                    {/* === Section 3: 完整摘要 === */}
                    {isCompleted && meeting.summary && (
                        <section>
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                                    <FileText size={14} /> 完整摘要
                                </h3>
                                {/* mobile-only inline regenerate */}
                                {canRegenerate && (
                                    <button
                                        onClick={() => onRegenerateSummary(meeting.id, selectedTemplate)}
                                        disabled={isRegenerating}
                                        className="md:hidden flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-brand-cta bg-brand-cta/10 rounded-lg hover:bg-brand-cta/20 disabled:opacity-50 transition-colors"
                                    >
                                        {isRegenerating ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                                        重新生成
                                    </button>
                                )}
                            </div>
                            <div className="bg-card p-6 rounded-xl border border-border shadow-sm leading-relaxed text-foreground/85 whitespace-pre-wrap">
                                {meeting.summary}
                            </div>

                            {/* Phase D: Version history */}
                            {summaryVersions.length > 0 && (
                                <>
                                    <button
                                        onClick={() => setShowVersions(!showVersions)}
                                        className="mt-3 flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                                    >
                                        <RefreshCw size={12} />
                                        <span>{summaryVersions.length} 個歷史版本</span>
                                        <ChevronDown size={12} className={`transition-transform ${showVersions ? 'rotate-180' : ''}`} />
                                    </button>
                                    {showVersions && (
                                        <div className="mt-2 space-y-2">
                                            {summaryVersions.map(v => (
                                                <div key={v.id} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg border border-border text-xs">
                                                    <div className="flex items-center gap-2">
                                                        <span className="px-1.5 py-0.5 bg-brand-cta/10 text-brand-cta rounded font-medium">{v.template_name}</span>
                                                        <span className="text-muted-foreground">
                                                            {v.created_at ? new Date(v.created_at).toLocaleString('zh-TW') : '未知時間'}
                                                        </span>
                                                    </div>
                                                    <button
                                                        onClick={() => handleRestoreVersion(v.id)}
                                                        className="px-2 py-1 text-xs text-brand-cta hover:bg-brand-cta/10 rounded transition-colors"
                                                    >
                                                        還原
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}
                        </section>
                    )}

                    {/* === Section 4: 精選引言 === */}
                    {isCompleted && keyQuotes.length > 0 && (
                        <section>
                            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
                                <MessageSquareQuote size={14} /> 精選原音
                            </h3>
                            <div className="space-y-3">
                                {keyQuotes.map((q, i) => {
                                    const sd = getSpeakerDisplay(q.speaker);
                                    return (
                                        <blockquote
                                            key={i}
                                            className="bg-card p-4 rounded-xl border border-border shadow-sm border-l-4"
                                            style={{ borderLeftColor: sd.color }}
                                        >
                                            <p className="text-foreground/90 leading-relaxed italic">
                                                「{q.text}」
                                            </p>
                                            <footer className="mt-2 text-xs flex items-center gap-2" style={{ color: sd.color }}>
                                                <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ backgroundColor: sd.color }} />
                                                {sd.name}
                                                {sd.role && <span className="opacity-60">({sd.role})</span>}
                                            </footer>
                                        </blockquote>
                                    );
                                })}
                            </div>
                        </section>
                    )}

                    {/* === Section 5: 完整逐字稿（折疊） === */}
                    {isCompleted && (
                        <section>
                            <button
                                onClick={() => setShowTranscript(!showTranscript)}
                                className="w-full flex items-center justify-between p-4 bg-card rounded-xl border border-border hover:border-brand-cta/30 transition-colors"
                                aria-expanded={showTranscript}
                            >
                                <div className="flex items-center gap-2">
                                    <FileText size={16} className="text-muted-foreground" />
                                    <span className="text-sm font-bold text-foreground">完整逐字稿</span>
                                    <span className="text-xs text-muted-foreground">
                                        ({meeting.transcript?.length ?? 0} 段)
                                    </span>
                                </div>
                                <ChevronDown
                                    size={18}
                                    className={`text-muted-foreground transition-transform ${showTranscript ? 'rotate-180' : ''}`}
                                />
                            </button>

                            {showTranscript && (
                                <div className="mt-3 bg-card rounded-xl border border-border overflow-hidden">
                                    {/* Speaker legend */}
                                    {meeting.speakerMappings && Object.keys(meeting.speakerMappings).length > 0 && (
                                        <div className="px-4 py-3 border-b border-border bg-muted/20">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <span className="text-xs text-muted-foreground mr-1">講者：</span>
                                                {Object.entries(meeting.speakerMappings).map(([id, mapping]) => (
                                                    editingSpeakerId === id ? (
                                                        <div key={id} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-card border border-brand-cta/30">
                                                            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: mapping.color }} />
                                                            <input
                                                                type="text"
                                                                value={editName}
                                                                onChange={e => setEditName(e.target.value)}
                                                                className="w-20 px-1.5 py-0.5 text-xs rounded border border-border bg-card focus:border-brand-cta focus:outline-none"
                                                                placeholder="名稱"
                                                                autoFocus
                                                            />
                                                            <input
                                                                type="text"
                                                                value={editRole}
                                                                onChange={e => setEditRole(e.target.value)}
                                                                className="w-16 px-1.5 py-0.5 text-xs rounded border border-border bg-card focus:border-brand-cta focus:outline-none"
                                                                placeholder="角色"
                                                            />
                                                            <button
                                                                onClick={handleSaveSpeaker}
                                                                disabled={isSavingSpeaker}
                                                                className="p-0.5 text-status-success hover:bg-status-success/10 rounded transition-colors"
                                                            >
                                                                {isSavingSpeaker ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                                                            </button>
                                                            <button
                                                                onClick={() => setEditingSpeakerId(null)}
                                                                className="p-0.5 text-status-error hover:bg-status-error/10 rounded transition-colors"
                                                            >
                                                                <X size={12} />
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <span
                                                            key={id}
                                                            onClick={() => handleStartEditSpeaker(id)}
                                                            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium cursor-pointer hover:ring-2 hover:ring-brand-cta/30 transition-all group"
                                                            style={{
                                                                backgroundColor: `${mapping.color}18`,
                                                                color: mapping.color,
                                                                border: `1px solid ${mapping.color}40`,
                                                            }}
                                                            title="點擊編輯"
                                                        >
                                                            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: mapping.color }} />
                                                            {mapping.display_name}
                                                            {mapping.role && <span className="opacity-60">({mapping.role})</span>}
                                                            <Edit2 size={10} className="opacity-0 group-hover:opacity-60 transition-opacity" />
                                                        </span>
                                                    )
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Transcript lines */}
                                    {/* P2 RWD：mobile portrait 60vh 太矮、桌機則太擠
                                          mobile/sm: 75vh（手機螢幕窄但長，多給空間）
                                          md+: 60vh（桌機橫向有空間，較緊湊讓使用者
                                          看到下方音訊播放器） */}
                                    <div className="p-4 sm:p-5 space-y-5 max-h-[75vh] md:max-h-[60vh] overflow-y-auto">
                                        {meeting.transcript && meeting.transcript.length > 0 ? (
                                            meeting.transcript.map((line, idx) => {
                                                const speaker = getSpeakerDisplay(line.speaker);
                                                return (
                                                    <div key={idx} className="group flex gap-4">
                                                        <div
                                                            onClick={() => handleTimestampClick(line.time)}
                                                            className="w-14 text-xs text-muted-foreground font-mono pt-1 text-right flex-shrink-0 group-hover:text-brand-cta cursor-pointer transition-colors"
                                                            title="點擊播放這段發言"
                                                        >
                                                            {line.time}
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <div
                                                                className="text-xs font-bold mb-1 inline-flex items-center gap-1.5"
                                                                style={{ color: speaker.color }}
                                                            >
                                                                <span
                                                                    className="w-1.5 h-1.5 rounded-full inline-block"
                                                                    style={{ backgroundColor: speaker.color }}
                                                                />
                                                                {speaker.name}
                                                            </div>
                                                            <p
                                                                className="text-foreground/80 text-sm leading-relaxed hover:bg-brand-green/10 rounded px-2 -ml-2 transition-colors cursor-pointer"
                                                                style={{ borderLeft: `2px solid ${speaker.color}30`, paddingLeft: '10px' }}
                                                            >
                                                                {line.text}
                                                            </p>
                                                        </div>
                                                    </div>
                                                );
                                            })
                                        ) : (
                                            <div className="text-center py-8 text-muted-foreground text-sm">
                                                尚無逐字稿內容
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </section>
                    )}

                    {/* Empty fallback for completed but no summary */}
                    {isCompleted && !meeting.summary && (
                        <section className="bg-card p-8 rounded-xl border border-border shadow-sm">
                            <div className="flex flex-col items-center justify-center py-4 text-muted-foreground">
                                <FileText className="h-8 w-8 mb-2" />
                                <p>尚無摘要</p>
                                <p className="text-xs mt-1">點擊右上「生成摘要」開始</p>
                            </div>
                        </section>
                    )}
                </div>
            </div>

            {/* Sticky audio player at bottom — 對齊上方內容寬度 */}
            {audioUrl && (
                <div className="border-t border-border bg-card shadow-[0_-4px_10px_rgba(0,0,0,0.05)] z-10 shrink-0 px-4 py-3">
                    <div className="max-w-3xl xl:max-w-5xl 2xl:max-w-6xl mx-auto">
                        <audio
                            ref={audioRef}
                            src={audioUrl}
                            controls
                            className="w-full h-10"
                        />
                    </div>
                </div>
            )}
        </div>
    );
};

/** 結論卡片：決策 / 待辦 / 風險 統一外觀 */
function ConclusionCard({
    icon,
    title,
    count,
    items,
    accentColor,
    bgColor,
    borderColor,
    emptyText,
}: {
    icon: React.ReactNode;
    title: string;
    count: number;
    items: string[];
    accentColor: string;
    bgColor: string;
    borderColor: string;
    emptyText: string;
}) {
    return (
        <div className={`p-4 rounded-xl border ${borderColor} ${bgColor} flex flex-col`}>
            <div className={`flex items-center gap-2 mb-3 ${accentColor}`}>
                {icon}
                <span className="text-xs font-bold uppercase tracking-wider">{title}</span>
                <span className="ml-auto text-sm font-bold tabular-nums">{count}</span>
            </div>
            {items.length === 0 ? (
                <p className="text-xs text-muted-foreground italic">{emptyText}</p>
            ) : (
                <ul className="space-y-1.5">
                    {items.map((it, i) => (
                        <li key={i} className="text-sm text-foreground/85 flex gap-2 leading-snug">
                            <span className={`mt-1.5 w-1 h-1 rounded-full flex-shrink-0 ${accentColor}`} style={{ backgroundColor: 'currentColor' }} />
                            <span className="flex-1 break-words">{it}</span>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
