"use client";

import React from 'react';
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
} from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';

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
}

export const Sidebar = ({ activeTab, setActiveTab, isMobileOpen, setIsMobileOpen, isConnected, user, provider, onOpenFeedback }: SidebarProps) => {
    const isUAT = provider === "credentials";

    const menuItems = [
        { id: 'dashboard', icon: FileText, label: '所有會議', primary: true },
        { id: 'rag', icon: MessageSquare, label: '跨會議知識庫' },
        { id: 'templates', icon: LayoutTemplate, label: '模板管理' },
        { id: 'settings', icon: Settings, label: '系統設定' },
    ];

    const sidebarClass = `fixed inset-y-0 left-0 z-50 w-64 bg-brand-navy text-white transform transition-transform duration-300 ease-in-out ${isMobileOpen ? 'translate-x-0' : '-translate-x-full'
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
                    {menuItems.map((item) => (
                        <button
                            key={item.id}
                            onClick={() => {
                                setActiveTab(item.id);
                                setIsMobileOpen(false);
                            }}
                            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-colors duration-150 ${item.primary
                                    ? activeTab === item.id
                                        ? 'bg-white/15 text-white font-semibold border border-white/20'
                                        : 'bg-white/10 text-white/90 hover:bg-white/15'
                                    : activeTab === item.id
                                        ? 'bg-white/10 text-brand-green'
                                        : 'text-white/50 hover:bg-white/5 hover:text-white/80'
                                }`}
                        >
                            <item.icon size={20} />
                            <span className="font-medium">{item.label}</span>
                        </button>
                    ))}
                </nav>

                {/* 回報問題入口 */}
                {onOpenFeedback && (
                    <div className="px-4 pb-2">
                        <button
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

                {/* User Profile Section */}
                {user && (
                    <div className="p-4 border-t border-white/10">
                        <div className="flex items-center gap-3 mb-3">
                            {user.image ? (
                                <img src={user.image} alt={user.name || 'User'} className="w-10 h-10 rounded-full" />
                            ) : (
                                <div className="w-10 h-10 rounded-full bg-brand-cta flex items-center justify-center text-white font-medium">
                                    {user.name?.charAt(0) || user.email?.charAt(0) || '?'}
                                </div>
                            )}
                            <div className="flex-1 min-w-0">
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
                        </div>
                        <button
                            onClick={() => signOut({ callbackUrl: '/login' })}
                            className="w-full flex items-center justify-center gap-2 px-3 py-2 mb-2 text-sm text-white/50 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                        >
                            <LogOut size={16} />
                            <span>登出</span>
                        </button>
                        <ThemeToggle />
                    </div>
                )}

                {/* 系統狀態 — 使用者友善（不暴露 API URL） */}
                <div className="px-4 pb-4">
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5">
                        <div className={`w-2 h-2 rounded-full shrink-0 ${isConnected ? 'bg-status-success animate-pulse' : 'bg-status-error'}`} />
                        <span className="text-xs text-white/50">
                            {isConnected ? '系統運作正常' : '系統暫時無法連線'}
                        </span>
                    </div>
                </div>
            </div>
        </>
    );
};

