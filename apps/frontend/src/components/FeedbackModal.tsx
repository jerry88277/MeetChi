"use client";

import React, { useState } from "react";
import {
    X,
    Loader2,
    AlertCircle,
    CheckCircle2,
    MessageSquare,
    FileText,
    Wrench,
    AlertTriangle,
    HelpCircle,
    ChevronRight,
    Send,
    Link2,
    Link2Off,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type {
    FeedbackIssueType,
    FeedbackSeverity,
    FeedbackFrequency,
} from "@/lib/api";
import { collectFeedbackMetadata } from "@/lib/feedback-metadata";

interface FeedbackModalProps {
    isOpen: boolean;
    onClose: () => void;
    userUpn: string;
    /** 觸發來源（system_error 自動觸發 / 使用者主動點 / 跟某個 meeting 綁定） */
    initialIssueType?: FeedbackIssueType;
    meetingId?: string;
    /** 額外帶入的 prefill summary（例如錯誤觸發時的 error message） */
    prefillSummary?: string;
}

const ISSUE_TYPE_OPTIONS: Array<{
    value: FeedbackIssueType;
    label: string;
    icon: React.ReactNode;
    desc: string;
}> = [
    {
        value: "summary_wrong",
        label: "摘要不對",
        icon: <FileText size={18} />,
        desc: "AI 摘要漏抓重點 / 內容錯誤",
    },
    {
        value: "transcript_inaccurate",
        label: "逐字稿不準",
        icon: <MessageSquare size={18} />,
        desc: "轉錄錯字、講者錯認",
    },
    {
        value: "ui_clunky",
        label: "操作不順",
        icon: <Wrench size={18} />,
        desc: "按鈕難找 / 流程卡卡",
    },
    {
        value: "system_error",
        label: "系統錯誤",
        icon: <AlertTriangle size={18} />,
        desc: "畫面壞掉 / 上傳失敗",
    },
    {
        value: "other",
        label: "其他",
        icon: <HelpCircle size={18} />,
        desc: "建議、提問、其他",
    },
];

const SEVERITY_OPTIONS: Array<{
    value: FeedbackSeverity;
    label: string;
    desc: string;
    cls: string;
}> = [
    {
        value: "minor",
        label: "輕微",
        desc: "影響不大",
        cls: "border-status-success/40 bg-status-success/5 text-status-success",
    },
    {
        value: "workaround",
        label: "需繞道",
        desc: "我有方法但不順",
        cls: "border-brand-orange/40 bg-brand-orange/5 text-brand-orange",
    },
    {
        value: "blocker",
        label: "卡死",
        desc: "完全做不下去",
        cls: "border-status-error/40 bg-status-error/5 text-status-error",
    },
];

const FREQUENCY_OPTIONS: Array<{ value: FeedbackFrequency; label: string }> = [
    { value: "first", label: "第一次遇到" },
    { value: "rare", label: "偶爾發生" },
    { value: "common", label: "常常發生" },
    { value: "always", label: "每次都這樣" },
];

/**
 * 從當前 page URL 嘗試 parse `/dashboard/meetings/{id}` 抓 meeting_id。
 * Sidebar 入口開 modal 時 meetingId prop = undefined，但若使用者剛好停在
 * 詳情頁，仍然能補回上下文（雙保險）。
 *
 * 2026-05-12 加入：解決使用者從 sidebar 開回報 → IT 收到無 meeting_id 的
 * feedback → 無法定位問題的 UX 漏洞。
 */
function parseMeetingIdFromUrl(): string | undefined {
    if (typeof window === "undefined") return undefined;
    const match = window.location.pathname.match(
        /\/dashboard\/meetings\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i
    );
    return match?.[1];
}

export const FeedbackModal = ({
    isOpen,
    onClose,
    userUpn,
    initialIssueType,
    meetingId,
    prefillSummary,
}: FeedbackModalProps) => {
    const [stage, setStage] = useState<1 | 2>(1);
    const [issueType, setIssueType] = useState<FeedbackIssueType | "">(
        initialIssueType ?? ""
    );
    const [summary, setSummary] = useState(prefillSummary ?? "");
    const [severity, setSeverity] = useState<FeedbackSeverity | "">("");
    const [expected, setExpected] = useState("");
    const [actual, setActual] = useState("");
    const [reproSteps, setReproSteps] = useState("");
    const [frequency, setFrequency] = useState<FeedbackFrequency | "">("");
    const [submitting, setSubmitting] = useState(false);
    const [submitted, setSubmitted] = useState(false);
    // 2026-05-12: parse URL fallback；caller 給的 meetingId 優先
    const [resolvedMeetingId, setResolvedMeetingId] = useState<string | undefined>(meetingId);

    React.useEffect(() => {
        if (isOpen) {
            setStage(1);
            setIssueType(initialIssueType ?? "");
            setSummary(prefillSummary ?? "");
            setSeverity("");
            setExpected("");
            setActual("");
            setReproSteps("");
            setFrequency("");
            setSubmitting(false);
            setSubmitted(false);
            // caller 已帶 meetingId → 用 caller；否則嘗試從 URL parse
            setResolvedMeetingId(meetingId ?? parseMeetingIdFromUrl());
        }
    }, [isOpen, initialIssueType, prefillSummary, meetingId]);

    const stage1Valid =
        !!issueType && summary.trim().length >= 5 && summary.length <= 200 && !!severity;

    const handleSubmit = async (skipStage2 = false) => {
        if (!stage1Valid) {
            toast.error("請先填完第一階段必填欄位");
            return;
        }
        setSubmitting(true);
        try {
            const meta = collectFeedbackMetadata();
            const created = await api.createFeedback({
                user_upn: userUpn,
                issue_type: issueType as FeedbackIssueType,
                summary: summary.trim(),
                severity: severity as FeedbackSeverity,
                ...(skipStage2
                    ? {}
                    : {
                          expected: expected.trim() || undefined,
                          actual: actual.trim() || undefined,
                          repro_steps: reproSteps.trim() || undefined,
                          frequency: (frequency as FeedbackFrequency) || undefined,
                      }),
                meeting_id: resolvedMeetingId,
                page_url: meta.page_url,
                browser_info: meta.browser_info,
                session_id: meta.session_id,
                frontend_version: meta.frontend_version,
                console_errors: meta.console_errors,
            });
            setSubmitted(true);
            // 2026-05-12 UX：顯示 feedback ID 給使用者可追蹤；附「IT 24h 回覆」
            // 建立信任感（解 MECE 中 C 層：可追蹤性缺口）
            const shortId = created?.id ? created.id.slice(0, 8) : "";
            toast.success("已收到回報，謝謝！", {
                description: shortId
                    ? `回報編號 #${shortId}（IT 會在 24 小時內回覆）`
                    : "IT 會在 24 小時內回覆。",
                duration: 7000,
            });
            // 1.5 秒後自動關閉
            setTimeout(() => {
                onClose();
            }, 1500);
        } catch (err) {
            console.error("Feedback submit failed:", err);
            toast.error(
                err instanceof Error ? `送出失敗：${err.message}` : "送出失敗，請稍後再試"
            );
            setSubmitting(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
            onClick={onClose}
        >
            <div
                className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-card rounded-2xl shadow-2xl border border-border"
                onClick={(e) => e.stopPropagation()}
                role="dialog"
                aria-labelledby="feedback-title"
                aria-modal="true"
            >
                {/* Header */}
                <div className="sticky top-0 z-10 bg-card px-6 py-4 border-b border-border flex items-center justify-between">
                    <div>
                        <h2
                            id="feedback-title"
                            className="text-lg font-bold text-foreground flex items-center gap-2"
                        >
                            <MessageSquare size={18} className="text-brand-cta" />
                            回報問題
                            <span className="text-xs text-muted-foreground font-normal ml-2">
                                {stage === 1 ? "1/2 必填" : "2/2 補充細節（可選）"}
                            </span>
                        </h2>
                        <p className="text-xs text-muted-foreground mt-0.5">
                            幫我們找出哪裡不順手 — 30 秒就好
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-muted rounded-full text-muted-foreground transition-colors"
                        aria-label="關閉"
                    >
                        <X size={20} />
                    </button>
                </div>

                {submitted ? (
                    <div className="px-6 py-12 flex flex-col items-center text-center">
                        <CheckCircle2 size={48} className="text-status-success mb-4" />
                        <h3 className="text-lg font-bold text-foreground mb-1">
                            已收到您的回報
                        </h3>
                        <p className="text-sm text-muted-foreground">
                            我們會盡快檢視並改善。
                        </p>
                    </div>
                ) : stage === 1 ? (
                    <>
                        {/* 2026-05-12 UX：上下文 badge 雙態，使用者一眼知道
                              IT 拿到的回報有沒有綁會議。解 MECE B 層「使用者
                              感知度」缺口。
                          - 有 meetingId（caller 給 OR URL parse 補）：綠色 badge
                          - 未綁定：黃色 warning + 提示「點某個會議再回報能更快
                            定位」，避免使用者送出後才知道資訊不全 */}
                        <div className="px-6 pt-4">
                            {resolvedMeetingId ? (
                                <div className="bg-status-success/10 border border-status-success/30 rounded-lg px-3 py-2 text-xs text-status-success flex items-center gap-2">
                                    <Link2 size={14} className="shrink-0" />
                                    <span className="flex-1">
                                        本回報已綁定會議
                                        <code className="ml-1.5 px-1 py-0.5 bg-status-success/15 rounded font-mono text-[11px]">{resolvedMeetingId.slice(0, 8)}…</code>
                                        ，IT 可精準定位問題。
                                        {!meetingId && (
                                            <span className="ml-1 opacity-75">（依目前頁面自動帶入）</span>
                                        )}
                                    </span>
                                </div>
                            ) : (
                                <div className="bg-brand-orange/10 border border-brand-orange/30 rounded-lg px-3 py-2 text-xs text-brand-orange flex items-start gap-2">
                                    <Link2Off size={14} className="shrink-0 mt-0.5" />
                                    <span className="flex-1 leading-relaxed">
                                        <strong>本回報未綁定任何會議</strong>。
                                        若與某個會議有關，建議先進入該會議的詳情頁
                                        再點「回報這個會議」按鈕，IT 較好追查。
                                    </span>
                                </div>
                            )}
                        </div>
                    <div className="px-6 py-5 space-y-5">
                        {/* Issue type */}
                        <div>
                            <label className="block text-sm font-bold text-foreground mb-2">
                                問題類型 <span className="text-status-error">*</span>
                            </label>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                {ISSUE_TYPE_OPTIONS.map((opt) => (
                                    <button
                                        key={opt.value}
                                        type="button"
                                        onClick={() => setIssueType(opt.value)}
                                        className={`flex items-start gap-3 p-3 text-left rounded-xl border-2 transition-all ${
                                            issueType === opt.value
                                                ? "border-brand-cta bg-brand-cta/5 text-brand-cta"
                                                : "border-border hover:border-brand-cta/40 text-foreground"
                                        }`}
                                    >
                                        <span className="mt-0.5 flex-shrink-0">{opt.icon}</span>
                                        <span className="flex-1">
                                            <span className="block text-sm font-medium">
                                                {opt.label}
                                            </span>
                                            <span className="block text-xs text-muted-foreground mt-0.5">
                                                {opt.desc}
                                            </span>
                                        </span>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Summary */}
                        <div>
                            <label
                                htmlFor="feedback-summary"
                                className="block text-sm font-bold text-foreground mb-2"
                            >
                                一句話描述問題{" "}
                                <span className="text-status-error">*</span>
                                <span className="text-xs text-muted-foreground font-normal ml-2">
                                    {summary.length} / 200
                                </span>
                            </label>
                            <textarea
                                id="feedback-summary"
                                value={summary}
                                onChange={(e) => setSummary(e.target.value.slice(0, 200))}
                                placeholder="例：摘要把預算金額抓錯了，應該是 50 萬不是 5 萬"
                                rows={3}
                                className="w-full px-3 py-2 bg-surface border border-border rounded-lg focus:border-brand-cta focus:outline-none text-sm text-foreground resize-none"
                            />
                            {summary.length > 0 && summary.trim().length < 5 && (
                                <p className="text-xs text-status-error mt-1 flex items-center gap-1">
                                    <AlertCircle size={12} /> 至少 5 個字
                                </p>
                            )}
                        </div>

                        {/* Severity */}
                        <div>
                            <label className="block text-sm font-bold text-foreground mb-2">
                                嚴重程度 <span className="text-status-error">*</span>
                            </label>
                            <div className="grid grid-cols-3 gap-2">
                                {SEVERITY_OPTIONS.map((opt) => (
                                    <button
                                        key={opt.value}
                                        type="button"
                                        onClick={() => setSeverity(opt.value)}
                                        className={`p-3 text-center rounded-xl border-2 transition-all ${
                                            severity === opt.value
                                                ? `${opt.cls} ring-2 ring-current/20`
                                                : "border-border text-muted-foreground hover:border-current"
                                        }`}
                                    >
                                        <span className="block text-sm font-medium">
                                            {opt.label}
                                        </span>
                                        <span className="block text-[11px] mt-0.5 opacity-80">
                                            {opt.desc}
                                        </span>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Buttons — DDG §4.1: 表單 submit → brand-cta primary；
                            「補更多細節」為次要動作，使用 outline 樣式。
                            submit 放右側（慣例 primary 位置）。 */}
                        <div className="flex flex-col-reverse sm:flex-row gap-2 pt-2 border-t border-border">
                            <button
                                onClick={() => setStage(2)}
                                disabled={!stage1Valid || submitting}
                                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-card text-muted-foreground border border-border hover:border-brand-cta/40 hover:text-brand-cta rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                補更多細節
                                <ChevronRight size={14} />
                            </button>
                            <button
                                onClick={() => handleSubmit(true)}
                                disabled={!stage1Valid || submitting}
                                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-brand-cta text-white hover:bg-brand-cta/90 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {submitting ? (
                                    <Loader2 size={14} className="animate-spin" />
                                ) : (
                                    <Send size={14} />
                                )}
                                送出回報
                            </button>
                        </div>
                    </div>
                    </>
                ) : (
                    <div className="px-6 py-5 space-y-5">
                        <div className="bg-muted/30 rounded-lg p-3 text-xs text-muted-foreground">
                            <span className="font-semibold text-foreground">
                                {ISSUE_TYPE_OPTIONS.find((o) => o.value === issueType)?.label}
                            </span>
                            ：{summary}
                        </div>

                        {/* Expected vs Actual */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label
                                    htmlFor="feedback-expected"
                                    className="block text-sm font-bold text-foreground mb-2"
                                >
                                    您期待的結果
                                </label>
                                <textarea
                                    id="feedback-expected"
                                    value={expected}
                                    onChange={(e) => setExpected(e.target.value.slice(0, 2000))}
                                    placeholder="原本以為會看到 / 應該要..."
                                    rows={4}
                                    className="w-full px-3 py-2 bg-surface border border-border rounded-lg focus:border-brand-cta focus:outline-none text-sm text-foreground resize-none"
                                />
                            </div>
                            <div>
                                <label
                                    htmlFor="feedback-actual"
                                    className="block text-sm font-bold text-foreground mb-2"
                                >
                                    實際看到什麼
                                </label>
                                <textarea
                                    id="feedback-actual"
                                    value={actual}
                                    onChange={(e) => setActual(e.target.value.slice(0, 2000))}
                                    placeholder="結果是 / 系統卻..."
                                    rows={4}
                                    className="w-full px-3 py-2 bg-surface border border-border rounded-lg focus:border-brand-cta focus:outline-none text-sm text-foreground resize-none"
                                />
                            </div>
                        </div>

                        {/* Repro steps */}
                        <div>
                            <label
                                htmlFor="feedback-repro"
                                className="block text-sm font-bold text-foreground mb-2"
                            >
                                如何重現？
                            </label>
                            <textarea
                                id="feedback-repro"
                                value={reproSteps}
                                onChange={(e) => setReproSteps(e.target.value.slice(0, 5000))}
                                placeholder="1. 上傳音檔...\n2. 等摘要產生...\n3. 看 BANT 欄位..."
                                rows={4}
                                className="w-full px-3 py-2 bg-surface border border-border rounded-lg focus:border-brand-cta focus:outline-none text-sm text-foreground resize-none font-mono"
                            />
                        </div>

                        {/* Frequency */}
                        <div>
                            <label className="block text-sm font-bold text-foreground mb-2">
                                發生頻率
                            </label>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                                {FREQUENCY_OPTIONS.map((opt) => (
                                    <button
                                        key={opt.value}
                                        type="button"
                                        onClick={() =>
                                            setFrequency((cur) =>
                                                cur === opt.value ? "" : opt.value
                                            )
                                        }
                                        className={`p-2 text-center rounded-lg border text-xs transition-colors ${
                                            frequency === opt.value
                                                ? "border-brand-cta bg-brand-cta/10 text-brand-cta"
                                                : "border-border text-muted-foreground hover:border-brand-cta/40"
                                        }`}
                                    >
                                        {opt.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Buttons */}
                        <div className="flex flex-col sm:flex-row gap-2 pt-2 border-t border-border">
                            <button
                                onClick={() => setStage(1)}
                                disabled={submitting}
                                className="px-4 py-2.5 bg-card text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg text-sm transition-colors disabled:opacity-50"
                            >
                                返回
                            </button>
                            <button
                                onClick={() => handleSubmit(false)}
                                disabled={submitting}
                                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-brand-cta text-white hover:bg-brand-cta/90 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {submitting ? (
                                    <Loader2 size={14} className="animate-spin" />
                                ) : (
                                    <Send size={14} />
                                )}
                                送出回報
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
