"use client";

import React from 'react';
import { signOut } from 'next-auth/react';
import {
    FileText,
    Settings,
    X,
    LogOut,
    Shield,
    LayoutTemplate,
    MessageSquare,
} from 'lucide-react';
import { API_BASE_URL } from '@/lib/api';
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
}

export const Sidebar = ({ activeTab, setActiveTab, isMobileOpen, setIsMobileOpen, isConnected, user }: SidebarProps) => {
    const menuItems = [
        { id: 'dashboard', icon: FileText, label: '所有會議', primary: true },
        { id: 'rag', icon: MessageSquare, label: '跨會議知識庫' },
        { id: 'templates', icon: LayoutTemplate, label: '模板管理' },
        { id: 'admin', icon: Shield, label: '管理' },
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
                            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${item.primary
                                    ? 'bg-gradient-to-r from-brand-cta to-brand-cta/80 text-white shadow-lg shadow-brand-cta/30 hover:shadow-brand-cta/50'
                                    : activeTab === item.id
                                        ? 'bg-white/10 text-brand-highlight'
                                        : 'text-white/50 hover:bg-white/5 hover:text-white/80'
                                }`}
                        >
                            <item.icon size={20} />
                            <span className="font-medium">{item.label}</span>
                        </button>
                    ))}
                </nav>

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
                                <p className="text-sm font-medium text-white truncate">{user.name}</p>
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

                {/* Backend Status */}
                <div className="p-4 border-t border-white/10">
                    <div className="bg-white/5 rounded-xl p-4">
                        <p className="text-xs text-white/40 mb-2">後端狀態</p>
                        <div className="flex items-center gap-2 mb-1">
                            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-status-success animate-pulse' : 'bg-status-error'}`}></div>
                            <span className="text-xs font-mono text-white/70">
                                {isConnected ? '已連線' : '未連線'}
                            </span>
                        </div>
                        <p className="text-xs text-white/30 truncate" title={API_BASE_URL}>
                            {API_BASE_URL.replace('https://', '').substring(0, 25)}...
                        </p>
                    </div>
                </div>
            </div>
        </>
    );
};
