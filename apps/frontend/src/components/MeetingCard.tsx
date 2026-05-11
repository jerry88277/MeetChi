"use client";

import React from 'react';
import {
    Calendar,
    Clock,
    Users,
    CheckCircle2,
    Zap,
    AlertTriangle,
    Loader2,
    AlertCircle,
} from 'lucide-react';
import type { Meeting } from '@/types/meeting';

interface MeetingCardProps {
    meeting: Meeting;
    onClick: (meeting: Meeting) => void;
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
    general:    { label: '通用',    color: 'bg-brand-cta/10 text-brand-cta' },
    sales_bant: { label: '銷售',    color: 'bg-brand-orange/10 text-brand-orange' },
    hr_star:    { label: '面試',    color: 'bg-brand-violet/10 text-brand-violet' },
    rd:         { label: '研發',    color: 'bg-brand-azure/10 text-brand-azure' },
    executive_brief: { label: '主管', color: 'bg-brand-coral/10 text-brand-coral' },
};

const STATUS_CONFIG = {
    completed: {
        color: 'bg-status-success/15 text-status-success',
        border: 'border-l-status-success',
        label: '已完成',
    },
    processing: {
        color: 'bg-status-warning/15 text-status-warning',
        border: 'border-l-status-warning',
        label: 'AI 處理中',
    },
    failed: {
        color: 'bg-status-error/15 text-status-error',
        border: 'border-l-status-error',
        label: '處理失敗',
    },
    pending: {
        color: 'bg-muted text-muted-foreground',
        border: 'border-l-muted-foreground',
        label: '等待處理',
    },
};

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

export const MeetingCard = ({ meeting, onClick }: MeetingCardProps) => {
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

    return (
        <div
            onClick={() => onClick(meeting)}
            className={`group bg-card border border-border rounded-xl cursor-pointer hover:shadow-lg hover:border-brand-cta/30 transition-all border-l-4 active:scale-[0.99] ${config.border}`}
            title={`Meeting ID: ${meeting.id}`}
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
                        <h3 className="font-bold text-foreground group-hover:text-brand-cta transition-colors break-words">
                            {meeting.title}
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
                    {config.label}
                </span>
            </div>

            {/* 顆粒中：TL;DR */}
            {tldr && (
                <p className="px-5 mt-3 text-foreground/80 text-sm line-clamp-2 leading-relaxed">
                    {tldr}
                </p>
            )}
            {meeting.status === 'pending' && (
                <p className="px-5 mt-3 text-sm text-muted-foreground italic">
                    音檔已上傳，等待 AI 開始處理…
                </p>
            )}
            {meeting.status === 'processing' && (
                <p className="px-5 mt-3 text-sm text-muted-foreground flex items-center gap-1.5">
                    <Loader2 size={14} className="animate-spin text-status-warning" />
                    AI 正在分析會議內容…
                </p>
            )}
            {meeting.status === 'failed' && (
                <p className="px-5 mt-3 text-sm text-status-error flex items-center gap-1.5">
                    <AlertCircle size={14} />
                    處理失敗，點擊查看詳情並重試
                </p>
            )}

            {/* 顆粒細：計數 chips（只在 completed 顯示） */}
            {meeting.status === 'completed' && (
                <div className="px-5 mt-4 mb-4 flex items-center gap-3 text-xs">
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
            {meeting.status !== 'completed' && <div className="h-4" />}
        </div>
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
