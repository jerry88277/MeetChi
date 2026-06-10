"use client";

import React, { useState, useRef, useEffect } from 'react';
import {
    Plus,
    Mic,
    Upload,
    Search,
    FileText,
    CheckCircle2,
    Loader2,
    RefreshCw,
    ChevronDown,
    Shield,
    Trash2,
    X,
} from 'lucide-react';
import type { Meeting } from '@/types/meeting';
import type { UploadState } from '@/hooks/useRecording';
import type { TemplateDTO } from '@/lib/api';
import { useDragSelect } from '@/hooks/useDragSelect';
import { MeetingCard } from './MeetingCard';
import { ErrorState } from './ui/error-state';

interface DashboardViewProps {
    meetings: Meeting[];
    isLoading: boolean;
    isUploading?: boolean;
    uploadState?: UploadState;
    error: string | null;
    successMessage: string | null;
    onSelectMeeting: (meeting: Meeting) => void;
    onCreateMeeting: () => void;
    onUploadClick?: () => void;
    onRefresh: () => void;
    // Phase C: Template selection for upload
    availableTemplates?: TemplateDTO[];
    selectedTemplateName?: string;
    onTemplateChange?: (name: string) => void;
    // Phase C: Context input
    uploadContext?: string;
    onUploadContextChange?: (context: string) => void;
    // Sprint 2e Phase 1 (2026-05-11): 機密會議旗標
    uploadConfidential?: boolean;
    onUploadConfidentialChange?: (confidential: boolean) => void;
    // 2026-05-24 (request #1)：拖曳框選後批次刪除
    onBulkDelete?: (meetingIds: string[]) => void;
    onRename?: (meetingId: string, newTitle: string) => void;
    // 2026-06-10: Server-side filtering
    onServerFilter?: (params: { keyword?: string; dateFrom?: string; dateTo?: string }) => void;
}

export const DashboardView = ({ meetings, isLoading, isUploading = false, uploadState = 'idle', error, successMessage, onSelectMeeting, onCreateMeeting, onUploadClick, onRefresh, availableTemplates = [], selectedTemplateName = 'general', onTemplateChange, uploadContext = '', onUploadContextChange, uploadConfidential = false, onUploadConfidentialChange, onBulkDelete, onRename, onServerFilter }: DashboardViewProps) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [showDateFilter, setShowDateFilter] = useState(false);
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const menuRef = useRef<HTMLDivElement>(null);

    // 2026-05-24 (request #1)：拖曳框選 + 批次刪除
    const {
        containerRef,
        selectedIds,
        toggleId,
        clearSelection,
        dragRect,
        isDragging,
    } = useDragSelect<HTMLDivElement>();

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setIsMenuOpen(false);
            }
        };
        if (isMenuOpen) document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [isMenuOpen]);

    const filteredMeetings = meetings.filter(m =>
        m.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.summary.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const isProcessing = uploadState === 'uploading' || uploadState === 'processing';

    return (
        // 2026-05-25 fix：containerRef 從 grid 移到最外層 full-width wrapper，
        // 讓拖曳框選可在 max-w-7xl 兩側留白也能啟動（user 反映無法橫向擴展）。
        // 卡片仍在內部，querySelectorAll('[data-select-id]') 與 bbox 交集計算
        // 都不變。dragRect 改在這個 wrapper 內 absolute 定位，覆蓋整個寬度。
        <div ref={containerRef} className="relative min-h-full select-none" style={{ userSelect: isDragging ? 'none' : undefined }}>
            {/* 拖曳選取框（覆蓋整個 dashboard 寬度，含 max-w-7xl 兩側留白）*/}
            {dragRect && (
                <div
                    className="absolute pointer-events-none border-2 border-brand-cta bg-brand-cta/10 rounded-md z-20"
                    style={{
                        left: dragRect.left,
                        top: dragRect.top,
                        width: dragRect.width,
                        height: dragRect.height,
                    }}
                />
            )}

        <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8 relative">

            {/* Header & Actions */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <div className="flex items-center gap-3 mb-1">
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">我的會議記錄</h1>
                        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-status-success/10 text-status-success border border-status-success/30 rounded-full text-xs font-medium" title="此平台的錄音與摘要處理完全在本地端或私有網路的 GPU 上運行，不會將機密對話外洩至任何第三方雲端服務。">
                            <Shield className="w-3.5 h-3.5" />
                            <span>資料安全保護</span>
                        </div>
                    </div>
                    <p className="text-muted-foreground">把分散的會議內容整理成可追蹤的進展</p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={onRefresh}
                        aria-label="重新整理會議列表"
                        title="重新整理會議列表"
                        className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-black/5 transition-colors duration-150 disabled:opacity-40"
                        disabled={isLoading}
                    >
                        <RefreshCw size={18} className={isLoading ? 'animate-spin' : ''} />
                    </button>

                    {/* P0 Fix: Split CTA — primary = upload directly, secondary = record audio.
                        Dropdown removed; template/confidential/context stay in upload modal (step 2). */}
                    <div className="flex items-center gap-2">
                        {/* Secondary: record audio */}
                        <button
                            onClick={onCreateMeeting}
                            disabled={isProcessing}
                            aria-label="即時錄音"
                            title="即時錄音（開發中）"
                            className="flex items-center gap-2 px-3 py-2 border border-border bg-card text-foreground rounded-lg hover:bg-muted text-sm font-medium transition-colors duration-150 disabled:opacity-50"
                        >
                            <Mic size={16} className="text-brand-cta" />
                            <span className="hidden sm:inline">即時錄音</span>
                        </button>

                        {/* Primary: upload audio file — direct action, no dropdown */}
                        <button
                            data-tour="upload-cta"
                            onClick={() => !isProcessing && onUploadClick?.()}
                            disabled={isProcessing}
                            aria-label="上傳音檔"
                            title="上傳會議音檔"
                            className="flex items-center gap-2 px-4 py-2 bg-brand-cta text-white rounded-lg hover:bg-brand-cta/90 hover:shadow-[0_4px_16px_-2px_rgba(45,66,139,0.35)] font-medium transition-[colors,shadow] duration-200 disabled:opacity-70"
                        >
                            {isProcessing ? (
                                <>
                                    <Loader2 size={18} className="animate-spin" />
                                    <span className="hidden sm:inline">
                                        {uploadState === 'uploading' ? '上傳中...' : '處理中...'}
                                    </span>
                                </>
                            ) : (
                                <>
                                    <Upload size={18} />
                                    <span className="hidden sm:inline">上傳音檔</span>
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>

            {/* Error Banner — 用統一 <ErrorState> 元件 */}
            {error && (
                <ErrorState
                    title="無法載入會議列表"
                    message={error}
                    onRetry={onRefresh}
                />
            )}

            {/* Success Banner */}
            <div className={`transition-all duration-500 ease-in-out overflow-hidden ${successMessage ? 'max-h-20 opacity-100' : 'max-h-0 opacity-0'}`}>
                <div className="bg-brand-chimei-green/10 border border-brand-chimei-green/30 rounded-xl p-4 flex items-center gap-3 mb-0">
                    <CheckCircle2 className="text-brand-chimei-green flex-shrink-0" size={20} />
                    <p className="font-medium text-brand-chimei-green">{successMessage}</p>
                </div>
            </div>

            {/* PR19: 移除手寫 inline toast banner，全改 sonner Toaster (mounted in providers.tsx) */}

            {/* Search Bar + Date Filter */}
            <div className="space-y-3">
                <div className="flex gap-2 items-center">
                    <div className="relative flex-1">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" size={18} />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && onServerFilter) {
                                    onServerFilter({ keyword: searchQuery || undefined, dateFrom: dateFrom || undefined, dateTo: dateTo || undefined });
                                }
                            }}
                            placeholder="搜尋會議標題或摘要重點"
                            className="w-full pl-11 pr-4 py-3 bg-card border border-border rounded-full focus:outline-none focus:ring-2 focus:ring-brand-cta/40 focus:border-brand-cta/40 shadow-sm transition-[border-color,box-shadow] duration-200"
                        />
                    </div>
                    <button
                        type="button"
                        onClick={() => setShowDateFilter(!showDateFilter)}
                        className={`px-3 py-3 rounded-full border transition-colors ${showDateFilter ? 'bg-brand-cta text-white border-brand-cta' : 'bg-card border-border text-muted-foreground hover:text-foreground'}`}
                        title="日期篩選"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
                    </button>
                    {onServerFilter && (searchQuery || dateFrom || dateTo) && (
                        <button
                            type="button"
                            onClick={() => {
                                setSearchQuery('');
                                setDateFrom('');
                                setDateTo('');
                                setShowDateFilter(false);
                                onServerFilter({});
                            }}
                            className="px-3 py-3 rounded-full border border-border bg-card text-muted-foreground hover:text-foreground transition-colors"
                            title="清除篩選"
                        >
                            <X size={18} />
                        </button>
                    )}
                </div>
                {showDateFilter && (
                    <div className="flex items-center gap-3 pl-4 animate-in fade-in slide-in-from-top-1 duration-200">
                        <span className="text-sm text-muted-foreground">日期範圍：</span>
                        <input
                            type="date"
                            value={dateFrom}
                            onChange={e => setDateFrom(e.target.value)}
                            className="px-3 py-1.5 text-sm border rounded-lg bg-card"
                        />
                        <span className="text-muted-foreground">—</span>
                        <input
                            type="date"
                            value={dateTo}
                            onChange={e => setDateTo(e.target.value)}
                            className="px-3 py-1.5 text-sm border rounded-lg bg-card"
                        />
                        <button
                            type="button"
                            onClick={() => onServerFilter?.({ keyword: searchQuery || undefined, dateFrom: dateFrom || undefined, dateTo: dateTo || undefined })}
                            className="px-4 py-1.5 text-sm bg-brand-cta text-white rounded-lg hover:opacity-90 font-medium"
                        >
                            套用
                        </button>
                    </div>
                )}
            </div>

            {/* Loading State */}
            {isLoading && (
                <div className="text-center py-16">
                    <Loader2 size={48} className="mx-auto text-brand-cta animate-spin mb-4" />
                    <p className="text-muted-foreground">載入會議列表中...</p>
                </div>
            )}

            {/* 2026-05-24 (request #1)：拖曳框選浮動工具列 */}
            {selectedIds.size > 0 && (
                <div className="sticky top-4 z-30 flex items-center justify-between gap-3 px-4 py-2.5 bg-brand-cta text-white rounded-xl shadow-lg animate-in fade-in slide-in-from-top-2 duration-200">
                    <span className="text-sm font-medium">
                        已選取 {selectedIds.size} 個會議
                    </span>
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            onClick={() => { onBulkDelete?.(Array.from(selectedIds)); clearSelection(); }}
                            disabled={!onBulkDelete}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-status-error hover:bg-status-error/90 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
                        >
                            <Trash2 size={14} /> 批次刪除
                        </button>
                        <button
                            type="button"
                            onClick={clearSelection}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-white/15 hover:bg-white/25 rounded-lg text-sm font-medium transition-colors"
                            title="清空選取（Esc）"
                        >
                            <X size={14} /> 取消
                        </button>
                    </div>
                </div>
            )}

            {/* Meeting List */}
            {!isLoading && (
                <div
                    className="relative grid gap-4 md:grid-cols-2 lg:grid-cols-3"
                    data-tour="meetings-grid"
                >
                    {filteredMeetings.map((meeting, index) => {
                        const isSelected = selectedIds.has(meeting.id);
                        return (
                            <div
                                key={meeting.id}
                                data-select-id={meeting.id}
                                style={{ animationDelay: `${index * 0.1}s` }}
                                onClick={(e) => {
                                    // Shift/Ctrl+click 切換選取；否則正常打開詳情頁
                                    // （若已有其他選取也 toggle，方便框選後微調）
                                    if (e.shiftKey || e.ctrlKey || e.metaKey || selectedIds.size > 0) {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        toggleId(meeting.id);
                                        return;
                                    }
                                    onSelectMeeting(meeting);
                                }}
                                className={`relative h-full animate-in fade-in slide-in-from-bottom-4 duration-500 rounded-xl transition-all ${
                                    isSelected ? 'ring-2 ring-brand-cta ring-offset-2 ring-offset-surface' : ''
                                }`}
                            >
                                {/* 已選取 checkmark 標記 */}
                                {isSelected && (
                                    <div className="absolute top-2 right-2 z-10 w-6 h-6 rounded-full bg-brand-cta text-white flex items-center justify-center shadow-md pointer-events-none">
                                        <CheckCircle2 size={14} />
                                    </div>
                                )}
                                <MeetingCard meeting={meeting} onClick={() => { /* 由外層 onClick 處理 */ }} onRename={onRename} />
                            </div>
                        );
                    })}

                    {/* dragRect 已移到最外層 wrapper，這裡不再渲染 */}
                </div>
            )}

            {/* Empty State */}
            {!isLoading && !error && filteredMeetings.length === 0 && (
                <div className="text-center py-16">
                    <FileText size={48} className="mx-auto text-muted-foreground/30 mb-4" />
                    <p className="text-muted-foreground">
                        {searchQuery ? '沒有找到符合的會議記錄' : '上傳第一場會議，系統會在背景自動整理重點、決策與下一步'}
                    </p>
                    {!searchQuery && (
                        <p className="mt-2 text-sm text-muted-foreground/80">
                            完成上傳後，您可直接搜尋摘要、決策與待辦重點。
                        </p>
                    )}
                </div>
            )}
        </div>
        {/* close outer containerRef wrapper */}
        </div>
    );
};
