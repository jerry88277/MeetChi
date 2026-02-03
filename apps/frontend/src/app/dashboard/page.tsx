"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { useSession, signOut } from 'next-auth/react';
import {
    Mic,
    Square,
    Upload,
    Search,
    Clock,
    Calendar,
    ChevronRight,
    Play,
    FileText,
    CheckCircle2,
    MoreVertical,
    Settings,
    Menu,
    X,
    Loader2,
    AlertCircle,
    RefreshCw,
    Wifi,
    WifiOff,
    LogOut,
    Shield,
    LayoutTemplate
} from 'lucide-react';
import { api, API_BASE_URL, Meeting as ApiMeeting, MeetingSummary } from '@/lib/api';

// --- Types ---
interface ActionItem {
    id: number;
    text: string;
    assignee: string;
    due: string;
}

interface TranscriptLine {
    time: string;
    speaker: string;
    text: string;
}

interface Meeting {
    id: string;
    title: string;
    date: string;
    duration: string;
    status: "completed" | "processing" | "failed";
    summary: string;
    actionItems: ActionItem[];
    transcript: TranscriptLine[];
}

// Transform API meeting to UI format
function transformMeeting(apiMeeting: ApiMeeting): Meeting {
    // Parse summary JSON if available
    let summary = "";
    let actionItems: ActionItem[] = [];

    if (apiMeeting.summary_json) {
        try {
            const summaryData: MeetingSummary = JSON.parse(apiMeeting.summary_json);
            summary = summaryData.summary || "";
            actionItems = (summaryData.action_items || []).map((text, idx) => ({
                id: idx + 1,
                text,
                assignee: "待分配",
                due: "待定"
            }));
        } catch {
            summary = apiMeeting.summary_json;
        }
    }

    // Transform transcript segments
    const transcript: TranscriptLine[] = (apiMeeting.transcript_segments || []).map(seg => ({
        time: formatSeconds(seg.start_time),
        speaker: seg.speaker || "Unknown",
        text: seg.content_polished || seg.content_raw
    }));

    // Format duration
    const durationStr = apiMeeting.duration
        ? formatSeconds(apiMeeting.duration)
        : "00:00";

    return {
        id: apiMeeting.id,
        title: apiMeeting.title,
        date: new Date(apiMeeting.created_at).toISOString().split('T')[0],
        duration: durationStr,
        status: apiMeeting.status === "completed" ? "completed"
            : apiMeeting.status === "failed" ? "failed"
                : "processing",
        summary,
        actionItems,
        transcript
    };
}

function formatSeconds(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// --- Sidebar Component ---
interface SidebarProps {
    activeTab: string;
    setActiveTab: (tab: string) => void;
    isMobileOpen: boolean;
    setIsMobileOpen: (open: boolean) => void;
    isConnected: boolean;
    user?: {
        name?: string | null;
        email?: string | null;
        image?: string | null;
    };
}

const Sidebar = ({ activeTab, setActiveTab, isMobileOpen, setIsMobileOpen, isConnected, user }: SidebarProps) => {
    const menuItems = [
        { id: 'dashboard', icon: FileText, label: '所有會議' },
        { id: 'record', icon: Mic, label: '開始錄音', primary: true },
        { id: 'templates', icon: LayoutTemplate, label: '模板管理' },
        { id: 'admin', icon: Shield, label: '管理' },
        { id: 'settings', icon: Settings, label: '系統設定' },
    ];

    const sidebarClass = `fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-white transform transition-transform duration-300 ease-in-out ${isMobileOpen ? 'translate-x-0' : '-translate-x-full'
        } md:relative md:translate-x-0 flex flex-col`;

    return (
        <>
            {isMobileOpen && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-50 z-40 md:hidden"
                    onClick={() => setIsMobileOpen(false)}
                />
            )}

            <div className={sidebarClass}>
                <div className="p-6 border-b border-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 bg-indigo-500 rounded-lg flex items-center justify-center">
                            <span className="font-bold text-white">M</span>
                        </div>
                        <span className="text-xl font-bold tracking-tight">MeetChi</span>
                    </div>
                    <button onClick={() => setIsMobileOpen(false)} className="md:hidden text-slate-400">
                        <X size={24} />
                    </button>
                </div>

                <nav className="flex-1 p-4 space-y-2">
                    {menuItems.map((item) => (
                        <button
                            key={item.id}
                            onClick={() => {
                                setActiveTab(item.id);
                                setIsMobileOpen(false);
                            }}
                            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${item.primary
                                ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50'
                                : activeTab === item.id
                                    ? 'bg-slate-800 text-white'
                                    : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                                }`}
                        >
                            <item.icon size={20} />
                            <span className="font-medium">{item.label}</span>
                        </button>
                    ))}
                </nav>

                {/* User Profile Section */}
                {user && (
                    <div className="p-4 border-t border-slate-800">
                        <div className="flex items-center gap-3 mb-3">
                            {user.image ? (
                                <img
                                    src={user.image}
                                    alt={user.name || 'User'}
                                    className="w-10 h-10 rounded-full"
                                />
                            ) : (
                                <div className="w-10 h-10 rounded-full bg-indigo-500 flex items-center justify-center text-white font-medium">
                                    {user.name?.charAt(0) || user.email?.charAt(0) || '?'}
                                </div>
                            )}
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-white truncate">{user.name}</p>
                                <p className="text-xs text-slate-400 truncate">{user.email}</p>
                            </div>
                        </div>
                        <button
                            onClick={() => signOut({ callbackUrl: '/login' })}
                            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
                        >
                            <LogOut size={16} />
                            <span>登出</span>
                        </button>
                    </div>
                )}

                {/* Backend Status */}
                <div className="p-4 border-t border-slate-800">
                    <div className="bg-slate-800/50 rounded-xl p-4">
                        <p className="text-xs text-slate-400 mb-2">後端狀態</p>
                        <div className="flex items-center gap-2 mb-1">
                            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`}></div>
                            <span className="text-xs font-mono text-slate-300">
                                {isConnected ? '已連線' : '未連線'}
                            </span>
                        </div>
                        <p className="text-xs text-slate-500 truncate" title={API_BASE_URL}>
                            {API_BASE_URL.replace('https://', '').substring(0, 25)}...
                        </p>
                    </div>
                </div>
            </div>
        </>
    );
};

// --- Recording View Component ---
interface RecordingViewProps {
    onStop: (durationSeconds: number) => void;
    onCancel: () => void;
    isSaving?: boolean;
}

const RecordingView = ({ onStop, onCancel, isSaving = false }: RecordingViewProps) => {
    const [duration, setDuration] = useState(0);
    const [waves, setWaves] = useState(Array(20).fill(10));

    useEffect(() => {
        const timer = setInterval(() => setDuration(d => d + 1), 1000);
        const animator = setInterval(() => {
            setWaves(Array(20).fill(0).map(() => Math.floor(Math.random() * 40) + 10));
        }, 100);
        return () => {
            clearInterval(timer);
            clearInterval(animator);
        };
    }, []);

    const handleStop = () => {
        onStop(duration);
    };

    return (
        <div className="h-full flex flex-col items-center justify-center bg-white p-6">
            <div className="text-center mb-12">
                <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium mb-4 ${isSaving ? 'bg-amber-100 text-amber-600' : 'bg-red-100 text-red-600 animate-pulse'}`}>
                    <div className={`w-2 h-2 rounded-full ${isSaving ? 'bg-amber-600' : 'bg-red-600'}`}></div>
                    {isSaving ? '儲存中...' : '正在錄音'}
                </div>
                <h2 className="text-6xl font-mono font-bold text-slate-900 tracking-tighter tabular-nums">
                    {formatSeconds(duration)}
                </h2>
                <p className="text-slate-500 mt-2">
                    {isSaving ? '正在儲存會議記錄...' : 'AI 正在即時聆聽會議內容...'}
                </p>
            </div>

            <div className="flex items-center justify-center gap-1 h-16 mb-16">
                {waves.map((h, i) => (
                    <div
                        key={i}
                        className={`w-2 rounded-full transition-all duration-100 ease-in-out ${isSaving ? 'bg-amber-500' : 'bg-indigo-500'}`}
                        style={{ height: `${h}%`, opacity: Math.max(0.3, h / 50) }}
                    />
                ))}
            </div>

            <div className="flex items-center gap-6">
                <button
                    onClick={onCancel}
                    className="p-4 rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors disabled:opacity-50"
                    title="取消錄音"
                    disabled={isSaving}
                >
                    <X size={24} />
                </button>
                <button
                    onClick={handleStop}
                    className="p-8 rounded-full bg-red-500 text-white shadow-xl shadow-red-500/30 hover:bg-red-600 hover:scale-105 transition-all disabled:opacity-50 disabled:hover:scale-100"
                    disabled={isSaving}
                >
                    {isSaving ? <Loader2 size={32} className="animate-spin" /> : <Square size={32} fill="currentColor" />}
                </button>
            </div>
        </div>
    );
};

// --- Meeting Card Component ---
interface MeetingCardProps {
    meeting: Meeting;
    onClick: (meeting: Meeting) => void;
}

const MeetingCard = ({ meeting, onClick }: MeetingCardProps) => {
    const statusColors = {
        completed: 'bg-emerald-100 text-emerald-700',
        processing: 'bg-amber-100 text-amber-700',
        failed: 'bg-red-100 text-red-700'
    };

    const statusLabels = {
        completed: '已完成',
        processing: '處理中...',
        failed: '失敗'
    };

    return (
        <div
            onClick={() => onClick(meeting)}
            className="group bg-white border border-slate-200 rounded-xl p-5 cursor-pointer hover:shadow-lg hover:border-indigo-200 transition-all duration-300"
        >
            <div className="flex justify-between items-start mb-3">
                <div>
                    <h3 className="font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">
                        {meeting.title}
                    </h3>
                    <div className="flex items-center gap-3 mt-1 text-sm text-slate-500">
                        <span className="flex items-center gap-1"><Calendar size={14} /> {meeting.date}</span>
                        <span className="flex items-center gap-1"><Clock size={14} /> {meeting.duration}</span>
                    </div>
                </div>
                <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${statusColors[meeting.status]}`}>
                    {meeting.status === 'processing' && <Loader2 size={12} className="inline mr-1 animate-spin" />}
                    {statusLabels[meeting.status]}
                </span>
            </div>

            <p className="text-slate-600 text-sm line-clamp-2 leading-relaxed">
                {meeting.summary || "等待 AI 生成摘要中..."}
            </p>

            <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                <div className="flex -space-x-2">
                    <div className="w-6 h-6 rounded-full bg-blue-500 border-2 border-white flex items-center justify-center text-[10px] text-white font-medium">P</div>
                    <div className="w-6 h-6 rounded-full bg-green-500 border-2 border-white flex items-center justify-center text-[10px] text-white font-medium">J</div>
                </div>
                <div className="text-indigo-600 text-sm font-medium flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    查看詳情 <ChevronRight size={16} />
                </div>
            </div>
        </div>
    );
};

// --- Dashboard View Component ---
interface DashboardViewProps {
    meetings: Meeting[];
    isLoading: boolean;
    error: string | null;
    onSelectMeeting: (meeting: Meeting) => void;
    onCreateMeeting: () => void;
    onRefresh: () => void;
}

const DashboardView = ({ meetings, isLoading, error, onSelectMeeting, onCreateMeeting, onRefresh }: DashboardViewProps) => {
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
                    <h1 className="text-2xl font-bold text-slate-900">我的會議記錄</h1>
                    <p className="text-slate-500">管理並搜尋所有的會議內容</p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={onRefresh}
                        className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50 font-medium transition-colors"
                        disabled={isLoading}
                    >
                        <RefreshCw size={18} className={isLoading ? 'animate-spin' : ''} />
                        <span>重新整理</span>
                    </button>
                </div>
            </div>

            {/* Error Banner */}
            {error && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
                    <AlertCircle className="text-red-500 flex-shrink-0 mt-0.5" size={20} />
                    <div>
                        <p className="font-medium text-red-800">無法載入會議列表</p>
                        <p className="text-sm text-red-600 mt-1">{error}</p>
                    </div>
                </div>
            )}

            {/* Search Bar */}
            <div className="relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
                <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="搜尋會議標題、關鍵字或參與者..."
                    className="w-full pl-12 pr-4 py-3 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent shadow-sm transition-all"
                />
            </div>

            {/* Loading State */}
            {isLoading && (
                <div className="text-center py-16">
                    <Loader2 size={48} className="mx-auto text-indigo-500 animate-spin mb-4" />
                    <p className="text-slate-500">載入會議列表中...</p>
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
                            <MeetingCard
                                meeting={meeting}
                                onClick={onSelectMeeting}
                            />
                        </div>
                    ))}
                </div>
            )}

            {/* Empty State */}
            {!isLoading && !error && filteredMeetings.length === 0 && (
                <div className="text-center py-16">
                    <FileText size={48} className="mx-auto text-slate-300 mb-4" />
                    <p className="text-slate-500">
                        {searchQuery ? '沒有找到符合的會議記錄' : '還沒有會議記錄，點擊「開始錄音」開始第一場會議'}
                    </p>
                </div>
            )}
        </div>
    );
};

// --- Detail View Component ---
interface DetailViewProps {
    meeting: Meeting | null;
    onBack: () => void;
}

const DetailView = ({ meeting, onBack }: DetailViewProps) => {
    if (!meeting) return null;

    return (
        <div className="h-full flex flex-col bg-white">
            <div className="border-b border-slate-200 px-6 py-4 flex items-center gap-4 bg-white sticky top-0 z-10">
                <button onClick={onBack} className="p-2 hover:bg-slate-100 rounded-full text-slate-500 transition-colors">
                    <ChevronRight size={24} className="rotate-180" />
                </button>
                <div className="flex-1">
                    <h2 className="text-xl font-bold text-slate-900">{meeting.title}</h2>
                    <div className="flex items-center gap-3 text-sm text-slate-500">
                        <span>{meeting.date}</span>
                        <span className="w-1 h-1 rounded-full bg-slate-300"></span>
                        <span>{meeting.duration}</span>
                    </div>
                </div>
                <div className="flex gap-2">
                    <button className="p-2 text-indigo-600 bg-indigo-50 rounded-full hover:bg-indigo-100">
                        <Play size={20} fill="currentColor" />
                    </button>
                    <button className="p-2 text-slate-400 hover:text-slate-600">
                        <MoreVertical size={20} />
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-hidden flex flex-col md:flex-row">
                <div className="flex-1 overflow-y-auto p-6 md:p-8 border-r border-slate-200 bg-slate-50/50">
                    <div className="max-w-3xl mx-auto space-y-8">
                        <section>
                            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500 mb-4 flex items-center gap-2">
                                <FileText size={16} /> 會議摘要
                            </h3>
                            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm leading-relaxed text-slate-700">
                                {meeting.summary ? meeting.summary : (
                                    <div className="flex flex-col items-center justify-center py-8 text-slate-400">
                                        <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mb-2" />
                                        <p>AI 正在生成摘要中...</p>
                                    </div>
                                )}
                            </div>
                        </section>

                        <section>
                            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500 mb-4 flex items-center gap-2">
                                <CheckCircle2 size={16} /> 待辦事項 (Action Items)
                            </h3>
                            <div className="space-y-3">
                                {meeting.actionItems && meeting.actionItems.length > 0 ? (
                                    meeting.actionItems.map(item => (
                                        <div key={item.id} className="flex items-start gap-3 bg-white p-4 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
                                            <div className="mt-1 w-5 h-5 rounded border-2 border-slate-300 cursor-pointer hover:border-indigo-500 transition-colors"></div>
                                            <div className="flex-1">
                                                <p className="text-slate-800 font-medium">{item.text}</p>
                                                <div className="flex items-center gap-3 mt-2 text-xs">
                                                    <span className="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded font-medium">{item.assignee}</span>
                                                    <span className="text-slate-400">Due: {item.due}</span>
                                                </div>
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    <p className="text-slate-400 text-sm italic ml-2">無待辦事項或尚未生成。</p>
                                )}
                            </div>
                        </section>
                    </div>
                </div>

                <div className="md:w-[400px] lg:w-[480px] flex flex-col bg-white">
                    <div className="p-4 border-b border-slate-200 bg-white">
                        <h3 className="font-bold text-slate-800">逐字稿紀錄</h3>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-6">
                        {meeting.transcript && meeting.transcript.length > 0 ? (
                            meeting.transcript.map((line, idx) => (
                                <div key={idx} className="group flex gap-4">
                                    <div className="w-12 text-xs text-slate-400 font-mono pt-1 text-right flex-shrink-0 group-hover:text-indigo-500 cursor-pointer transition-colors">
                                        {line.time}
                                    </div>
                                    <div>
                                        <div className="text-xs font-bold text-slate-900 mb-1">{line.speaker}</div>
                                        <p className="text-slate-600 text-sm leading-relaxed hover:bg-yellow-50 rounded px-1 -ml-1 transition-colors cursor-pointer">
                                            {line.text}
                                        </p>
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div className="text-center py-10 text-slate-400">
                                <p>尚無逐字稿內容</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

// --- Settings View Component ---
const SettingsView = ({ onBack, isConnected }: { onBack: () => void; isConnected: boolean }) => {
    return (
        <div className="p-6 md:p-8 max-w-4xl mx-auto">
            <div className="flex items-center gap-4 mb-8">
                <button onClick={onBack} className="p-2 hover:bg-slate-100 rounded-full text-slate-500 transition-colors">
                    <ChevronRight size={24} className="rotate-180" />
                </button>
                <h1 className="text-2xl font-bold text-slate-900">系統設定</h1>
            </div>

            <div className="space-y-6">
                <div className="bg-white rounded-xl border border-slate-200 p-6">
                    <h3 className="font-bold text-slate-900 mb-4">API 連線狀態</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                {isConnected ? (
                                    <Wifi className="text-emerald-500" size={24} />
                                ) : (
                                    <WifiOff className="text-red-500" size={24} />
                                )}
                                <div>
                                    <p className="font-medium text-slate-800">
                                        {isConnected ? '已連線到後端服務' : '無法連線到後端服務'}
                                    </p>
                                    <p className="text-sm text-slate-500">
                                        {isConnected ? '所有功能正常運作' : '請檢查網路連線或後端服務狀態'}
                                    </p>
                                </div>
                            </div>
                            <span className={`px-3 py-1 rounded-full text-sm font-medium ${isConnected ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                                }`}>
                                {isConnected ? 'Online' : 'Offline'}
                            </span>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-1">Backend URL</label>
                            <input
                                type="text"
                                value={API_BASE_URL}
                                readOnly
                                className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-600 font-mono text-sm"
                            />
                        </div>
                    </div>
                </div>

                <div className="bg-white rounded-xl border border-slate-200 p-6">
                    <h3 className="font-bold text-slate-900 mb-4">語音辨識設定</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="font-medium text-slate-800">自動標點符號</p>
                                <p className="text-sm text-slate-500">AI 自動添加逗號、句號</p>
                            </div>
                            <div className="w-12 h-6 bg-indigo-600 rounded-full relative cursor-pointer">
                                <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full shadow"></div>
                            </div>
                        </div>
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="font-medium text-slate-800">說話者分離</p>
                                <p className="text-sm text-slate-500">自動識別不同說話者</p>
                            </div>
                            <div className="w-12 h-6 bg-indigo-600 rounded-full relative cursor-pointer">
                                <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full shadow"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

// --- Main App Component ---
export default function DashboardPage() {
    const { data: session } = useSession();
    const [currentView, setCurrentView] = useState<'dashboard' | 'record' | 'detail' | 'settings' | 'templates' | 'admin'>('dashboard');
    const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    // API State
    const [meetings, setMeetings] = useState<Meeting[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isConnected, setIsConnected] = useState(false);

    // Fetch meetings from API
    const fetchMeetings = useCallback(async () => {
        setIsLoading(true);
        setError(null);

        try {
            // Check connection first
            await api.checkHealth();
            setIsConnected(true);

            // Fetch meetings
            const apiMeetings = await api.listMeetings();
            const transformedMeetings = apiMeetings.map(transformMeeting);
            setMeetings(transformedMeetings);
        } catch (err) {
            setIsConnected(false);
            setError(err instanceof Error ? err.message : '發生未知錯誤');
            setMeetings([]);
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Initial load
    useEffect(() => {
        fetchMeetings();
    }, [fetchMeetings]);

    // Recording state
    const [isSaving, setIsSaving] = useState(false);

    const handleStartRecord = () => {
        setCurrentView('record');
    };

    const handleStopRecord = async (durationSeconds: number) => {
        setIsSaving(true);
        try {
            // Generate meeting title with timestamp
            const now = new Date();
            const dateStr = now.toLocaleDateString('zh-TW', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit'
            });
            const timeStr = now.toLocaleTimeString('zh-TW', {
                hour: '2-digit',
                minute: '2-digit'
            });
            const title = `會議記錄 - ${dateStr} ${timeStr}`;

            // Create meeting via API
            const newMeeting = await api.createMeeting({
                title,
                language: 'zh-TW',
                template_name: 'general'
            });

            // Refresh meetings list
            await fetchMeetings();

            // Navigate to the new meeting detail
            const transformedMeeting = transformMeeting(newMeeting);
            setSelectedMeeting(transformedMeeting);
            setCurrentView('detail');
        } catch (err) {
            console.error('Failed to save meeting:', err);
            setError(err instanceof Error ? err.message : '儲存會議失敗');
            setCurrentView('dashboard');
        } finally {
            setIsSaving(false);
        }
    };

    const handleViewDetail = (meeting: Meeting) => {
        setSelectedMeeting(meeting);
        setCurrentView('detail');
    };

    const handleBackToDashboard = () => {
        setSelectedMeeting(null);
        setCurrentView('dashboard');
    };

    const handleTabChange = (tab: string) => {
        if (tab === 'record') {
            handleStartRecord();
        } else if (tab === 'settings') {
            setCurrentView('settings');
        } else if (tab === 'templates') {
            setCurrentView('templates');
        } else if (tab === 'admin') {
            setCurrentView('admin');
        } else {
            handleBackToDashboard();
        }
    };

    return (
        <div className="flex h-screen bg-slate-50 font-sans text-slate-900 overflow-hidden">
            {currentView !== 'record' && (
                <Sidebar
                    activeTab={currentView === 'detail' ? 'dashboard' : currentView}
                    setActiveTab={handleTabChange}
                    isMobileOpen={isMobileMenuOpen}
                    setIsMobileOpen={setIsMobileMenuOpen}
                    isConnected={isConnected}
                    user={session?.user}
                />
            )}

            <main className="flex-1 flex flex-col relative overflow-hidden">
                {currentView !== 'record' && (
                    <div className="md:hidden bg-white border-b border-slate-200 p-4 flex items-center justify-between z-20">
                        <div className="flex items-center gap-2">
                            <div className="w-6 h-6 bg-indigo-500 rounded flex items-center justify-center">
                                <span className="font-bold text-white text-xs">M</span>
                            </div>
                            <span className="font-bold">MeetChi</span>
                        </div>
                        <button onClick={() => setIsMobileMenuOpen(true)}>
                            <Menu className="text-slate-600" />
                        </button>
                    </div>
                )}

                <div className="flex-1 overflow-auto bg-slate-50">
                    {currentView === 'dashboard' && (
                        <DashboardView
                            meetings={meetings}
                            isLoading={isLoading}
                            error={error}
                            onSelectMeeting={handleViewDetail}
                            onCreateMeeting={handleStartRecord}
                            onRefresh={fetchMeetings}
                        />
                    )}

                    {currentView === 'record' && (
                        <RecordingView
                            onStop={handleStopRecord}
                            onCancel={handleBackToDashboard}
                            isSaving={isSaving}
                        />
                    )}

                    {currentView === 'detail' && (
                        <DetailView
                            meeting={selectedMeeting}
                            onBack={handleBackToDashboard}
                        />
                    )}

                    {currentView === 'settings' && (
                        <SettingsView
                            onBack={handleBackToDashboard}
                            isConnected={isConnected}
                        />
                    )}

                    {currentView === 'templates' && (
                        <div className="p-6 md:p-8 max-w-5xl mx-auto overflow-auto">
                            <div className="mb-8">
                                <h1 className="text-2xl font-bold text-slate-900 mb-2">模板管理</h1>
                                <p className="text-slate-500">選擇適合會議類型的摘要模板</p>
                            </div>

                            {/* Template Cards */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {/* General Template */}
                                <div className="bg-white rounded-xl border border-slate-200 p-6 hover:shadow-lg hover:border-indigo-300 transition-all cursor-pointer group">
                                    <div className="flex items-start gap-4">
                                        <div className="w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center text-indigo-600 group-hover:bg-indigo-500 group-hover:text-white transition-colors">
                                            <FileText size={24} />
                                        </div>
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2 mb-1">
                                                <h3 className="font-semibold text-slate-900">一般會議</h3>
                                                <span className="px-2 py-0.5 text-xs bg-indigo-100 text-indigo-600 rounded-full">預設</span>
                                            </div>
                                            <p className="text-sm text-slate-500 mb-3">適用於大多數會議場景的通用模板</p>
                                            <div className="flex flex-wrap gap-2">
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">摘要</span>
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">待辦事項</span>
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">決議</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Standup Template */}
                                <div className="bg-white rounded-xl border border-slate-200 p-6 hover:shadow-lg hover:border-amber-300 transition-all cursor-pointer group">
                                    <div className="flex items-start gap-4">
                                        <div className="w-12 h-12 bg-amber-100 rounded-xl flex items-center justify-center text-amber-600 group-hover:bg-amber-500 group-hover:text-white transition-colors">
                                            <Clock size={24} />
                                        </div>
                                        <div className="flex-1">
                                            <h3 className="font-semibold text-slate-900 mb-1">站立會議</h3>
                                            <p className="text-sm text-slate-500 mb-3">每日站立會議、進度更新專用</p>
                                            <div className="flex flex-wrap gap-2">
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">進度更新</span>
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">阻礙</span>
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">下一步</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* 1:1 Template */}
                                <div className="bg-white rounded-xl border border-slate-200 p-6 hover:shadow-lg hover:border-emerald-300 transition-all cursor-pointer group">
                                    <div className="flex items-start gap-4">
                                        <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center text-emerald-600 group-hover:bg-emerald-500 group-hover:text-white transition-colors">
                                            <CheckCircle2 size={24} />
                                        </div>
                                        <div className="flex-1">
                                            <h3 className="font-semibold text-slate-900 mb-1">一對一會議</h3>
                                            <p className="text-sm text-slate-500 mb-3">主管與團隊成員的定期溝通</p>
                                            <div className="flex flex-wrap gap-2">
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">回顧</span>
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">目標</span>
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">反饋</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Interview Template */}
                                <div className="bg-white rounded-xl border border-slate-200 p-6 hover:shadow-lg hover:border-purple-300 transition-all cursor-pointer group">
                                    <div className="flex items-start gap-4">
                                        <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center text-purple-600 group-hover:bg-purple-500 group-hover:text-white transition-colors">
                                            <Mic size={24} />
                                        </div>
                                        <div className="flex-1">
                                            <h3 className="font-semibold text-slate-900 mb-1">面試紀錄</h3>
                                            <p className="text-sm text-slate-500 mb-3">求職面試、候選人評估</p>
                                            <div className="flex flex-wrap gap-2">
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">技能評估</span>
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">優缺點</span>
                                                <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">建議</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Coming Soon */}
                            <div className="mt-8 p-6 bg-gradient-to-r from-slate-50 to-slate-100 rounded-xl border border-dashed border-slate-300">
                                <div className="flex items-center gap-4">
                                    <div className="w-10 h-10 bg-white rounded-lg flex items-center justify-center shadow-sm">
                                        <LayoutTemplate size={20} className="text-slate-400" />
                                    </div>
                                    <div>
                                        <h3 className="font-medium text-slate-700">自訂模板</h3>
                                        <p className="text-sm text-slate-500">即將推出：建立專屬於您團隊的會議摘要模板</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {currentView === 'admin' && (
                        <div className="p-6 md:p-8 max-w-5xl mx-auto overflow-auto">
                            <div className="mb-8">
                                <h1 className="text-2xl font-bold text-slate-900 mb-2">管理</h1>
                                <p className="text-slate-500">系統管理與用戶設定</p>
                            </div>

                            {/* User Profile Card */}
                            <div className="bg-white rounded-xl border border-slate-200 p-6 mb-6">
                                <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
                                    <Shield size={20} className="text-indigo-600" />
                                    當前用戶
                                </h2>
                                <div className="flex items-center gap-4">
                                    {session?.user?.image ? (
                                        <img
                                            src={session.user.image}
                                            alt={session.user.name || 'User'}
                                            className="w-16 h-16 rounded-full"
                                        />
                                    ) : (
                                        <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center text-white text-2xl font-bold">
                                            {session?.user?.name?.charAt(0) || '?'}
                                        </div>
                                    )}
                                    <div>
                                        <p className="text-lg font-medium text-slate-900">{session?.user?.name || '未登入'}</p>
                                        <p className="text-slate-500">{session?.user?.email || '-'}</p>
                                        <span className="inline-flex items-center gap-1 mt-1 px-2 py-0.5 text-xs bg-indigo-100 text-indigo-600 rounded-full">
                                            <Shield size={12} />
                                            管理員
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Stats Grid */}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                                <div className="bg-white rounded-xl border border-slate-200 p-5">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center text-indigo-600">
                                            <FileText size={20} />
                                        </div>
                                        <div>
                                            <p className="text-2xl font-bold text-slate-900">{meetings.length}</p>
                                            <p className="text-sm text-slate-500">會議記錄</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="bg-white rounded-xl border border-slate-200 p-5">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center text-emerald-600">
                                            <LayoutTemplate size={20} />
                                        </div>
                                        <div>
                                            <p className="text-2xl font-bold text-slate-900">4</p>
                                            <p className="text-sm text-slate-500">可用模板</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="bg-white rounded-xl border border-slate-200 p-5">
                                    <div className="flex items-center gap-3">
                                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${isConnected ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-600'}`}>
                                            {isConnected ? <Wifi size={20} /> : <WifiOff size={20} />}
                                        </div>
                                        <div>
                                            <p className="text-2xl font-bold text-slate-900">{isConnected ? 'Online' : 'Offline'}</p>
                                            <p className="text-sm text-slate-500">後端狀態</p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Coming Soon Features */}
                            <div className="bg-white rounded-xl border border-slate-200 p-6">
                                <h2 className="text-lg font-semibold text-slate-900 mb-4">功能規劃</h2>
                                <div className="space-y-3">
                                    <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                                        <div className="w-8 h-8 bg-amber-100 rounded-lg flex items-center justify-center text-amber-600">
                                            <Shield size={16} />
                                        </div>
                                        <div className="flex-1">
                                            <p className="font-medium text-slate-700">Entra ID 整合</p>
                                            <p className="text-xs text-slate-500">企業 SSO 認證</p>
                                        </div>
                                        <span className="px-2 py-1 text-xs bg-amber-100 text-amber-600 rounded">規劃中</span>
                                    </div>
                                    <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                                        <div className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center text-purple-600">
                                            <Settings size={16} />
                                        </div>
                                        <div className="flex-1">
                                            <p className="font-medium text-slate-700">用戶管理</p>
                                            <p className="text-xs text-slate-500">角色權限設定</p>
                                        </div>
                                        <span className="px-2 py-1 text-xs bg-purple-100 text-purple-600 rounded">規劃中</span>
                                    </div>
                                    <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                                        <div className="w-8 h-8 bg-indigo-100 rounded-lg flex items-center justify-center text-indigo-600">
                                            <Calendar size={16} />
                                        </div>
                                        <div className="flex-1">
                                            <p className="font-medium text-slate-700">會議分析</p>
                                            <p className="text-xs text-slate-500">統計報表、趨勢分析</p>
                                        </div>
                                        <span className="px-2 py-1 text-xs bg-indigo-100 text-indigo-600 rounded">規劃中</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
