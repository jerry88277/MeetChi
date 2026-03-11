"use client";

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import type { Meeting } from '@/types/meeting';
import { transformMeeting } from '@/lib/transform';

export function useMeetings() {
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

    const deleteMeeting = useCallback(async (meetingId: string) => {
        if (!confirm('確定要刪除這個會議記錄嗎？此操作無法復原。')) return;
        try {
            await api.deleteMeeting(meetingId);
            await fetchMeetings();
            showSuccess('會議已成功刪除');
            return true;
        } catch (err) {
            console.error('Failed to delete meeting:', err);
            setError(err instanceof Error ? err.message : '刪除會議失敗');
            return false;
        }
    }, [fetchMeetings, showSuccess]);

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
