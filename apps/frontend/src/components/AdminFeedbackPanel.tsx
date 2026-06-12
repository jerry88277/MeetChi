'use client';

/**
 * AdminFeedbackPanel — 管理員回報問題總覽
 *
 * Design decisions (design-advisor + taste-skill):
 *   - Calm table layout, Granola-inspired spacing & typography
 *   - Status pills reuse existing brand token system (azure/orange/green/red)
 *   - Severity badge with subtle left-border accent (consistent with MeetingCard)
 *   - Quick-action: click status pill to cycle → open → in_progress → fixed
 *   - Expandable row for full details (no modal clutter)
 *   - Filter bar: tab-style status filter + severity dropdown
 *   -護眼: uses global F5F7FA background, card elevation for contrast
 */

import { useEffect, useState, useCallback } from 'react';
import {
    AlertCircle, CheckCircle2, Clock, ChevronDown, ChevronRight,
    ExternalLink, MessageSquare, Filter,
} from 'lucide-react';
import { api, FeedbackRead } from '@/lib/api';

interface AdminFeedbackPanelProps {
    userUpn: string;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; next: string }> = {
    open: { label: '待處理', color: 'bg-brand-azure/15 text-brand-azure border border-brand-azure/30', next: 'in_progress' },
    in_progress: { label: '處理中', color: 'bg-brand-chimei-orange/15 text-brand-chimei-orange border border-brand-chimei-orange/30', next: 'fixed' },
    fixed: { label: '已修復', color: 'bg-status-success/15 text-status-success border border-status-success/30', next: 'open' },
    wontfix: { label: '不處理', color: 'bg-muted text-muted-foreground border border-border', next: 'open' },
    duplicate: { label: '重複', color: 'bg-muted text-muted-foreground border border-border', next: 'open' },
};

const SEVERITY_CONFIG: Record<string, { label: string; color: string }> = {
    blocker: { label: '嚴重', color: 'text-status-error' },
    workaround: { label: '中等', color: 'text-brand-chimei-orange' },
    minor: { label: '輕微', color: 'text-muted-foreground' },
};

const FILTER_TABS = [
    { key: '', label: '全部' },
    { key: 'open', label: '待處理' },
    { key: 'in_progress', label: '處理中' },
    { key: 'fixed', label: '已修復' },
];

export function AdminFeedbackPanel({ userUpn }: AdminFeedbackPanelProps) {
    const [feedbacks, setFeedbacks] = useState<FeedbackRead[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [statusFilter, setStatusFilter] = useState('');
    const [expandedId, setExpandedId] = useState<string | null>(null);

    const loadFeedbacks = useCallback(async () => {
        try {
            setLoading(true);
            const data = await api.listAdminFeedback(userUpn, statusFilter || undefined);
            setFeedbacks(data);
            setError(null);
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : String(e);
            if (msg.includes('403')) {
                setError('權限不足：僅管理員可查看');
            } else {
                setError(`載入失敗：${msg}`);
            }
        } finally {
            setLoading(false);
        }
    }, [userUpn, statusFilter]);

    useEffect(() => { loadFeedbacks(); }, [loadFeedbacks]);

    const handleStatusChange = async (fb: FeedbackRead) => {
        const cfg = STATUS_CONFIG[fb.status] || STATUS_CONFIG.open;
        const newStatus = cfg.next;
        try {
            await api.patchFeedback(fb.id, userUpn, { status: newStatus });
            setFeedbacks(prev => prev.map(f => f.id === fb.id ? { ...f, status: newStatus } : f));
        } catch {
            // Silently fail — user can retry
        }
    };

    const formatDate = (iso: string) => {
        const d = new Date(iso);
        return d.toLocaleDateString('zh-TW', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Taipei' });
    };

    if (error) {
        return (
            <div className="bg-status-error/10 border border-status-error/20 rounded-xl p-6 text-center">
                <AlertCircle className="mx-auto mb-2 text-status-error" size={24} />
                <p className="text-status-error font-medium">{error}</p>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                        <MessageSquare size={20} className="text-brand-cta" />
                        問題回報管理
                    </h2>
                    <p className="text-sm text-muted-foreground mt-0.5">
                        {feedbacks.length} 筆回報 · 點擊狀態標籤可快速切換
                    </p>
                </div>
                <div className="flex items-center gap-1 text-xs">
                    <Filter size={14} className="text-muted-foreground" />
                </div>
            </div>

            {/* Filter Tabs */}
            <div className="flex gap-1 bg-muted/50 p-1 rounded-lg w-fit">
                {FILTER_TABS.map(tab => (
                    <button
                        key={tab.key}
                        onClick={() => setStatusFilter(tab.key)}
                        className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                            statusFilter === tab.key
                                ? 'bg-card text-foreground shadow-sm'
                                : 'text-muted-foreground hover:text-foreground'
                        }`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Table */}
            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <div className="w-6 h-6 border-2 border-brand-cta/30 border-t-brand-cta rounded-full animate-spin" />
                </div>
            ) : feedbacks.length === 0 ? (
                <div className="bg-card rounded-xl border border-border p-8 text-center">
                    <CheckCircle2 className="mx-auto mb-2 text-status-success" size={32} />
                    <p className="text-foreground font-medium">沒有符合條件的回報</p>
                    <p className="text-sm text-muted-foreground mt-1">所有問題都已處理完畢 🎉</p>
                </div>
            ) : (
                <div className="bg-card rounded-xl border border-border overflow-hidden">
                    <div className="divide-y divide-border">
                        {feedbacks.map(fb => {
                            const isExpanded = expandedId === fb.id;
                            const statusCfg = STATUS_CONFIG[fb.status] || STATUS_CONFIG.open;
                            const severityCfg = SEVERITY_CONFIG[fb.severity] || SEVERITY_CONFIG.minor;

                            return (
                                <div key={fb.id} className="group">
                                    {/* Row */}
                                    <div
                                        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
                                        onClick={() => setExpandedId(isExpanded ? null : fb.id)}
                                    >
                                        {isExpanded ? <ChevronDown size={14} className="text-muted-foreground flex-shrink-0" /> : <ChevronRight size={14} className="text-muted-foreground flex-shrink-0" />}

                                        {/* Severity dot */}
                                        <span className={`text-[10px] font-bold flex-shrink-0 ${severityCfg.color}`}>
                                            {severityCfg.label}
                                        </span>

                                        {/* Summary */}
                                        <p className="flex-1 text-sm text-foreground truncate">
                                            {fb.summary.split('\n')[0]}
                                        </p>

                                        {/* Date */}
                                        <span className="text-[11px] text-muted-foreground flex-shrink-0 flex items-center gap-1">
                                            <Clock size={11} />
                                            {formatDate(fb.created_at)}
                                        </span>

                                        {/* Status pill (clickable) */}
                                        <button
                                            onClick={(e) => { e.stopPropagation(); handleStatusChange(fb); }}
                                            className={`text-[10px] font-semibold px-2 py-0.5 rounded-full flex-shrink-0 cursor-pointer hover:opacity-80 transition-opacity ${statusCfg.color}`}
                                            title={`點擊切換為「${STATUS_CONFIG[statusCfg.next]?.label}」`}
                                        >
                                            {statusCfg.label}
                                        </button>
                                    </div>

                                    {/* Expanded detail */}
                                    {isExpanded && (
                                        <div className="px-10 pb-4 pt-1 space-y-2 bg-muted/20 border-t border-border/50">
                                            <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                                                {fb.summary}
                                            </p>
                                            <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                                                <span>類型: {fb.issue_type}</span>
                                                <span>回報者: {fb.user_upn}</span>
                                                {fb.meeting_id && <span>Meeting: {fb.meeting_id.slice(0, 8)}…</span>}
                                                {fb.page_url && (
                                                    <a href={fb.page_url} target="_blank" rel="noreferrer" className="flex items-center gap-0.5 text-brand-cta hover:underline">
                                                        <ExternalLink size={10} /> 來源頁面
                                                    </a>
                                                )}
                                            </div>
                                            {fb.admin_notes && (
                                                <p className="text-xs text-brand-cta bg-brand-cta/5 px-2 py-1 rounded">
                                                    📝 {fb.admin_notes}
                                                </p>
                                            )}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}
