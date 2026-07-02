"use client";

import React, { useState } from 'react';
import { signOut } from 'next-auth/react';
import {
    FileText,
    Settings,
    X,
    LogOut,
    LayoutTemplate,
    MessageSquare,
    MessageSquareWarning,
    FlaskConical,
    ChevronUp,
    HelpCircle,
    Map,
} from 'lucide-react';
import { RestartTourButton } from './TourOverlay';

interface SidebarProps {
    activeTab: string;
    setActiveTab: (tab: string) => void;
    isMobileOpen: boolean;
    setIsMobileOpen: (open: boolean) => void;
    isConnected: boolean;
    isAdmin?: boolean;
    user?: {
        name?: string | null;
        email?: string | null;
        image?: string | null;
    };
    /** provider = "credentials" 表示 UAT 測試帳號 */
    provider?: string | null;
    onOpenFeedback?: () => void;
    onStartTour?: () => void;
}

export const Sidebar = ({
    activeTab, setActiveTab, isMobileOpen, setIsMobileOpen,
    isConnected, isAdmin, user, provider, onOpenFeedback, onStartTour
}: SidebarProps) => {
    const isUAT = provider === "credentials";
    const [profileOpen, setProfileOpen] = useState(false);
    // CS-7：常駐「使用說明」入口——冷啟動者卡住時的求助出口（含重播導覽 + FAQ）
    const [helpOpen, setHelpOpen] = useState(false);

    const workspaceItems = [
        { id: 'dashboard', icon: FileText, label: '所有會議', primary: true, subtitle: undefined as string | undefined },
        { id: 'rag', icon: MessageSquare, label: 'ChiMemo', tourId: 'nav-rag', subtitle: '跨會議 AI 搜尋' },
    ];

    const systemItems = [
        { id: 'templates', icon: LayoutTemplate, label: '模板管理', tourId: 'nav-templates' as string | undefined },
        { id: 'settings', icon: Settings, label: '系統設定', tourId: 'nav-settings' as string | undefined },
        ...(isAdmin ? [{ id: 'admin', icon: FlaskConical, label: '系統維運', tourId: undefined as string | undefined }] : []),
    ];

    const sidebarClass = `fixed inset-y-0 left-0 z-50 w-64 bg-brand-navy text-white transform transition-transform duration-300 ease-in-out ${
        isMobileOpen ? 'translate-x-0' : '-translate-x-full'
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
                <div className="p-6 border-b border-white/10 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 bg-brand-cta rounded-lg flex items-center justify-center">
                            <span className="font-bold text-white">M</span>
                        </div>
                        <span className="text-xl font-bold tracking-tight">MeetChi</span>
                    </div>
                    <button onClick={() => setIsMobileOpen(false)} className="md:hidden text-white/50">
                        <X size={24} />
                    </button>
                </div>

                <nav className="flex-1 p-4 space-y-1">
                    {/* 工作區 */}
                    <p className="px-4 pt-2 pb-1 text-[10px] uppercase tracking-widest text-white/30 font-semibold">工作區</p>
                    {workspaceItems.map((item) => {
                        const className = `w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-colors duration-150 ${
                            item.primary
                                ? activeTab === item.id
                                    ? 'bg-white/15 text-white font-semibold border border-white/20'
                                    : 'bg-white/10 text-white/90 hover:bg-white/15'
                                : activeTab === item.id
                                    ? 'bg-white/10 text-brand-chimei-teal'
                                    : 'text-white/50 hover:bg-white/5 hover:text-white/80'
                        }`;

                        return (
                            <button
                                key={item.id}
                                data-tour={item.tourId}
                                onClick={() => {
                                    setActiveTab(item.id);
                                    setIsMobileOpen(false);
                                }}
                                className={className}
                            >
                                <item.icon size={20} />
                                {/* CS-9：ChiMemo 品牌字加副標，跳過導覽也能理解用途 */}
                                <span className="flex flex-col items-start leading-tight">
                                    <span className="font-medium">{item.label}</span>
                                    {item.subtitle && (
                                        <span className="text-[10px] text-white/40 font-normal">{item.subtitle}</span>
                                    )}
                                </span>
                            </button>
                        );
                    })}

                    {/* 系統 */}
                    <div className="pt-4">
                        <p className="px-4 pt-2 pb-1 text-[10px] uppercase tracking-widest text-white/30 font-semibold">系統</p>
                        {systemItems.map((item) => {
                            const className = `w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-colors duration-150 ${
                                activeTab === item.id
                                    ? 'bg-white/10 text-brand-chimei-teal'
                                    : 'text-white/50 hover:bg-white/5 hover:text-white/80'
                            }`;

                            return (
                                <button
                                    key={item.id}
                                    data-tour={item.tourId}
                                    onClick={() => {
                                        setActiveTab(item.id);
                                        setIsMobileOpen(false);
                                    }}
                                    className={className}
                                >
                                    <item.icon size={20} />
                                    <span className="font-medium">{item.label}</span>
                                </button>
                            );
                        })}
                    </div>
                </nav>

                {/* CS-7：使用說明 + 回報問題（常駐求助入口） */}
                <div className="px-4 pb-2 space-y-2">
                    <button
                        onClick={() => setHelpOpen(true)}
                        className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-white/60 hover:text-white hover:bg-white/5 border border-white/10 rounded-lg transition-colors"
                        title="使用說明與教學"
                    >
                        <HelpCircle size={16} />
                        <span className="font-medium">使用說明</span>
                    </button>
                    {onOpenFeedback && (
                        <button
                            data-tour="feedback-btn"
                            onClick={onOpenFeedback}
                            className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-white/60 hover:text-white hover:bg-white/5 border border-white/10 hover:border-brand-orange/40 rounded-lg transition-colors"
                            title="回報問題或建議"
                        >
                            <MessageSquareWarning size={16} />
                            <span className="font-medium">回報問題</span>
                            <span className="ml-auto text-[10px] text-white/30">Beta</span>
                        </button>
                    )}
                </div>

                {/* Profile section — always visible (Design Advisor: 兩層互動架構) */}
                <div className="px-4 pb-2 relative">
                    <button
                        onClick={() => setProfileOpen(v => !v)}
                        className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-white/5 transition-colors border border-white/10"
                        aria-expanded={profileOpen}
                        aria-haspopup="true"
                    >
                        {user?.image ? (
                            <img src={user.image} alt={user.name || 'User'} className="w-9 h-9 rounded-full shrink-0" />
                        ) : (
                            <div className="w-9 h-9 rounded-full bg-brand-cta flex items-center justify-center text-white font-medium shrink-0">
                                {user?.name?.charAt(0) || user?.email?.charAt(0) || '?'}
                            </div>
                        )}
                        <div className="flex-1 min-w-0 text-left">
                            <div className="flex items-center gap-1.5">
                                <p className="text-sm font-medium text-white truncate">
                                    {user?.name || user?.email?.split('@')[0] || '載入中...'}
                                </p>
                                {isUAT && (
                                    <span className="flex items-center gap-0.5 px-1.5 py-0.5 bg-white/10 rounded text-[10px] text-white/60 shrink-0">
                                        <FlaskConical size={9} />UAT
                                    </span>
                                )}
                            </div>
                            <p className="text-xs text-white/40 truncate">{user?.email || '...'}</p>
                        </div>
                        <ChevronUp
                            size={14}
                            className={`text-white/30 shrink-0 transition-transform duration-200 ${profileOpen ? '' : 'rotate-180'}`}
                        />
                    </button>

                    {profileOpen && (
                        <div className="absolute bottom-full left-4 right-4 mb-1 bg-white rounded-xl shadow-xl border border-border overflow-hidden z-50">
                            <div className="px-4 py-3 border-b border-border">
                                <p className="text-sm font-semibold text-foreground truncate">{user?.name || user?.email || '使用者'}</p>
                                <p className="text-xs text-muted-foreground truncate">{user?.email || ''}</p>
                            </div>
                            <button
                                onClick={() => signOut({ callbackUrl: '/login' })}
                                className="w-full flex items-center gap-2 px-4 py-3 text-sm text-status-error hover:bg-status-error/5 transition-colors"
                            >
                                <LogOut size={15} />
                                <span>登出</span>
                            </button>
                        </div>
                    )}
                </div>

                <div className="px-4 pb-4 flex items-center justify-between">
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 flex-1 mr-2">
                        <div className={`w-2 h-2 rounded-full shrink-0 ${isConnected ? 'bg-status-success animate-pulse' : 'bg-status-error'}`} />
                        <span className="text-xs text-white/50">
                            {isConnected ? '所有系統正常運行' : '目前無法連線，請稍後再試'}
                        </span>
                    </div>
                    {onStartTour && <RestartTourButton onClick={onStartTour} />}
                </div>
            </div>

            {/* CS-7：使用說明 / 教學 Modal */}
            {helpOpen && (
                <div className="fixed inset-0 z-[60] bg-black/50 flex items-center justify-center p-4" onClick={() => setHelpOpen(false)}>
                    <div className="bg-card text-foreground rounded-2xl border border-border max-w-md w-full max-h-[85vh] overflow-auto p-6" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-bold flex items-center gap-2"><HelpCircle size={18} className="text-brand-cta" /> 使用說明</h2>
                            <button onClick={() => setHelpOpen(false)} aria-label="關閉說明" className="p-2 hover:bg-muted rounded-lg text-muted-foreground"><X size={18} /></button>
                        </div>

                        {onStartTour && (
                            <button
                                onClick={() => { setHelpOpen(false); onStartTour(); }}
                                className="w-full flex items-center gap-2 px-4 py-3 mb-4 bg-brand-cta text-white rounded-xl hover:bg-brand-cta/90 transition-colors text-sm font-medium"
                            >
                                <Map size={16} /> 重新播放 1 分鐘功能導覽
                            </button>
                        )}

                        <div className="space-y-4 text-sm">
                            <div>
                                <p className="font-semibold mb-1">MeetChi 是什麼？</p>
                                <p className="text-muted-foreground leading-relaxed">把開會的錄音變成文字，再自動整理出摘要、決定了什麼、待辦事項與要注意的風險。</p>
                            </div>
                            <div>
                                <p className="font-semibold mb-1">怎麼開始？</p>
                                <ol className="text-muted-foreground leading-relaxed list-decimal pl-5 space-y-1">
                                    <li>點右上角「上傳音檔」，選一個錄音檔（.m4a / .mp3 / .wav）。</li>
                                    <li>選會議語言與摘要模板（不確定就用「通用」）。</li>
                                    <li>等幾分鐘，AI 整理好後點會議卡片看結果。</li>
                                </ol>
                            </div>
                            <div>
                                <p className="font-semibold mb-1">常見問題</p>
                                <ul className="text-muted-foreground leading-relaxed space-y-2">
                                    <li><span className="text-foreground">Q：模板要選哪個？</span><br/>不確定就用「通用」，之後可在「模板管理」調整或設為預設。</li>
                                    <li><span className="text-foreground">Q：ChiMemo 是什麼？</span><br/>可以一次問所有會議的問題，例如「上週決定的預算是多少？」。</li>
                                    <li><span className="text-foreground">Q：機密會議？</span><br/>勾選後檢視時會加浮水印並停用複製/列印，降低外洩風險。</li>
                                    <li><span className="text-foreground">Q：還是卡住？</span><br/>用左側「回報問題」告訴我們，會盡快協助。</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};
