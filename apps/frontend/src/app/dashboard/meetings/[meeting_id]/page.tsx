"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Loader2, ChevronLeft, AlertCircle } from "lucide-react";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";
import { transformMeeting } from "@/lib/transform";
import type { Meeting } from "@/types/meeting";
import { DetailView } from "@/components/DetailView";
import { Sidebar } from "@/components/Sidebar";
import { FeedbackModal } from "@/components/FeedbackModal";

/**
 * V2 Q7 / SUMMARY_FINAL_SPEC §3.4 — Meeting 詳情可分享 URL.
 *
 * 使用者複製 `https://meetchi.../dashboard/meetings/{id}` 給 IT，
 * 或從 cross_meeting_refs 點過來，都能直接到對應會議。
 *
 * 行為：
 *   - SSR shell + CSR fetch（API 走 client 端 fetch 避免 SSR auth 複雜化）
 *   - Loading 顯示 spinner + Meeting ID（給 IT debug）
 *   - 404 顯示提示 + 返回 dashboard
 *   - 全域 Sidebar 保留導航一致性（與 dashboard/page.tsx 相同 layout）
 *   - DetailView 內「回報這個會議」按鈕自動帶 meeting_id 開 FeedbackModal
 *
 * 取代了原本的 mock stub 頁面。
 */
export default function MeetingDeepLinkPage() {
    const params = useParams<{ meeting_id: string }>();
    const router = useRouter();
    const { data: session } = useSession();

    const meetingId = params?.meeting_id;
    const [meeting, setMeeting] = useState<Meeting | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [feedbackContext, setFeedbackContext] = useState<{ meetingId?: string } | null>(null);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    useEffect(() => {
        if (!meetingId) return;
        let cancelled = false;
        setLoading(true);
        setError(null);

        api.getMeeting(meetingId)
            .then((apiMeeting) => {
                if (cancelled) return;
                setMeeting(transformMeeting(apiMeeting));
            })
            .catch((err) => {
                if (cancelled) return;
                console.error("Failed to fetch meeting:", err);
                setError(err instanceof Error ? err.message : "無法載入會議");
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });

        return () => {
            cancelled = true;
        };
    }, [meetingId]);

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
                        onReportThisMeeting={(mid) => setFeedbackContext({ meetingId: mid })}
                        // deep-link 頁暫不暴露 regenerate/delete（避免誤觸；
                        // 主要 dashboard 流程才提供完整操作）
                    />
                )}
            </main>

            <FeedbackModal
                isOpen={feedbackContext !== null}
                onClose={() => setFeedbackContext(null)}
                userUpn={session?.user?.email || "anonymous@meetchi.test"}
                meetingId={feedbackContext?.meetingId}
            />
        </div>
    );
}
