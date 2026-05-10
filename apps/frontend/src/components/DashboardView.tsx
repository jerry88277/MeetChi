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
} from 'lucide-react';
import type { Meeting } from '@/types/meeting';
import type { UploadState } from '@/hooks/useRecording';
import type { TemplateDTO } from '@/lib/api';
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
}

export const DashboardView = ({ meetings, isLoading, isUploading = false, uploadState = 'idle', error, successMessage, onSelectMeeting, onCreateMeeting, onUploadClick, onRefresh, availableTemplates = [], selectedTemplateName = 'general', onTemplateChange, uploadContext = '', onUploadContextChange }: DashboardViewProps) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);

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
        <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">

            {/* Header & Actions */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <div className="flex items-center gap-3 mb-1">
                        <h1 className="text-2xl font-bold text-foreground">我的會議記錄</h1>
                        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-status-success/10 text-status-success border border-status-success/30 rounded-full text-xs font-medium" title="此平台的錄音與摘要處理完全在本地端或私有網路的 GPU 上運行，不會將機密對話外洩至任何第三方雲端服務。">
                            <Shield className="w-3.5 h-3.5" />
                            <span>地端機密處理</span>
                        </div>
                    </div>
                    <p className="text-muted-foreground">管理並搜尋所有的會議內容</p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={onRefresh}
                        aria-label="重新整理會議列表"
                        title="重新整理會議列表"
                        className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg text-foreground/70 hover:bg-muted font-medium transition-colors"
                        disabled={isLoading}
                    >
                        <RefreshCw size={18} className={isLoading ? 'animate-spin' : ''} />
                        <span className="hidden sm:inline">重新整理</span>
                    </button>

                    {/* Unified CTA Dropdown */}
                    <div className="relative" ref={menuRef}>
                        <button
                            onClick={() => !isProcessing && setIsMenuOpen(!isMenuOpen)}
                            disabled={isProcessing}
                            aria-haspopup="menu"
                            aria-expanded={isMenuOpen}
                            aria-label="新增會議記錄"
                            title="新增會議記錄"
                            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-brand-cta to-brand-cta/80 text-white rounded-lg hover:shadow-lg hover:shadow-brand-cta/30 font-medium transition-all disabled:opacity-70"
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
                                    <Plus size={18} />
                                    <span className="hidden sm:inline">新增會議記錄</span>
                                    <ChevronDown size={14} className={`transition-transform ${isMenuOpen ? 'rotate-180' : ''}`} />
                                </>
                            )}
                        </button>

                        {/* Dropdown Menu */}
                        {isMenuOpen && (
                            <div className="absolute right-0 mt-2 w-48 bg-card border border-border rounded-xl shadow-lg overflow-hidden z-50 animate-in fade-in slide-in-from-top-2 duration-200">
                                <button
                                    onClick={() => { setIsMenuOpen(false); onCreateMeeting(); }}
                                    className="w-full flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-muted transition-colors"
                                >
                                    <Mic size={16} className="text-brand-cta" />
                                    <span>即時錄音</span>
                                </button>
                                {onUploadClick && (
                                    <button
                                        onClick={() => { setIsMenuOpen(false); onUploadClick(); }}
                                        className="w-full flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-muted transition-colors border-t border-border"
                                    >
                                        <Upload size={16} className="text-brand-violet" />
                                        <span>上傳音檔</span>
                                    </button>
                                )}
                                {/* Phase C: Template selector */}
                                {availableTemplates.length > 0 && onTemplateChange && (
                                    <div className="border-t border-border px-4 py-2">
                                        <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">摘要模板</label>
                                        <select
                                            value={selectedTemplateName}
                                            onChange={(e) => onTemplateChange(e.target.value)}
                                            className="mt-1 w-full px-2 py-1.5 text-xs bg-muted border border-border rounded-lg text-foreground focus:outline-none focus:ring-1 focus:ring-brand-cta"
                                        >
                                            {availableTemplates.filter(t => t.is_active).map(t => (
                                                <option key={t.id} value={t.name}>{t.display_name}</option>
                                            ))}
                                        </select>
                                        
                                        {/* Phase C: Context Input */}
                                        {onUploadContextChange && (
                                            <div className="mt-3">
                                                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">專有名詞 / 背景提示 (可選)</label>
                                                <input
                                                    type="text"
                                                    placeholder="例如: Scrum, Jira, 產品規劃..."
                                                    value={uploadContext}
                                                    onChange={(e) => onUploadContextChange(e.target.value)}
                                                    className="mt-1 w-full px-2 py-1.5 text-xs bg-muted border border-border rounded-lg text-foreground focus:outline-none focus:ring-1 focus:ring-brand-cta placeholder:text-muted-foreground/50"
                                                />
                                                {/* Phase C.3: Supplementary file upload UI Foundation (OCR) */}
                                        <div className="mt-3 pt-3 border-t border-border/50">
                                            <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider flex items-center justify-between">
                                                <span>補充資料 (白板/簡報)</span>
                                                <span className="bg-brand-cta/10 text-brand-cta px-1.5 py-0.5 rounded text-[8px]">開發中</span>
                                            </label>
                                            <div className="mt-1 flex items-center gap-2">
                                                <button
                                                    disabled
                                                    className="w-full flex items-center justify-center gap-2 px-2 py-1.5 text-xs bg-muted/50 border border-border border-dashed rounded-lg text-muted-foreground opacity-60 cursor-not-allowed"
                                                >
                                                    <Upload size={14} />
                                                    <span>選擇圖片 (.jpg, .png)</span>
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
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
                <div className="bg-status-success/10 border border-status-success/30 rounded-xl p-4 flex items-center gap-3 mb-0">
                    <CheckCircle2 className="text-status-success flex-shrink-0" size={20} />
                    <p className="font-medium text-status-success">{successMessage}</p>
                </div>
            </div>

            {/* PR19: 移除手寫 inline toast banner，全改 sonner Toaster (mounted in providers.tsx) */}

            {/* Search Bar */}
            <div className="relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" size={20} />
                <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="搜尋會議標題、關鍵字或參與者..."
                    className="w-full pl-12 pr-4 py-3 bg-card border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-cta focus:border-transparent shadow-sm transition-all"
                />
            </div>

            {/* Loading State */}
            {isLoading && (
                <div className="text-center py-16">
                    <Loader2 size={48} className="mx-auto text-brand-cta animate-spin mb-4" />
                    <p className="text-muted-foreground">載入會議列表中...</p>
                </div>
            )}

            {/* Meeting List */}
            {!isLoading && (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {filteredMeetings.map((meeting, index) => (
                        <div
                            key={meeting.id}
                            style={{ animationDelay: `${index * 0.1}s` }}
                            className="animate-in fade-in slide-in-from-bottom-4 duration-500"
                        >
                            <MeetingCard meeting={meeting} onClick={onSelectMeeting} />
                        </div>
                    ))}
                </div>
            )}

            {/* Empty State */}
            {!isLoading && !error && filteredMeetings.length === 0 && (
                <div className="text-center py-16">
                    <FileText size={48} className="mx-auto text-muted-foreground/30 mb-4" />
                    <p className="text-muted-foreground">
                        {searchQuery ? '沒有找到符合的會議記錄' : '還沒有會議記錄，點擊「新增會議記錄」開始第一場會議'}
                    </p>
                </div>
            )}
        </div>
    );
};
