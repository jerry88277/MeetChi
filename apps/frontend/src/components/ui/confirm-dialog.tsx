"use client";

import React from "react";
import { AlertTriangle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useEscape } from "@/hooks/useEscape";

export interface ConfirmDialogProps {
    open: boolean;
    title: string;
    description?: string;
    confirmText?: string;
    cancelText?: string;
    /** "destructive" 顯示紅色按鈕；"primary" 顯示主色按鈕。預設 "destructive". */
    variant?: "destructive" | "primary";
    onConfirm: () => void;
    onCancel: () => void;
}

/**
 * 取代 `window.confirm()` 與 `prompt()` 的可控 Modal 元件。
 *
 * 用法：
 *   const [pending, setPending] = useState<{ key: string } | null>(null);
 *   ...
 *   <ConfirmDialog
 *     open={!!pending}
 *     title="確定刪除嗎？"
 *     description="刪除後無法復原。"
 *     onConfirm={() => { handleDelete(pending!.key); setPending(null); }}
 *     onCancel={() => setPending(null)}
 *   />
 *
 * 設計：
 *   - 預設 destructive variant（紅色），因為大部分 confirm 是刪除/放棄類
 *   - 支援 Esc 關閉 → 等同 cancel
 *   - 點 backdrop 關閉 → 等同 cancel
 *   - 不依賴 portal/radix；用 fixed 定位的最小實作避免 dep 膨脹
 */
export function ConfirmDialog({
    open,
    title,
    description,
    confirmText = "確認",
    cancelText = "取消",
    variant = "destructive",
    onConfirm,
    onCancel,
}: ConfirmDialogProps) {
    useEscape(onCancel, open);

    if (!open) return null;

    const confirmClass =
        variant === "destructive"
            ? "bg-status-error text-white hover:bg-status-error/90"
            : "bg-brand-cta text-white hover:bg-brand-cta/90";

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-in fade-in duration-150"
            onClick={onCancel}
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-dialog-title"
        >
            <div
                className="relative bg-background rounded-2xl shadow-2xl max-w-md w-[90vw] p-6 animate-in zoom-in-95 duration-150"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Close button */}
                <button
                    onClick={onCancel}
                    className="absolute top-4 right-4 text-muted-foreground hover:text-foreground transition-colors"
                    aria-label="關閉"
                >
                    <X size={18} />
                </button>

                {/* Icon */}
                <div className="flex items-start gap-4">
                    <div
                        className={`shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
                            variant === "destructive"
                                ? "bg-status-error/10 text-status-error"
                                : "bg-brand-cta/10 text-brand-cta"
                        }`}
                    >
                        <AlertTriangle size={20} />
                    </div>
                    <div className="flex-1 pt-1">
                        <h3
                            id="confirm-dialog-title"
                            className="text-lg font-semibold text-foreground"
                        >
                            {title}
                        </h3>
                        {description && (
                            <p className="mt-2 text-sm text-muted-foreground leading-relaxed whitespace-pre-line">
                                {description}
                            </p>
                        )}
                    </div>
                </div>

                {/* Actions */}
                <div className="mt-6 flex justify-end gap-2">
                    <Button variant="outline" onClick={onCancel}>
                        {cancelText}
                    </Button>
                    <button
                        onClick={onConfirm}
                        className={`px-4 py-2 rounded-md text-sm font-medium transition-all active:scale-[0.98] ${confirmClass}`}
                    >
                        {confirmText}
                    </button>
                </div>
            </div>
        </div>
    );
}
