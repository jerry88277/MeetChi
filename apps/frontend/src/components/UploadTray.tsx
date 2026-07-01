"use client";

import React from "react";
import {
    ChevronDown,
    ChevronUp,
    CheckCircle2,
    Loader2,
    AlertCircle,
    UploadCloud,
    Trash2,
    X,
} from "lucide-react";
import type { UploadTask } from "@/hooks/useUploadQueue";

interface UploadTrayProps {
    tasks: UploadTask[];
    isOpen: boolean;
    onToggle: () => void;
    onRetry: (taskId: string) => void;
    onRemove: (taskId: string) => void;
    onCancel: (taskId: string) => void;
    onClearCompleted: () => void;
}

function formatSize(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function TaskStatusIcon({ status }: { status: UploadTask["status"] }) {
    switch (status) {
        case "queued":
            return <UploadCloud size={14} className="text-muted-foreground" />;
        case "uploading":
            return <Loader2 size={14} className="text-brand-cta animate-spin" />;
        case "processing":
            return <Loader2 size={14} className="text-brand-chimei-teal animate-spin" />;
        case "done":
            return <CheckCircle2 size={14} className="text-status-success" />;
        case "error":
            return <AlertCircle size={14} className="text-status-error" />;
    }
}

function statusLabel(status: UploadTask["status"], progress: number, fileSize?: number): string {
    switch (status) {
        case "queued": return "排隊中";
        case "uploading": return `${progress}%`;
        case "processing": {
            // Estimate based on file size: ~1MB ≈ 60s audio, ratio 0.15 for long
            if (fileSize && fileSize > 0) {
                const estAudioSec = (fileSize / (1024 * 1024)) * 60;
                const ratio = estAudioSec > 1200 ? 0.15 : 0.35;
                const estMin = Math.ceil((estAudioSec * ratio + 90) / 60);
                return `AI 處理中（約 ${estMin} 分鐘）`;
            }
            return "AI 處理中";
        }
        case "done": return "完成";
        case "error": return "失敗";
    }
}

/**
 * UploadTray — Bottom-right floating panel (Google Drive style).
 * Shows all upload tasks with progress, retries, and queue status.
 */
export function UploadTray({ tasks, isOpen, onToggle, onRetry, onRemove, onCancel, onClearCompleted }: UploadTrayProps) {
    if (tasks.length === 0) return null;

    const activeCount = tasks.filter(t => t.status === "uploading" || t.status === "processing").length;
    const doneCount = tasks.filter(t => t.status === "done").length;
    const totalCount = tasks.length;

    return (
        <div className="fixed bottom-4 right-4 z-[100] w-[min(22rem,calc(100vw-2rem))] shadow-2xl rounded-xl border border-border bg-card overflow-hidden transition-all">
            {/* Header — always visible */}
            <button
                type="button"
                onClick={onToggle}
                className="w-full flex items-center justify-between px-4 py-3 bg-card hover:bg-muted/50 transition-colors border-b border-border"
            >
                <div className="flex items-center gap-2">
                    <UploadCloud size={16} className="text-brand-cta" />
                    <span className="text-sm font-medium text-foreground">
                        {activeCount > 0
                            ? `上傳中 (${activeCount}/${totalCount})`
                            : `上傳完成 (${doneCount}/${totalCount})`
                        }
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    {doneCount > 0 && doneCount === totalCount && (
                        <span
                            onClick={(e) => { e.stopPropagation(); onClearCompleted(); }}
                            className="text-[10px] text-muted-foreground hover:text-foreground cursor-pointer"
                        >
                            清除
                        </span>
                    )}
                    {isOpen ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronUp size={14} className="text-muted-foreground" />}
                </div>
            </button>

            {/* Task list — collapsible */}
            {isOpen && (
                <div className="max-h-64 overflow-y-auto divide-y divide-border">
                    {tasks.map(task => (
                        <div key={task.id} className="px-4 py-2.5 flex items-center gap-3 group">
                            <TaskStatusIcon status={task.status} />
                            <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium text-foreground truncate">{task.fileName}</p>
                                <div className="flex items-center gap-2 mt-0.5">
                                    <span className="text-[10px] text-muted-foreground">
                                        {formatSize(task.fileSize)}
                                    </span>
                                    <span className="text-[10px] text-muted-foreground">·</span>
                                    <span className={`text-[10px] font-medium ${
                                        task.status === "error" ? "text-status-error" :
                                        task.status === "done" ? "text-status-success" :
                                        "text-muted-foreground"
                                    }`}>
                                        {statusLabel(task.status, task.progress, task.fileSize)}
                                    </span>
                                </div>
                                {/* Progress bar for uploading state */}
                                {task.status === "uploading" && (
                                    <div className="mt-1 w-full bg-muted rounded-full h-1.5 overflow-hidden">
                                        <div
                                            className="bg-brand-cta h-full transition-all duration-300 ease-out"
                                            style={{ width: `${task.progress}%` }}
                                        />
                                    </div>
                                )}
                                {task.status === "error" && (
                                    <div className="mt-1 flex items-center gap-2">
                                        {task.error && (
                                            <p className="flex-1 text-[10px] text-status-error line-clamp-1">{task.error}</p>
                                        )}
                                        <button
                                            type="button"
                                            onClick={() => onRetry(task.id)}
                                            className="shrink-0 text-[10px] font-medium text-brand-cta hover:text-brand-cta/80 transition-colors"
                                            title="重試"
                                        >
                                            重試
                                        </button>
                                    </div>
                                )}
                            </div>
                            {/* Actions */}
                            <div className="flex items-center gap-1">
                                {/* Cancel — visible during active upload (U-B2) */}
                                {task.status === "uploading" && (
                                    <button
                                        onClick={() => onCancel(task.id)}
                                        className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-status-error transition-colors"
                                        title="取消上傳"
                                        aria-label="取消上傳"
                                    >
                                        <X size={14} />
                                    </button>
                                )}
                                {(task.status === "done" || task.status === "error" || task.status === "queued") && (
                                    <button
                                        onClick={() => task.status === "queued" ? onCancel(task.id) : onRemove(task.id)}
                                        className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-status-error transition-colors opacity-0 group-hover:opacity-100"
                                        title={task.status === "queued" ? "取消" : "移除"}
                                    >
                                        <Trash2 size={12} />
                                    </button>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
