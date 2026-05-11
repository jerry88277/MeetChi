"use client";

import { useState, useEffect, useCallback, useRef } from 'react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import type { Meeting } from '@/types/meeting';
import { transformMeeting } from '@/lib/transform';

export function useMeetings() {
    const [meetings, setMeetings] = useState<Meeting[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    /** 2026-05-11 修：原本 dashboard/page.tsx 把 isDeleting hardcoded false，
     *  按下刪除中按鈕不會 disable + 沒 spinner；改由 hook 統一管理。 */
    const [isDeleting, setIsDeleting] = useState(false);

    const fetchMeetings = useCallback(async () => {
        setIsLoading(true);
        setError(null);

        try {
            await api.checkHealth();
            setIsConnected(true);

            const apiMeetings = await api.listMeetings();
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
    }, []);

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
     */
    const deleteMeeting = useCallback(async (meetingId: string) => {
        setIsDeleting(true);
        try {
            await api.deleteMeeting(meetingId);
            await fetchMeetings();
            toast.success('會議已成功刪除');
            return true;
        } catch (err) {
            // 2026-05-11 修：原本只 setError 但 detail 頁不顯示這個 error
            // → 使用者按刪除「毫無反應」。改用 toast.error 確保跨頁都看得到
            const msg = err instanceof Error ? err.message : '刪除會議失敗';
            console.error('Failed to delete meeting:', err);
            toast.error(`刪除失敗：${msg}`, {
                description: '請檢查網路或稍後再試；若持續失敗請使用「回報問題」。',
                duration: 8000,
            });
            setError(msg);
            return false;
        } finally {
            setIsDeleting(false);
        }
    }, [fetchMeetings]);

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
        isDeleting,
    };
}
