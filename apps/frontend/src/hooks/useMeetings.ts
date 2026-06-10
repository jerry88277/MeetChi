"use client";

import { useState, useEffect, useCallback, useRef } from 'react';
import { useSession } from 'next-auth/react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import type { Meeting } from '@/types/meeting';
import { transformMeeting } from '@/lib/transform';

export function useMeetings() {
    const { data: session } = useSession();
    const [meetings, setMeetings] = useState<Meeting[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    const userEmail = session?.user?.email;

    const fetchMeetings = useCallback(async () => {
        setIsLoading(true);
        setError(null);

        try {
            await api.checkHealth();
            setIsConnected(true);

            const apiMeetings = await api.listMeetings(0, 100, userEmail || undefined);
            const transformedMeetings = apiMeetings.map(transformMeeting)
                .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
            setMeetings(transformedMeetings);
        } catch (err) {
            setIsConnected(false);
            setError(err instanceof Error ? err.message : '發生未知錯誤');
            setMeetings([]);
        } finally {
            setIsLoading(false);
        }
    }, [userEmail]);

    useEffect(() => {
        fetchMeetings();
    }, [fetchMeetings]);

    const showSuccess = useCallback((msg: string) => {
        setSuccessMessage(msg);
        setTimeout(() => setSuccessMessage(null), 5000);
    }, []);

    /**
     * 真正執行刪除（不再內含 confirm()）。
     * Caller 須先用 <ConfirmDialog> 取得使用者確認，再呼叫此函式。
     *
     * 2026-05-11：後端改 soft delete + audit log；傳 user.email 給 audit 用。
     *
     * 2026-05-12 UX 優化（方案 A）：
     *   原本 `await api.deleteMeeting + await fetchMeetings` 共 ~2-3s，使用者
     *   會看到頁面僵著沒反應。改成只 await API（~0.5-1s），成功後本地
     *   `setMeetings(prev => prev.filter(...))` 直接拿掉那筆，不重抓整份列表。
     *   省下 fetchMeetings 的 1-2s round trip，且不影響其他 meeting 排序。
     */
    /**
     * 2026-05-12 UX (feedback 617bb614)：
     *   原刪除失敗 toast 只顯示 raw error string（例：「(psycopg2.errors.
     *   ForeignKeyViolation) ...」），使用者直接看到 stack trace 風格訊息，
     *   無法理解、也不知道下一步。
     *
     *   改成：user-friendly 標題 + 引導句 + 「立即回報」action 按鈕。
     *   action 透過 onReportFailedDelete callback 開 FeedbackModal 並帶
     *   meeting_id（caller 在 page 層接 callback）。
     */
    const deleteMeeting = useCallback(async (
        meetingId: string,
        onReportFailedDelete?: (meetingId: string) => void
    ) => {
        try {
            await api.deleteMeeting(meetingId, session?.user?.email ?? undefined);
            // 本地 splice（避免重抓整份 list 多 1-2s 延遲）
            setMeetings(prev => prev.filter(m => m.id !== meetingId));
            toast.success('會議已刪除', {
                description: '資料保留 30 天供 IT 還原，期間請與 IT 聯絡可恢復。',
                duration: 5000,
            });
            return true;
        } catch (err) {
            console.error('Failed to delete meeting:', err);
            const msg = err instanceof Error ? err.message : '刪除會議失敗';
            toast.error('刪除失敗，請稍候再試', {
                description:
                    '若持續失敗，請點下方「立即回報」交給 IT 協助處理（系統會自動附上 Meeting ID）。',
                duration: 10000,
                action: onReportFailedDelete
                    ? {
                          label: '立即回報',
                          onClick: () => onReportFailedDelete(meetingId),
                      }
                    : undefined,
            });
            setError(msg);
            return false;
        }
    }, [session?.user?.email]);

    return {
        meetings,
        isLoading,
        error,
        setError,
        isConnected,
        successMessage,
        fetchMeetings,
        showSuccess,
        deleteMeeting,
    };
}
