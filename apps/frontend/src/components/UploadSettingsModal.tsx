"use client";

import React, { useState, useEffect } from "react";
import { X, Upload, FileAudio, Lock, Languages, FileText, Info } from "lucide-react";
import type { TemplateDTO } from "@/lib/api";
import { useEscape } from "@/hooks/useEscape";

export interface UploadSettings {
    templateName: string;
    language: "zh" | "zh-nan";
    context: string;
    isConfidential: boolean;
}

interface UploadSettingsModalProps {
    files: File[];
    availableTemplates: TemplateDTO[];
    initial: UploadSettings;
    onConfirm: (settings: UploadSettings) => void;
    onCancel: () => void;
}

function formatSize(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * UploadSettingsModal — 上傳前的「步驟 2」設定視窗。
 *
 * 讓使用者在正式上傳前選擇：摘要模板、語言、情境描述、機密標記。
 * 解決 audit U-A2/T-A1：先前 DashboardView 收了這些 props 卻從未渲染，
 * 導致上傳永遠使用預設值（general / 空 / 非機密）。
 */
export function UploadSettingsModal({ files, availableTemplates, initial, onConfirm, onCancel }: UploadSettingsModalProps) {
    const [templateName, setTemplateName] = useState(initial.templateName);
    const [language, setLanguage] = useState<"zh" | "zh-nan">(initial.language);
    const [context, setContext] = useState(initial.context);
    const [isConfidential, setIsConfidential] = useState(initial.isConfidential);

    useEscape(onCancel, true);

    // 僅顯示啟用中的模板；系統模板優先，其次自訂
    const templates = availableTemplates.filter(t => t.is_active !== false);
    const selectedTpl = templates.find(t => t.name === templateName);

    // 若傳入的預設模板不存在（例如清單尚未載入或已刪），退回 general/第一個
    useEffect(() => {
        if (templates.length > 0 && !templates.find(t => t.name === templateName)) {
            setTemplateName(templates.find(t => t.name === "general")?.name || templates[0].name);
        }
    }, [templates, templateName]);

    return (
        <div
            className="fixed inset-0 z-[210] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-settings-title"
            onClick={onCancel}
        >
            <div
                className="bg-card rounded-2xl shadow-2xl border border-border w-full max-w-lg max-h-[90vh] overflow-auto"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-card z-10">
                    <h2 id="upload-settings-title" className="text-lg font-bold text-foreground flex items-center gap-2">
                        <Upload size={18} className="text-brand-cta" /> 上傳設定
                    </h2>
                    <button onClick={onCancel} aria-label="取消上傳" className="p-2 hover:bg-muted rounded-lg text-muted-foreground">
                        <X size={18} />
                    </button>
                </div>

                <div className="px-6 py-5 space-y-5">
                    {/* File list */}
                    <div>
                        <p className="text-xs font-medium text-muted-foreground mb-2">
                            即將上傳 {files.length} 個檔案
                        </p>
                        <div className="max-h-28 overflow-y-auto space-y-1.5 rounded-lg border border-border bg-muted/30 p-2">
                            {files.map((f, i) => (
                                <div key={i} className="flex items-center gap-2 text-sm text-foreground">
                                    <FileAudio size={14} className="text-brand-cta shrink-0" />
                                    <span className="truncate flex-1">{f.name}</span>
                                    <span className="text-[11px] text-muted-foreground shrink-0">{formatSize(f.size)}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Template */}
                    <div>
                        <label htmlFor="us-template" className="block text-sm font-medium text-foreground mb-1 flex items-center gap-1.5">
                            <FileText size={14} className="text-muted-foreground" /> 摘要模板
                        </label>
                        <select
                            id="us-template"
                            value={templateName}
                            onChange={(e) => setTemplateName(e.target.value)}
                            className="w-full px-3 py-2 bg-card border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-cta/40"
                        >
                            {templates.length === 0 && <option value="general">通用</option>}
                            {templates.map(t => (
                                <option key={t.id} value={t.name}>
                                    {t.display_name}{t.is_system ? "" : "（我的）"}
                                </option>
                            ))}
                        </select>
                        <p className="text-xs text-muted-foreground mt-1 flex items-start gap-1">
                            <Info size={12} className="mt-0.5 shrink-0" />
                            {selectedTpl?.description || "不同模板會讓 AI 用不同框架整理摘要。不確定就用「通用」。"}
                        </p>
                    </div>

                    {/* Language */}
                    <div>
                        <label htmlFor="us-lang" className="block text-sm font-medium text-foreground mb-1 flex items-center gap-1.5">
                            <Languages size={14} className="text-muted-foreground" /> 會議語言
                        </label>
                        <select
                            id="us-lang"
                            value={language}
                            onChange={(e) => setLanguage(e.target.value as "zh" | "zh-nan")}
                            className="w-full px-3 py-2 bg-card border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-cta/40"
                        >
                            <option value="zh">國語 + 英語</option>
                            <option value="zh-nan">國語 + 台語 + 英語</option>
                        </select>
                    </div>

                    {/* Context */}
                    <div>
                        <label htmlFor="us-context" className="block text-sm font-medium text-foreground mb-1">
                            情境描述 <span className="text-muted-foreground font-normal">(選填)</span>
                        </label>
                        <textarea
                            id="us-context"
                            value={context}
                            onChange={(e) => setContext(e.target.value)}
                            rows={2}
                            placeholder="例如：這是一場與客戶的產品需求訪談，重點在報價與交期。"
                            className="w-full px-3 py-2 bg-card border border-border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-cta/40"
                        />
                        <p className="text-xs text-muted-foreground mt-1">補充背景可讓摘要更準確；不填也沒關係。</p>
                    </div>

                    {/* Confidential */}
                    <label className="flex items-start gap-3 p-3 rounded-lg border border-border hover:bg-muted/30 cursor-pointer transition-colors">
                        <input
                            type="checkbox"
                            checked={isConfidential}
                            onChange={(e) => setIsConfidential(e.target.checked)}
                            className="mt-0.5 w-4 h-4 accent-brand-cta"
                        />
                        <div className="min-w-0">
                            <span className="text-sm font-medium text-foreground flex items-center gap-1.5">
                                <Lock size={14} className="text-status-error" /> 標記為機密會議
                            </span>
                            <p className="text-xs text-muted-foreground mt-0.5">
                                機密會議在檢視時會套用浮水印，並停用複製/右鍵/列印以降低外洩風險。
                            </p>
                        </div>
                    </label>
                </div>

                {/* Footer */}
                <div className="flex justify-end gap-3 px-6 py-4 border-t border-border sticky bottom-0 bg-card">
                    <button
                        onClick={onCancel}
                        className="px-4 py-2 text-sm bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground transition-colors"
                    >
                        取消
                    </button>
                    <button
                        onClick={() => onConfirm({ templateName, language, context, isConfidential })}
                        className="flex items-center gap-1.5 px-5 py-2 text-sm bg-brand-cta text-white rounded-lg hover:bg-brand-cta/90 font-medium transition-colors shadow-sm"
                    >
                        <Upload size={16} /> 開始上傳
                    </button>
                </div>
            </div>
        </div>
    );
}
