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
     *
     * 2026-05-11：後端改 soft delete + audit log；傳 user.email 給 audit 用。
     */
    const deleteMeeting = useCallback(async (meetingId: string) => {
        try {
            await api.deleteMeeting(meetingId, session?.user?.email ?? undefined);
            await fetchMeetings();
            toast.success('會議已刪除', {
                description: '資料保留 30 天供 IT 還原，期間請與 IT 聯絡可恢復。',
                duration: 5000,
            });
            return true;
        } catch (err) {
            console.error('Failed to delete meeting:', err);
            const msg = err instanceof Error ? err.message : '刪除會議失敗';
            toast.error(`刪除失敗：${msg}`, {
                description: '請檢查網路或稍後再試；若持續失敗請使用「回報問題」並附 Meeting ID。',
                duration: 8000,
            });
            setError(msg);
            return false;
        }
    }, [fetchMeetings, session?.user?.email]);

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
