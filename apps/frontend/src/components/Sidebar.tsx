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
} from 'lucide-react';
import { RestartTourButton } from './TourOverlay';

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
    /** provider = "credentials" 表示 UAT 測試帳號 */
    provider?: string | null;
    onOpenFeedback?: () => void;
    onStartTour?: () => void;
}

export const Sidebar = ({
    activeTab, setActiveTab, isMobileOpen, setIsMobileOpen,
    isConnected, user, provider, onOpenFeedback, onStartTour
}: SidebarProps) => {
    const isUAT = provider === "credentials";
    const [profileOpen, setProfileOpen] = useState(false);

    const menuItems = [
        { id: 'dashboard', icon: FileText, label: '所有會議', primary: true },
        { id: 'rag', icon: MessageSquare, label: '跨會議知識庫', tourId: 'nav-rag' },
        { id: 'templates', icon: LayoutTemplate, label: '模板管理' },
        { id: 'settings', icon: Settings, label: '系統設定' },
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

                <nav className="flex-1 p-4 space-y-2">
                    {menuItems.map((item) => {
                        const className = `w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-colors duration-150 ${
                            item.primary
                                ? activeTab === item.id
                                    ? 'bg-white/15 text-white font-semibold border border-white/20'
                                    : 'bg-white/10 text-white/90 hover:bg-white/15'
                                : activeTab === item.id
                                    ? 'bg-white/10 text-brand-chimei-teal'
                                    : 'text-white/50 hover:bg-white/5 hover:text-white/80'
                        }`;

                        if (item.id === 'rag') {
                            return (
                                <button
                                    key={item.id}
                                    data-tour="nav-rag"
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
                        }

                        return (
                            <button
                                key={item.id}
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
                </nav>

                {onOpenFeedback && (
                    <div className="px-4 pb-2">
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
                    </div>
                )}

                {user && (
                    <div className="px-4 pb-2 relative">
                        <button
                            onClick={() => setProfileOpen(v => !v)}
                            className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-white/5 transition-colors border border-white/10"
                            aria-expanded={profileOpen}
                            aria-haspopup="true"
                        >
                            {user.image ? (
                                <img src={user.image} alt={user.name || 'User'} className="w-9 h-9 rounded-full shrink-0" />
                            ) : (
                                <div className="w-9 h-9 rounded-full bg-brand-cta flex items-center justify-center text-white font-medium shrink-0">
                                    {user.name?.charAt(0) || user.email?.charAt(0) || '?'}
                                </div>
                            )}
                            <div className="flex-1 min-w-0 text-left">
                                <div className="flex items-center gap-1.5">
                                    <p className="text-sm font-medium text-white truncate">{user.name}</p>
                                    {isUAT && (
                                        <span className="flex items-center gap-0.5 px-1.5 py-0.5 bg-white/10 rounded text-[10px] text-white/60 shrink-0">
                                            <FlaskConical size={9} />UAT
                                        </span>
                                    )}
                                </div>
                                <p className="text-xs text-white/40 truncate">{user.email}</p>
                            </div>
                            <ChevronUp
                                size={14}
                                className={`text-white/30 shrink-0 transition-transform duration-200 ${profileOpen ? '' : 'rotate-180'}`}
                            />
                        </button>

                        {profileOpen && (
                            <div className="absolute bottom-full left-4 right-4 mb-1 bg-white rounded-xl shadow-xl border border-border overflow-hidden z-50">
                                <div className="px-4 py-3 border-b border-border">
                                    <p className="text-sm font-semibold text-foreground truncate">{user.name || user.email}</p>
                                    <p className="text-xs text-muted-foreground truncate">{user.email}</p>
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
                )}

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
        </>
    );
};
