"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Loader2, ChevronLeft, AlertCircle } from "lucide-react";
import { useSession } from "next-auth/react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { transformMeeting } from "@/lib/transform";
import type { Meeting } from "@/types/meeting";
import type { Meeting as ApiMeeting } from "@/lib/api";
import { DetailView } from "@/components/DetailView";
import { Sidebar } from "@/components/Sidebar";
import { FeedbackModal } from "@/components/FeedbackModal";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useMeetings } from "@/hooks/useMeetings";
import { useSummary } from "@/hooks/useSummary";
import { useMeetingPolling } from "@/hooks/useMeetingPolling";

/**
 * V2 Q7 / SUMMARY_FINAL_SPEC §3.4 — Meeting 詳情可分享 URL.
 *
 * 使用者複製 `https://meetchi.../dashboard/meetings/{id}` 給 IT，
 * 或從 cross_meeting_refs 點過來，都能直接到對應會議。
 *
 * 2026-07-08（方案 2）：本頁成為會議詳情的「單一真相來源」。
 *   Dashboard 列表點擊改用 router.push 進入本路由（不再走 SPA 內嵌 DetailView），
 *   因此本頁必須提供與 dashboard 相同的完整操作，避免「列表進入 vs 重新整理」
 *   畫面不一致（缺少 重新生成/刪除/更名，且 processing 不會自動更新）。
 *
 * 行為：
 *   - SSR shell + CSR fetch（API 走 client 端 fetch 避免 SSR auth 複雜化）
 *   - Loading 顯示 spinner + Meeting ID（給 IT debug）
 *   - 404 顯示提示 + 返回 dashboard
 *   - 全域 Sidebar 保留導航一致性（與 dashboard/page.tsx 相同 layout）
 *   - 完整操作：重新生成摘要 / 重新生成逐字稿 / 刪除 / 更名 / 回報
 *   - processing / pending 會議自動輪詢，完成後即時更新畫面
 */
export default function MeetingDeepLinkPage() {
    const params = useParams<{ meeting_id: string }>();
    const router = useRouter();
    const { data: session } = useSession();
    const userUpn = session?.user?.email || undefined;

    const meetingId = params?.meeting_id;
    const [meeting, setMeeting] = useState<Meeting | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [feedbackContext, setFeedbackContext] = useState<{ meetingId?: string } | null>(null);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    const [pendingDelete, setPendingDelete] = useState<{ meetingId: string } | null>(null);

    // deleteMeeting + fetchMeetings 由 useMeetings 提供（與 dashboard 同一實作）。
    const { deleteMeeting, fetchMeetings } = useMeetings();
    // 重新生成摘要 / 逐字稿（與 dashboard 同一 hook，行為一致）。
    const { isRegenerating, regenerateSummary, regenerateTranscript } = useSummary(
        fetchMeetings,
        userUpn,
    );

    useEffect(() => {
        if (!meetingId) return;
        let cancelled = false;

        const load = async () => {
            setLoading(true);
            setError(null);
            try {
                const apiMeeting = await api.getMeeting(meetingId);
                if (!cancelled) setMeeting(transformMeeting(apiMeeting));
            } catch (err) {
                if (cancelled) return;
                console.error("Failed to fetch meeting:", err);
                setError(err instanceof Error ? err.message : "無法載入會議");
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        load();

        return () => {
            cancelled = true;
        };
    }, [meetingId]);

    // processing / pending 會議自動輪詢，完成後以完整版（含逐字稿）覆蓋畫面。
    const isProcessing = meeting?.status === "processing" || meeting?.status === "pending";
    const handlePollingStatusChange = useCallback((apiMeeting: ApiMeeting) => {
        setMeeting(transformMeeting(apiMeeting));
    }, []);
    useMeetingPolling(
        isProcessing ? (meetingId ?? null) : null,
        !!isProcessing,
        handlePollingStatusChange,
    );

    const handleRegenerateSummary = useCallback(
        async (id: string, templateName?: string) => {
            try {
                await regenerateSummary(id, meeting, setMeeting, templateName);
            } catch (err) {
                console.error("Failed to regenerate summary:", err);
                toast.error(err instanceof Error ? err.message : "重新生成摘要失敗");
            }
        },
        [regenerateSummary, meeting],
    );

    const handleRegenerateTranscript = useCallback(
        async (id: string, templateName?: string) => {
            try {
                await regenerateTranscript(id, meeting, setMeeting, templateName);
            } catch (err) {
                console.error("Failed to regenerate transcript:", err);
                toast.error(err instanceof Error ? err.message : "重新整理與轉錄失敗");
            }
        },
        [regenerateTranscript, meeting],
    );

    const handleRename = useCallback(
        async (id: string, newTitle: string) => {
            try {
                await api.renameMeeting(id, newTitle);
                setMeeting((prev) => (prev && prev.id === id ? { ...prev, title: newTitle } : prev));
                toast.success(`已更名為「${newTitle}」`);
            } catch (err) {
                console.error("Rename failed:", err);
                toast.error("修改名稱失敗");
            }
        },
        [],
    );

    // 刪除：開確認框 → 確認後刪除 → 返回 dashboard（與 dashboard 感知一致）。
    const handleDelete = useCallback((id: string) => {
        setPendingDelete({ meetingId: id });
    }, []);

    const executeDelete = useCallback(
        async (id: string) => {
            const success = await deleteMeeting(id, (failedMeetingId) => {
                setFeedbackContext({ meetingId: failedMeetingId });
            });
            if (success) {
                router.push("/dashboard");
            }
        },
        [deleteMeeting, router],
    );

    return (
        <div className="flex h-screen bg-surface font-sans text-foreground overflow-hidden relative">
            <Sidebar
                activeTab="dashboard"
                setActiveTab={() => router.push("/dashboard")}
                isMobileOpen={isMobileMenuOpen}
                setIsMobileOpen={setIsMobileMenuOpen}
                isConnected={true}
                user={session?.user ?? undefined}
                onOpenFeedback={() => setFeedbackContext({})}
            />

            <main className="flex-1 flex flex-col relative overflow-hidden">
                {loading && (
                    <div className="flex-1 flex items-center justify-center bg-surface">
                        <div className="text-center">
                            <Loader2 size={48} className="text-brand-cta animate-spin mx-auto mb-3" />
                            <p className="text-sm text-muted-foreground">載入會議中...</p>
                            <p className="text-xs text-muted-foreground/70 mt-1 font-mono">
                                Meeting ID: {meetingId}
                            </p>
                        </div>
                    </div>
                )}

                {!loading && error && (
                    <div className="flex-1 flex items-center justify-center bg-surface p-6">
                        <div className="max-w-md w-full text-center">
                            <div className="w-12 h-12 bg-status-error/10 rounded-full flex items-center justify-center mx-auto mb-4">
                                <AlertCircle className="w-6 h-6 text-status-error" />
                            </div>
                            <h2 className="text-lg font-bold text-foreground mb-1">無法載入會議</h2>
                            <p className="text-sm text-muted-foreground mb-1">{error}</p>
                            <p className="text-xs text-muted-foreground/70 font-mono mb-6">
                                Meeting ID: {meetingId}
                            </p>
                            <Link
                                href="/dashboard"
                                className="inline-flex items-center gap-2 px-4 py-2 bg-brand-cta text-white rounded-lg hover:bg-brand-cta/90 transition-colors text-sm font-medium"
                            >
                                <ChevronLeft size={14} /> 返回 Dashboard
                            </Link>
                        </div>
                    </div>
                )}

                {!loading && !error && meeting && (
                    <DetailView
                        meeting={meeting}
                        onBack={() => router.push("/dashboard")}
                        onRegenerateSummary={handleRegenerateSummary}
                        onRegenerateTranscript={handleRegenerateTranscript}
                        isRegenerating={isRegenerating}
                        onDelete={handleDelete}
                        isDeleting={false}
                        onRename={handleRename}
                        onReportThisMeeting={(mid) => setFeedbackContext({ meetingId: mid })}
                    />
                )}
            </main>

            <ConfirmDialog
                open={!!pendingDelete}
                title="確定要刪除這個會議記錄嗎？"
                description="此操作將移除音檔、逐字稿與摘要。資料保留 30 天供 IT 還原，期間可與 IT 聯絡恢復。"
                confirmText="刪除"
                cancelText="取消"
                variant="destructive"
                onConfirm={async () => {
                    if (pendingDelete) {
                        const id = pendingDelete.meetingId;
                        setPendingDelete(null);
                        await executeDelete(id);
                    }
                }}
                onCancel={() => setPendingDelete(null)}
            />

            <FeedbackModal
                isOpen={feedbackContext !== null}
                onClose={() => setFeedbackContext(null)}
                userUpn={session?.user?.email || "anonymous@meetchi.test"}
                meetingId={feedbackContext?.meetingId}
            />
        </div>
    );
}
