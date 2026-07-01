"use client";

import React, { useState, useRef, useEffect } from 'react';
import {
    Calendar,
    Clock,
    Users,
    CheckCircle2,
    Zap,
    AlertTriangle,
    Loader2,
    AlertCircle,
    Pencil,
} from 'lucide-react';
import type { Meeting } from '@/types/meeting';

interface MeetingCardProps {
    meeting: Meeting;
    onClick: (meeting: Meeting) => void;
    onRename?: (meetingId: string, newTitle: string) => void;
}

/**
 * MeetingCard — PR23 (Sprint 2b) 重設計，依 IA agent 提案：
 *   顆粒度由大→小排序：
 *     [大] 模板 chip + 標題 + ⋯ menu
 *     [大] 日期 / 時長 / 講者 dot
 *     [中] TL;DR (一句話) — 不是線性截斷的整段 summary
 *     [細] 計數 chips (✅決策 ⚡待辦 ⚠️風險) + status badge (右下)
 *
 * 移除：
 *   - Meeting ID（user 無價值；只在 hover tooltip 提供）
 *   - 底部「查看詳情」hover label（整張卡可點，多餘）
 *   - status desc 文字（已有 border-left 顏色 + 右下 badge）
 *
 * 模板 label 對應（與 PR18 + PR21 SYSTEM_TEMPLATES 對齊）：
 */
const TEMPLATE_LABEL_MAP: Record<string, { label: string; color: string }> = {
    general:    { label: '通用',    color: 'bg-brand-chimei-teal/10 text-brand-chimei-teal' },
    sales_bant: { label: '銷售',    color: 'bg-brand-orange/10 text-brand-orange' },
    hr_star:    { label: '面試',    color: 'bg-brand-violet/10 text-brand-violet' },
    rd:         { label: '研發',    color: 'bg-brand-azure/10 text-brand-azure' },
    executive_brief: { label: '主管', color: 'bg-brand-coral/10 text-brand-coral' },
};

const STATUS_CONFIG = {
    completed: {
        color: 'bg-status-success/15 text-status-success border border-status-success/30',
        border: 'border-l-status-success',
        label: '已完成',
    },
    processing: {
        color: 'bg-brand-chimei-orange/15 text-brand-chimei-orange border border-brand-chimei-orange/30',
        border: 'border-l-brand-chimei-orange',
        label: 'AI 處理中',
    },
    transcribed: {
        color: 'bg-brand-azure/15 text-brand-azure border border-brand-azure/30',
        border: 'border-l-brand-azure',
        label: '轉錄完成',
    },
    failed: {
        color: 'bg-status-error/15 text-status-error border border-status-error/30',
        border: 'border-l-status-error',
        label: '處理失敗',
    },
    pending: {
        color: 'bg-brand-azure/15 text-brand-azure border border-brand-azure/30',
        border: 'border-l-brand-azure',
        label: '等待處理',
    },
};

/** Processing stage labels and progress for the pipeline indicator */
const STAGE_CONFIG: Record<string, { label: string; desc: string; progress: string }> = {
    queued:       { label: '排隊中',    desc: '等待前方會議處理完畢',                    progress: '15%' },
    transcribing: { label: '轉錄中',    desc: '正在將語音轉換為逐字稿',                  progress: '50%' },
    diarizing:    { label: '辨識講者',  desc: '正在辨識不同講者身份',                    progress: '65%' },
    summarizing:  { label: '生成摘要中', desc: '正在整理決策、待辦與風險',                  progress: '85%' },
};

function stageLabel(stage?: string | null): string {
    return STAGE_CONFIG[stage ?? '']?.label ?? 'AI 處理中';
}

function ProcessingStageIndicator({ stage }: { stage?: string | null }) {
    const config = STAGE_CONFIG[stage ?? ''];
    const steps = ['queued', 'transcribing', 'diarizing', 'summarizing'] as const;

    return (
        <div className="space-y-1.5">
            <p className="text-sm text-foreground/70 flex items-center gap-1.5 font-medium">
                <Loader2 size={14} className="animate-spin text-brand-chimei-orange" />
                {config?.desc ?? '正在處理中'}
            </p>
            <div className="flex items-center gap-1.5">
                {steps.map((s) => {
                    const isActive = s === stage;
                    const isDone = steps.indexOf(s) < steps.indexOf(stage as typeof steps[number]);
                    return (
                        <span
                            key={s}
                            className={`text-[10px] px-1.5 py-0.5 rounded ${
                                isActive
                                    ? 'bg-brand-chimei-orange/20 text-brand-chimei-orange font-semibold'
                                    : isDone
                                        ? 'bg-status-success/15 text-status-success'
                                        : 'bg-muted text-muted-foreground'
                            }`}
                        >
                            {isDone ? '✓ ' : ''}{STAGE_CONFIG[s].label}
                        </span>
                    );
                })}
            </div>
        </div>
    );
}

/** 講者 dot 用 speakerMappings.color；最多顯示 5 點 + 「+N」溢出 */
function SpeakerDots({ meeting }: { meeting: Meeting }) {
    const count = meeting.speakerCount ?? 0;
    if (!count) return null;

    const colors = meeting.speakerMappings
        ? Object.values(meeting.speakerMappings).map((m) => m.color)
        : [];

    const dots: string[] = [];
    const palette = colors.length ? colors : ['#2D428B', '#FF6B35', '#06D6A0', '#F2C14E', '#4D5CB7'];
    for (let i = 0; i < Math.min(count, 5); i++) {
        dots.push(palette[i % palette.length]);
    }
    const overflow = count - 5;

    return (
        <span className="flex items-center gap-1" title={`${count} 位講者`}>
            <Users size={14} className="text-muted-foreground" />
            <span className="flex -space-x-1">
                {dots.map((c, i) => (
                    <span
                        key={i}
                        className="w-2.5 h-2.5 rounded-full border border-card"
                        style={{ backgroundColor: c }}
                    />
                ))}
            </span>
            {overflow > 0 && (
                <span className="text-[10px] text-muted-foreground">+{overflow}</span>
            )}
        </span>
    );
}

/** Compute and display ETA for processing meetings — recalculates on each render (10s polling) */
function ProcessingEta({ meeting }: { meeting: Meeting }) {
    const dur = meeting.durationSeconds;
    if (!dur || dur <= 0) return null;

    // Historical avg: long meetings (>20min parallel ASR) ≈ 0.15x; short ≈ 0.35x
    const ratio = dur > 1200 ? 0.15 : 0.35;
    // Processing time (ASR + summary + embedding)
    const processingTimeSec = Math.round(dur * ratio) + 90;
    // Upload time estimate: ~1MB per 60s audio; at ~5MB/s browser upload ≈ fileSize/5
    // Simplified: for pending meetings, add ~3 min for large files
    const uploadTimeSec = meeting.status === 'pending' ? Math.min(300, Math.round(dur * 0.016)) : 0;
    const estimatedTotalSec = processingTimeSec + uploadTimeSec;

    const createdAt = new Date(meeting.createdAt).getTime();
    const elapsedSec = Math.max(0, Math.round((Date.now() - createdAt) / 1000));
    const remainingSec = Math.max(0, estimatedTotalSec - elapsedSec);

    const formatEta = (sec: number): string => {
        if (sec <= 0) return '即將完成';
        if (sec < 60) return '不到 1 分鐘';
        const min = Math.ceil(sec / 60);
        return `約 ${min} 分鐘`;
    };

    return (
        <p className="text-[11px] text-muted-foreground" title="依歷史平均推估，實際時間可能因排隊與音檔長度而不同">
            預計剩餘 {formatEta(remainingSec)}（預估）
        </p>
    );
}

/** F1 heartbeat: show elapsed time since processing started — proves system is alive */
function ProcessingHeartbeat({ meeting }: { meeting: Meeting }) {
    const [elapsed, setElapsed] = useState(0);

    useEffect(() => {
        const startTime = new Date(meeting.createdAt).getTime();
        const update = () => setElapsed(Math.round((Date.now() - startTime) / 1000));
        update();
        const id = setInterval(update, 1000);
        return () => clearInterval(id);
    }, [meeting.createdAt]);

    const min = Math.floor(elapsed / 60);
    const sec = elapsed % 60;

    return (
        <p className="text-[10px] text-muted-foreground/60 tabular-nums">
            已處理 {min > 0 ? `${min} 分 ` : ''}{sec.toString().padStart(2, '0')} 秒
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-brand-chimei-orange animate-pulse ml-1.5 align-middle" />
        </p>
    );
}

export const MeetingCard = ({ meeting, onClick, onRename }: MeetingCardProps) => {
    const config = STATUS_CONFIG[meeting.status];
    const tpl = meeting.templateName
        ? TEMPLATE_LABEL_MAP[meeting.templateName] || { label: meeting.templateName, color: 'bg-muted text-muted-foreground' }
        : null;

    const decisionsCount = meeting.decisions?.length ?? 0;
    const actionItemsCount = meeting.actionItems?.length ?? 0;
    const risksCount = meeting.risks?.length ?? 0;

    // 顆粒中：TL;DR（PR23 設計核心 — 一句話結論）
    const tldr = meeting.status === 'completed'
        ? (meeting.tldr || meeting.summary || '暫無摘要')
        : null;

    // Right-click context menu
    const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
    const [isRenaming, setIsRenaming] = useState(false);
    const [renameValue, setRenameValue] = useState(meeting.title);
    const renameInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (isRenaming) renameInputRef.current?.focus();
    }, [isRenaming]);

    // Close context menu on click outside
    useEffect(() => {
        if (!contextMenu) return;
        const close = () => setContextMenu(null);
        window.addEventListener('click', close);
        return () => window.removeEventListener('click', close);
    }, [contextMenu]);

    const handleContextMenu = (e: React.MouseEvent) => {
        e.preventDefault();
        setContextMenu({ x: e.clientX, y: e.clientY });
    };

    const handleRenameSubmit = () => {
        const trimmed = renameValue.trim();
        if (trimmed && trimmed !== meeting.title && onRename) {
            onRename(meeting.id, trimmed);
        }
        setIsRenaming(false);
    };

    return (
        <>
            <article
                role="button"
                tabIndex={0}
                onClick={() => !isRenaming && onClick(meeting)}
                onKeyDown={(e) => {
                    if ((e.key === 'Enter' || e.key === ' ') && !isRenaming) {
                        e.preventDefault();
                        onClick(meeting);
                    }
                }}
                onContextMenu={handleContextMenu}
                className={`group bg-card rounded-2xl cursor-pointer h-full flex flex-col
                    shadow-sm hover:shadow-[0_4px_24px_-4px_rgba(45,66,139,0.14)]
                    hover:border-l-brand-cta/60
                    transition-[shadow,transform,border-color] duration-200 ease-brand
                    border-l-4 active:scale-[0.98] active:duration-100 ${config.border}`}
                aria-label={`會議: ${meeting.title}, 狀態: ${config.label}`}
            >
            {/* 顆粒大 1：模板 chip + 標題 + status badge */}
            <div className="flex justify-between items-start gap-3 px-5 pt-5">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                        {tpl && (
                            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${tpl.color}`}>
                                {tpl.label}
                            </span>
                        )}
                        {meeting.isConfidential && (
                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-status-error/10 text-status-error border border-status-error/20" title="機密會議">
                                🔒 機密
                            </span>
                        )}
            <h3 className="font-bold text-foreground group-hover:text-brand-cta transition-colors break-words line-clamp-2">
                            {isRenaming ? (
                                <input
                                    ref={renameInputRef}
                                    value={renameValue}
                                    onChange={(e) => setRenameValue(e.target.value)}
                                    onBlur={handleRenameSubmit}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') handleRenameSubmit();
                                        if (e.key === 'Escape') { setIsRenaming(false); setRenameValue(meeting.title); }
                                    }}
                                    onClick={(e) => e.stopPropagation()}
                                    className="w-full bg-muted border border-brand-cta/40 rounded px-2 py-0.5 text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-brand-cta/50"
                                />
                            ) : meeting.title}
                        </h3>
                    </div>
                    {/* 顆粒大 2：日期 / 時長 / 講者 dot */}
                    <div className="flex items-center gap-3 text-sm text-muted-foreground flex-wrap">
                        <span className="flex items-center gap-1"><Calendar size={14} /> {meeting.date}</span>
                        <span className="flex items-center gap-1"><Clock size={14} /> {meeting.duration}</span>
                        <SpeakerDots meeting={meeting} />
                    </div>
                </div>
                <span className={`text-xs font-medium px-2.5 py-1 rounded-full flex-shrink-0 ${config.color}`}>
                    {meeting.status === 'processing' && <Loader2 size={12} className="inline mr-1 animate-spin" />}
                    {meeting.status === 'processing' ? stageLabel(meeting.processingStage) : config.label}
                </span>
            </div>

            {/* Body: flex-1 fills remaining space so all cards in a grid row are equal height */}
            <div className="flex-1 min-h-[3.5rem]">
            {/* 顆粒中：TL;DR */}
            {tldr && (
                <p className="px-5 mt-3 text-foreground/80 text-sm line-clamp-2 leading-relaxed">
                    {tldr}
                </p>
            )}
            {meeting.status === 'pending' && (
                <div className="px-5 mt-3">
                    <p className="text-sm text-brand-azure flex items-center gap-1.5 italic">
                        <Loader2 size={14} className="animate-spin text-brand-azure" />
                        音檔上傳中，完成後自動開始轉錄
                    </p>
                    <ProcessingEta meeting={meeting} />
                </div>
            )}
            {meeting.status === 'processing' && (
                <div className="px-5 mt-3 space-y-2">
                    <ProcessingStageIndicator stage={meeting.processingStage} />
                    <ProcessingEta meeting={meeting} />
                    {/* U-A5: indeterminate activity bar — no fake percentage.
                        Real progress lives in the stage pills + heartbeat above/below. */}
                    <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className="h-full w-1/3 bg-brand-chimei-orange/60 rounded-full animate-indeterminate" />
                    </div>
                    <ProcessingHeartbeat meeting={meeting} />
                </div>
            )}
            {meeting.status === 'failed' && (
                <div className="px-5 mt-3 space-y-1">
                    <p className="text-sm text-status-error flex items-center gap-1.5">
                        <AlertCircle size={14} />
                        處理未完成 — 點擊查看詳情
                    </p>
                    {meeting.failureReason && (
                        <p className="text-[11px] text-status-error/70 pl-5 line-clamp-1">
                            原因：{meeting.failureReason}
                        </p>
                    )}
                    {meeting.processingStage && (
                        <p className="text-[11px] text-muted-foreground pl-5">
                            失敗階段：{STAGE_CONFIG[meeting.processingStage]?.label ?? meeting.processingStage}
                        </p>
                    )}
                </div>
            )}
            {meeting.status === 'transcribed' && (
                <div className="px-5 mt-3 space-y-1">
                    <p className="text-sm text-brand-azure font-medium flex items-center gap-1.5 animate-pulse">
                        <CheckCircle2 size={14} className="text-status-success" />
                        📄 逐字稿已可查看
                    </p>
                    <p className="text-[11px] text-muted-foreground pl-5">
                        摘要生成中，您可以先點擊查看逐字稿內容
                    </p>
                </div>
            )}
            </div>

            {/* 顆粒細：計數 chips（只在 completed 顯示） */}
            {meeting.status === 'completed' && (
                <div className="px-5 mt-4 pb-5 flex items-center gap-3 text-xs">
                    <Chip
                        icon={<CheckCircle2 size={12} />}
                        label={`${decisionsCount}`}
                        title="決策"
                        cls="text-status-success"
                    />
                    <Chip
                        icon={<Zap size={12} />}
                        label={`${actionItemsCount}`}
                        title="待辦"
                        cls="text-brand-orange"
                    />
                    <Chip
                        icon={<AlertTriangle size={12} />}
                        label={`${risksCount}`}
                        title="風險"
                        cls="text-status-error"
                    />
                </div>
            )}
            {/* 非 completed 狀態：空白佔位讓不同 status 卡片同高 */}
            {meeting.status !== 'completed' && <div className="h-5" />}
        </article>

            {/* Right-click context menu */}
            {contextMenu && (
                <div
                    className="fixed z-[300] bg-card border border-border rounded-xl shadow-xl py-1 min-w-[140px]"
                    style={{ top: contextMenu.y, left: contextMenu.x }}
                    onClick={(e) => e.stopPropagation()}
                >
                    <button
                        className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-foreground hover:bg-muted transition-colors text-left"
                        onClick={() => {
                            setContextMenu(null);
                            setRenameValue(meeting.title);
                            setIsRenaming(true);
                        }}
                    >
                        <Pencil size={14} />
                        修改名稱
                    </button>
                </div>
            )}
        </>
    );
};

function Chip({ icon, label, title, cls }: { icon: React.ReactNode; label: string; title: string; cls: string }) {
    return (
        <span className={`inline-flex items-center gap-1 ${cls}`} title={title}>
            {icon}
            <span className="font-semibold tabular-nums">{label}</span>
            <span className="text-muted-foreground/70">{title}</span>
        </span>
    );
}
