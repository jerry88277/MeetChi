"use client";

import React, { useState, useEffect } from 'react';
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
    Edit2,
    Check,
    X,
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

export const DetailView = ({ meeting, onBack, onRegenerateSummary, onRegenerateTranscript, isRegenerating = false, onDelete, isDeleting = false }: DetailViewProps) => {
    const searchParams = useSearchParams();
    const [templates, setTemplates] = useState<TemplateDTO[]>([]);
    const [selectedTemplate, setSelectedTemplate] = useState('general');
    const [showTemplateSelector, setShowTemplateSelector] = useState(false);
    const [summaryVersions, setSummaryVersions] = useState<SummaryVersionDTO[]>([]);
    const [showVersions, setShowVersions] = useState(false);

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

    // Fetch summary versions & audio url when meeting changes
    useEffect(() => {
        if (meeting?.id) {
            api.getSummaryVersions(meeting.id)
                .then(setSummaryVersions)
                .catch(() => setSummaryVersions([]));
                
            // Fetch playback URL
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
            // Copy existing mappings
            if (meeting.speakerMappings) {
                for (const [id, m] of Object.entries(meeting.speakerMappings)) {
                    updatedMappings[id] = { display_name: m.display_name, role: m.role, color: m.color };
                }
            }
            // Update the edited speaker
            updatedMappings[editingSpeakerId] = {
                display_name: editName.trim() || editingSpeakerId,
                role: editRole.trim(),
                color: meeting.speakerMappings?.[editingSpeakerId]?.color,
            };
            await api.updateSpeakerMappings(meeting.id, updatedMappings);
            // Refresh to show updated labels
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
        // e.g., "00:01:23,450" or "01:23"
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
        audioRef.current.currentTime = parseTimeToSeconds(timeStr);
        audioRef.current.play().catch(e => console.error("Playback failed:", e));
    };

    useEffect(() => {
        const timestamp = searchParams.get('t');
        if (timestamp && audioRef.current && audioUrl) {
            const timeNum = parseFloat(timestamp);
            if (!isNaN(timeNum)) {
                audioRef.current.currentTime = timeNum;
                // auto-play
                audioRef.current.play().catch(e => console.error("Auto playback failed:", e));
            }
        }
    }, [searchParams, audioUrl]);

    if (!meeting) return null;

    const canRegenerate = meeting.status !== 'processing' && onRegenerateSummary;
    const needsSummary = !meeting.summary || meeting.status === 'failed';

    // Phase 8.1.3: Resolve speaker display name and color
    const getSpeakerDisplay = (speakerId: string) => {
        const mapping = meeting.speakerMappings?.[speakerId];
        return {
            name: mapping?.display_name || speakerId,
            color: mapping?.color || 'var(--brand-cta)',
            role: mapping?.role || '',
        };
    };

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
                                    <div className="flex items-center gap-2">
                                        {/* Template selector */}
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
                                        {/* Regenerate button */}
                                        <button
                                            onClick={() => onRegenerateSummary(meeting.id, selectedTemplate)}
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
                                    </div>
                                )}
                            </div>
                            <div className="bg-card p-6 rounded-xl border border-border shadow-sm leading-relaxed text-foreground/80">
                                {meeting.status === 'pending' ? (
                                    <div className="flex flex-col items-center justify-center py-12 px-4 bg-muted/30 rounded-xl border border-dashed border-muted">
                                        <div className="relative mb-6">
                                            <div className="absolute -inset-4 bg-status-warning/10 rounded-full animate-pulse"></div>
                                            <div className="relative bg-status-warning/20 p-4 rounded-full">
                                                <FileText className="h-10 w-10 text-status-warning" />
                                            </div>
                                        </div>
                                        <h4 className="text-xl font-bold text-foreground mb-2">已進入排程佇列</h4>
                                        <p className="text-sm text-muted-foreground text-center max-w-md">
                                            系統正在調度運算資源。一旦準備就緒，會自動開始進行語音轉錄，請保持此頁面開啟或稍後回來查看。
                                        </p>
                                        
                                        <div className="mt-8 w-full max-w-sm flex items-center gap-2">
                                            <div className="h-2 w-1/3 bg-status-warning/60 rounded animate-pulse"></div>
                                            <div className="h-2 w-1/3 bg-muted rounded"></div>
                                            <div className="h-2 w-1/3 bg-muted rounded"></div>
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-2 font-mono">Status: QUEUED</p>
                                    </div>
                                ) : meeting.status === 'processing' ? (
                                    <div className="flex flex-col py-6 px-4">
                                        <div className="flex items-center gap-4 mb-8">
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
                                                    <span>正在處理音訊，依據長度可能需要 1~10 分鐘，請稍候。</span>
                                                </p>
                                            </div>
                                        </div>
                                        
                                        <div className="space-y-4 w-full">
                                            <div className="h-4 bg-muted/80 rounded-md animate-pulse w-3/4"></div>
                                            <div className="h-4 bg-muted/80 rounded-md animate-pulse w-full"></div>
                                            <div className="h-4 bg-muted/80 rounded-md animate-pulse w-5/6"></div>
                                            <div className="h-4 bg-muted/60 rounded-md animate-pulse w-2/3 mt-4"></div>
                                            <div className="h-4 bg-muted/40 rounded-md animate-pulse w-1/2"></div>
                                        </div>
                                    </div>
                                ) : meeting.status === 'failed' ? (
                                    <div className="flex flex-col items-center justify-center py-8 text-status-error">
                                        <AlertCircle className="h-8 w-8 mb-4" />
                                        <p className="text-lg font-semibold mb-1">處理失敗</p>
                                        <p className="text-sm text-foreground/70 mb-6 max-w-sm text-center">
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

                        {/* Phase D: Summary Version History */}
                        {summaryVersions.length > 0 && (
                            <section>
                                <button
                                    onClick={() => setShowVersions(!showVersions)}
                                    className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors mb-2"
                                >
                                    <RefreshCw size={12} />
                                    <span>{summaryVersions.length} 個歷史版本</span>
                                    <ChevronDown size={12} className={`transition-transform ${showVersions ? 'rotate-180' : ''}`} />
                                </button>
                                {showVersions && (
                                    <div className="space-y-2 mb-4">
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
                            </section>
                        )}

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
                    {/* Phase 8.1.3: Speaker Legend Bar (Editable) */}
                    {meeting.speakerMappings && Object.keys(meeting.speakerMappings).length > 0 && (
                        <div className="px-4 py-2.5 border-b border-border">
                            <div className="flex flex-wrap items-center gap-2">
                                {Object.entries(meeting.speakerMappings).map(([id, mapping]) => (
                                    editingSpeakerId === id ? (
                                        <div key={id} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-muted border border-brand-cta/30">
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

                    <div className="p-4 border-b border-border bg-card">
                        <h3 className="font-bold text-foreground">逐字稿紀錄</h3>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-6">
                        {meeting.transcript && meeting.transcript.length > 0 ? (
                            meeting.transcript.map((line, idx) => {
                                const speaker = getSpeakerDisplay(line.speaker);
                                return (
                                    <div key={idx} className="group flex gap-4">
                                        <div 
                                            onClick={() => handleTimestampClick(line.time)}
                                            className="w-12 text-xs text-muted-foreground font-mono pt-1 text-right flex-shrink-0 group-hover:text-brand-cta cursor-pointer transition-colors"
                                            title="點擊播放這段發言"
                                        >
                                            {line.time}
                                        </div>
                                        <div>
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
                                            <p className="text-foreground/70 text-sm leading-relaxed hover:bg-brand-highlight/10 rounded px-1 -ml-1 transition-colors cursor-pointer"
                                                style={{ borderLeft: `2px solid ${speaker.color}30`, paddingLeft: '8px' }}
                                            >
                                                {line.text}
                                            </p>
                                        </div>
                                    </div>
                                );
                            })
                        ) : (
                            <div className="text-center py-10 text-muted-foreground">
                                <p>尚無逐字稿內容</p>
                            </div>
                        )}
                    </div>

                    {/* Phase D: Audio Player at bottom of the transcript pane */}
                    {audioUrl && (
                        <div className="p-3 bg-card border-t border-border shadow-[0_-4px_10px_rgba(0,0,0,0.05)] z-10 shrink-0">
                            <audio 
                                ref={audioRef}
                                src={audioUrl}
                                controls
                                className="w-full h-10"
                            />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
