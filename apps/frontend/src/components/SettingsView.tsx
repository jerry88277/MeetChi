"use client";

import React from 'react';
import {
    ChevronRight,
    Wifi,
    WifiOff,
    Moon,
    Sun,
    Loader2,
    Type,
    RotateCcw,
} from 'lucide-react';
import { API_BASE_URL } from '@/lib/api';
// 2026-05-25 (Y1)：原 useTheme 用 data-theme attribute，與 providers 掛的
// next-themes (.dark class) 不相容 → toggle 無視覺變化。改用 next-themes 統一。
import { useTheme } from 'next-themes';
import { useFontSize, MIN_FONT_PCT, MAX_FONT_PCT, DEFAULT_FONT_PCT } from '@/hooks/useFontSize';

interface SettingsViewProps {
    onBack: () => void;
    isConnected: boolean;
    /** P1 (audit 2026-05-10)：父層尚未完成 health check 時為 true，避免顯示假 Offline */
    isLoadingConnection?: boolean;
}

export const SettingsView = ({ onBack, isConnected, isLoadingConnection = false }: SettingsViewProps) => {
    // next-themes：resolvedTheme 含 system → light/dark 已 resolve；setTheme 直接寫 .dark class
    const { resolvedTheme, setTheme } = useTheme();
    const [mounted, setMounted] = React.useState(false);
    React.useEffect(() => setMounted(true), []);
    const theme: 'dark' | 'light' = (mounted ? (resolvedTheme as 'dark' | 'light') : 'light') || 'light';
    const toggleTheme = () => setTheme(theme === 'dark' ? 'light' : 'dark');
    const { fontSizePct, setFontSizePct, reset: resetFontSize } = useFontSize();

    return (
        <div className="p-6 md:p-8 max-w-4xl mx-auto">
            <div className="flex items-center gap-4 mb-8">
                <button onClick={onBack} className="p-2 hover:bg-muted rounded-full text-muted-foreground transition-colors">
                    <ChevronRight size={24} className="rotate-180" />
                </button>
                <h1 className="text-2xl font-bold text-foreground">系統設定</h1>
            </div>

            <div className="space-y-6">
                {/* API Connection — P1：補 loading skeleton 避免假 Offline 閃爍 */}
                <div className="bg-card rounded-xl border border-border p-6">
                    <h3 className="font-bold text-foreground mb-4">API 連線狀態</h3>
                    <div className="space-y-4">
                        {isLoadingConnection ? (
                            <div className="flex items-center justify-between" aria-busy="true" aria-live="polite">
                                <div className="flex items-center gap-3">
                                    <Loader2 className="text-muted-foreground animate-spin" size={24} />
                                    <div className="flex-1">
                                        <div className="h-4 w-44 bg-muted rounded animate-pulse mb-2" />
                                        <div className="h-3 w-32 bg-muted/70 rounded animate-pulse" />
                                    </div>
                                </div>
                                <span className="px-3 py-1 rounded-full text-sm font-medium bg-muted text-muted-foreground">
                                    檢查中...
                                </span>
                            </div>
                        ) : (
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
                        )}
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
                                {theme === 'dark' ? <Moon className="text-brand-green" size={24} /> : <Sun className="text-status-warning" size={24} />}
                                <div>
                                    <p className="font-medium text-foreground">深色模式</p>
                                    <p className="text-sm text-muted-foreground">
                                        {theme === 'dark' ? '目前使用深色主題' : '目前使用淺色主題'}
                                    </p>
                                </div>
                            </div>
                            <button
                                type="button"
                                role="switch"
                                aria-checked={theme === 'dark'}
                                aria-label={theme === 'dark' ? '切換為淺色模式' : '切換為深色模式'}
                                onClick={toggleTheme}
                                className={`w-12 h-6 rounded-full relative transition-colors cursor-pointer ${theme === 'dark' ? 'bg-brand-green' : 'bg-muted-foreground/30'
                                    }`}
                            >
                                <div aria-hidden="true" className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${theme === 'dark' ? 'right-1' : 'left-1'
                                    }`}></div>
                            </button>
                        </div>
                    </div>
                </div>

                {/* 2026-05-24 (request #2)：字體大小設定，給高齡使用者放大用。
                    全域 root font-size 縮放，所有 rem 單位元素同步調整。 */}
                <div className="bg-card rounded-xl border border-border p-6">
                    <h3 className="font-bold text-foreground mb-4 flex items-center gap-2">
                        <Type size={18} /> 字體大小
                    </h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between gap-4">
                            <div className="flex-1">
                                <p className="font-medium text-foreground">介面字體縮放</p>
                                <p className="text-sm text-muted-foreground">
                                    調整整個應用程式的文字大小（{MIN_FONT_PCT}% – {MAX_FONT_PCT}%）
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={resetFontSize}
                                className="px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground border border-border hover:border-brand-cta rounded-lg transition-colors flex items-center gap-1.5"
                                title="重設為預設大小（100%）"
                                disabled={fontSizePct === DEFAULT_FONT_PCT}
                            >
                                <RotateCcw size={12} /> 重設
                            </button>
                        </div>
                        <div className="flex items-center gap-3">
                            <button
                                type="button"
                                onClick={() => setFontSizePct(fontSizePct - 5)}
                                disabled={fontSizePct <= MIN_FONT_PCT}
                                className="w-9 h-9 rounded-full border border-border hover:border-brand-cta text-foreground hover:text-brand-cta font-bold disabled:opacity-30 transition-colors"
                                aria-label="縮小字體"
                            >
                                A-
                            </button>
                            <input
                                type="range"
                                min={MIN_FONT_PCT}
                                max={MAX_FONT_PCT}
                                step={5}
                                value={fontSizePct}
                                onChange={(e) => setFontSizePct(parseInt(e.target.value, 10))}
                                className="flex-1 h-2 accent-brand-cta cursor-pointer"
                                aria-label="字體縮放比例"
                            />
                            <button
                                type="button"
                                onClick={() => setFontSizePct(fontSizePct + 5)}
                                disabled={fontSizePct >= MAX_FONT_PCT}
                                className="w-9 h-9 rounded-full border border-border hover:border-brand-cta text-foreground hover:text-brand-cta font-bold disabled:opacity-30 transition-colors text-lg"
                                aria-label="放大字體"
                            >
                                A+
                            </button>
                            <div className="w-16 text-center">
                                <input
                                    type="number"
                                    min={MIN_FONT_PCT}
                                    max={MAX_FONT_PCT}
                                    step={5}
                                    value={fontSizePct}
                                    onChange={(e) => {
                                        const v = parseInt(e.target.value, 10);
                                        if (Number.isFinite(v)) setFontSizePct(v);
                                    }}
                                    className="w-full px-2 py-1.5 text-sm text-center border border-border rounded-lg bg-surface text-foreground focus:border-brand-cta focus:outline-none font-mono"
                                />
                                <span className="text-xs text-muted-foreground">%</span>
                            </div>
                        </div>
                        <p className="text-xs text-muted-foreground italic">
                            預覽：這段範例文字會隨設定立即變化，方便您找出最舒適的閱讀大小。
                        </p>
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
