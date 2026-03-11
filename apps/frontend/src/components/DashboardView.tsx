"use client";

import React, { useState } from 'react';
import {
    Mic,
    Upload,
    Search,
    FileText,
    CheckCircle2,
    Loader2,
    AlertCircle,
    RefreshCw,
} from 'lucide-react';
import type { Meeting } from '@/types/meeting';
import { MeetingCard } from './MeetingCard';

interface DashboardViewProps {
    meetings: Meeting[];
    isLoading: boolean;
    isUploading?: boolean;
    error: string | null;
    successMessage: string | null;
    onSelectMeeting: (meeting: Meeting) => void;
    onCreateMeeting: () => void;
    onUploadClick?: () => void;
    onRefresh: () => void;
}

export const DashboardView = ({ meetings, isLoading, isUploading = false, error, successMessage, onSelectMeeting, onCreateMeeting, onUploadClick, onRefresh }: DashboardViewProps) => {
    const [searchQuery, setSearchQuery] = useState('');

    const filteredMeetings = meetings.filter(m =>
        m.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.summary.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">

            {/* Header & Actions */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-foreground">我的會議記錄</h1>
                    <p className="text-muted-foreground">管理並搜尋所有的會議內容</p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={onRefresh}
                        className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg text-foreground/70 hover:bg-muted font-medium transition-colors"
                        disabled={isLoading}
                    >
                        <RefreshCw size={18} className={isLoading ? 'animate-spin' : ''} />
                        <span className="hidden sm:inline">重新整理</span>
                    </button>
                    {onUploadClick && (
                        <button
                            onClick={onUploadClick}
                            disabled={isUploading}
                            className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg text-foreground/70 hover:bg-muted font-medium transition-colors disabled:opacity-50"
                        >
                            {isUploading ? <Loader2 size={18} className="animate-spin" /> : <Upload size={18} />}
                            <span className="hidden sm:inline">{isUploading ? '上傳中...' : '上傳錄音'}</span>
                        </button>
                    )}
                    <button
                        onClick={onCreateMeeting}
                        className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-brand-cta to-brand-cta/80 text-white rounded-lg hover:shadow-lg hover:shadow-brand-cta/30 font-medium transition-all"
                    >
                        <Mic size={18} />
                        <span className="hidden sm:inline">新會議 (錄音)</span>
                    </button>
                </div>
            </div>

            {/* Error Banner */}
            {error && (
                <div className="bg-status-error/10 border border-status-error/30 rounded-xl p-4 flex items-start gap-3">
                    <AlertCircle className="text-status-error flex-shrink-0 mt-0.5" size={20} />
                    <div>
                        <p className="font-medium text-status-error">無法載入會議列表</p>
                        <p className="text-sm text-status-error/70 mt-1">{error}</p>
                    </div>
                </div>
            )}

            {/* Success Banner */}
            <div className={`transition-all duration-500 ease-in-out overflow-hidden ${successMessage ? 'max-h-20 opacity-100' : 'max-h-0 opacity-0'}`}>
                <div className="bg-status-success/10 border border-status-success/30 rounded-xl p-4 flex items-center gap-3 mb-0">
                    <CheckCircle2 className="text-status-success flex-shrink-0" size={20} />
                    <p className="font-medium text-status-success">{successMessage}</p>
                </div>
            </div>

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
                        {searchQuery ? '沒有找到符合的會議記錄' : '還沒有會議記錄，點擊「開始錄音」開始第一場會議'}
                    </p>
                </div>
            )}
        </div>
    );
};
