"use client";

import React from 'react';
import {
    ChevronRight,
    Wifi,
    WifiOff,
    Moon,
    Sun,
} from 'lucide-react';
import { API_BASE_URL } from '@/lib/api';
import { useTheme } from '@/hooks/useTheme';

export const SettingsView = ({ onBack, isConnected }: { onBack: () => void; isConnected: boolean }) => {
    const { theme, toggleTheme } = useTheme();

    return (
        <div className="p-6 md:p-8 max-w-4xl mx-auto">
            <div className="flex items-center gap-4 mb-8">
                <button onClick={onBack} className="p-2 hover:bg-muted rounded-full text-muted-foreground transition-colors">
                    <ChevronRight size={24} className="rotate-180" />
                </button>
                <h1 className="text-2xl font-bold text-foreground">系統設定</h1>
            </div>

            <div className="space-y-6">
                {/* API Connection */}
                <div className="bg-card rounded-xl border border-border p-6">
                    <h3 className="font-bold text-foreground mb-4">API 連線狀態</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                {isConnected ? (
                                    <Wifi className="text-status-success" size={24} />
                                ) : (
                                    <WifiOff className="text-status-error" size={24} />
                                )}
                                <div>
                                    <p className="font-medium text-foreground">
                                        {isConnected ? '已連線到後端服務' : '無法連線到後端服務'}
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        {isConnected ? '所有功能正常運作' : '請檢查網路連線或後端服務狀態'}
                                    </p>
                                </div>
                            </div>
                            <span className={`px-3 py-1 rounded-full text-sm font-medium ${isConnected ? 'bg-status-success/15 text-status-success' : 'bg-status-error/15 text-status-error'
                                }`}>
                                {isConnected ? 'Online' : 'Offline'}
                            </span>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-foreground/70 mb-1">Backend URL</label>
                            <input
                                type="text"
                                value={API_BASE_URL}
                                readOnly
                                className="w-full px-4 py-2 bg-muted border border-border rounded-lg text-muted-foreground font-mono text-sm"
                            />
                        </div>
                    </div>
                </div>

                {/* Theme Toggle */}
                <div className="bg-card rounded-xl border border-border p-6">
                    <h3 className="font-bold text-foreground mb-4">外觀設定</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                {theme === 'dark' ? <Moon className="text-brand-highlight" size={24} /> : <Sun className="text-status-warning" size={24} />}
                                <div>
                                    <p className="font-medium text-foreground">深色模式</p>
                                    <p className="text-sm text-muted-foreground">
                                        {theme === 'dark' ? '目前使用深色主題' : '目前使用淺色主題'}
                                    </p>
                                </div>
                            </div>
                            <button
                                onClick={toggleTheme}
                                className={`w-12 h-6 rounded-full relative transition-colors cursor-pointer ${theme === 'dark' ? 'bg-brand-highlight' : 'bg-muted-foreground/30'
                                    }`}
                            >
                                <div className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${theme === 'dark' ? 'right-1' : 'left-1'
                                    }`}></div>
                            </button>
                        </div>
                    </div>
                </div>

                {/* ASR Settings (disabled) */}
                <div className="bg-card rounded-xl border border-border p-6">
                    <h3 className="font-bold text-foreground mb-4">語音辨識設定</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between opacity-60">
                            <div>
                                <p className="font-medium text-foreground">自動標點符號</p>
                                <p className="text-sm text-muted-foreground">AI 自動添加逗號、句號</p>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-xs text-muted-foreground">預設開啟</span>
                                <div className="w-12 h-6 bg-muted-foreground/30 rounded-full relative cursor-not-allowed" title="此設定尚未開放調整">
                                    <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full shadow"></div>
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center justify-between opacity-60">
                            <div>
                                <p className="font-medium text-foreground">說話者分離</p>
                                <p className="text-sm text-muted-foreground">自動識別不同說話者</p>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-xs text-muted-foreground">預設開啟</span>
                                <div className="w-12 h-6 bg-muted-foreground/30 rounded-full relative cursor-not-allowed" title="此設定尚未開放調整">
                                    <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full shadow"></div>
                                </div>
                            </div>
                        </div>
                        <p className="text-xs text-muted-foreground italic mt-2">※ 設定調整功能開發中，目前使用後端預設值</p>
                    </div>
                </div>
            </div>
        </div>
    );
};
