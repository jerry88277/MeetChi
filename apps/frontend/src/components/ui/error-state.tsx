"use client";

import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

interface ErrorStateProps {
    /** 錯誤標題（例：「載入失敗」） */
    title?: string;
    /** 錯誤訊息（從 API 來的 detail 字串） */
    message?: string;
    /** Retry callback；提供時顯示「再試一次」按鈕 */
    onRetry?: () => void;
    /** 緊湊版（用於 inline 或 banner） vs 大版（用於 page-level）*/
    variant?: "inline" | "page";
    /** 自訂額外操作（例如「回上一頁」按鈕）*/
    extraAction?: React.ReactNode;
    className?: string;
}

/**
 * ErrorState — 統一錯誤呈現元件（PR-X3 / 對齊 docs/audits 2026-05-10 user-flow audit）。
 *
 * 取代散落各處的 inline banner / toast.error / 自製紅色 div，讓所有錯誤呈現
 * 視覺一致、行為一致（同樣的 retry 按鈕位置、訊息層級、color token）。
 *
 * 兩個變體：
 *   - `inline`（預設）：銀行卡狀，適合在 list/dashboard 上方
 *   - `page`：撐滿空間並置中，適合 detail 頁主區域當完全失敗 fallback
 */
export function ErrorState({
    title = "發生錯誤",
    message,
    onRetry,
    variant = "inline",
    extraAction,
    className = "",
}: ErrorStateProps) {
    if (variant === "page") {
        return (
            <div className={`flex flex-col items-center justify-center py-16 px-4 text-center ${className}`}>
                <div className="bg-status-error/10 p-4 rounded-full mb-4">
                    <AlertCircle className="w-10 h-10 text-status-error" />
                </div>
                <h3 className="text-lg font-bold text-foreground mb-1">{title}</h3>
                {message && (
                    <p className="text-sm text-muted-foreground max-w-md mb-6 leading-relaxed">
                        {message}
                    </p>
                )}
                <div className="flex flex-col sm:flex-row gap-2">
                    {onRetry && (
                        <button
                            onClick={onRetry}
                            className="flex items-center gap-2 px-4 py-2 bg-brand-cta text-white rounded-lg hover:bg-brand-cta/90 transition-colors text-sm font-medium"
                        >
                            <RefreshCw size={14} /> 再試一次
                        </button>
                    )}
                    {extraAction}
                </div>
            </div>
        );
    }

    return (
        <div
            role="alert"
            className={`bg-status-error/10 border border-status-error/30 rounded-xl p-4 flex items-start gap-3 ${className}`}
        >
            <AlertCircle className="w-5 h-5 text-status-error flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
                <p className="font-medium text-status-error text-sm">{title}</p>
                {message && (
                    <p className="text-sm text-foreground/80 mt-1 break-words">{message}</p>
                )}
            </div>
            {(onRetry || extraAction) && (
                <div className="flex items-center gap-2 flex-shrink-0">
                    {onRetry && (
                        <button
                            onClick={onRetry}
                            aria-label="再試一次"
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-status-error hover:bg-status-error/10 rounded-lg transition-colors"
                        >
                            <RefreshCw size={12} /> 再試
                        </button>
                    )}
                    {extraAction}
                </div>
            )}
        </div>
    );
}
