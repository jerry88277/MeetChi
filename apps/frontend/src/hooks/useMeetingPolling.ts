"use client";

import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '@/lib/api';
import type { Meeting as ApiMeeting } from '@/lib/api';

/**
 * Phase 9.1: Event-Triggered Polling Hook (v14 — stable refs)
 * 
 * Polls a single meeting's status with exponential backoff.
 * Auto-stops when status is no longer 'processing' or 'pending'.
 * Pauses when page is hidden (Page Visibility API).
 * 
 * v14 fix: Uses refs for poll/enabled/meetingId to prevent React
 * re-render from destroying setTimeout chains via useCallback rebuild.
 * 
 * @param meetingId - Meeting ID to poll (null = disabled)
 * @param enabled - Whether polling is active
 * @param onStatusChange - Callback when meeting status changes from processing/pending
 */
export function useMeetingPolling(
    meetingId: string | null,
    enabled: boolean,
    onStatusChange?: (meeting: ApiMeeting) => void,
) {
    const [isPolling, setIsPolling] = useState(false);
    const intervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const attemptRef = useRef(0);
    const isPageVisibleRef = useRef(true);

    // Stable refs — prevent re-render from rebuilding poll/useEffect
    const onStatusChangeRef = useRef(onStatusChange);
    const meetingIdRef = useRef(meetingId);
    const enabledRef = useRef(enabled);

    useEffect(() => { onStatusChangeRef.current = onStatusChange; }, [onStatusChange]);
    useEffect(() => { meetingIdRef.current = meetingId; }, [meetingId]);
    useEffect(() => { enabledRef.current = enabled; }, [enabled]);

    // Calculate delay with exponential backoff: 5s → 10s → 15s → 20s → 25s → cap at 30s
    const getDelay = useCallback((attempt: number): number => {
        const delays = [5000, 10000, 15000, 20000, 25000, 30000];
        return delays[Math.min(attempt, delays.length - 1)];
    }, []);

    const stopPolling = useCallback(() => {
        if (intervalRef.current) {
            clearTimeout(intervalRef.current);
            intervalRef.current = null;
        }
        attemptRef.current = 0;
        setIsPolling(false);
    }, []);

    // poll is stable — reads from refs, no dependency on meetingId/enabled
    const poll = useCallback(async () => {
        const id = meetingIdRef.current;
        if (!id || !isPageVisibleRef.current || !enabledRef.current) return;

        try {
            const meeting = await api.getMeeting(id);
            const currentStatus = meeting.status?.toLowerCase();

            // Check if status has changed to a terminal state
            const isTerminal = currentStatus !== 'processing' && currentStatus !== 'pending';

            if (isTerminal) {
                // Status changed from processing → completed/failed
                onStatusChangeRef.current?.(meeting);
                stopPolling();
                return;
            }

            // Still processing — schedule next poll with backoff
            attemptRef.current += 1;
            const delay = getDelay(attemptRef.current);
            intervalRef.current = setTimeout(poll, delay);
        } catch (error) {
            console.error('[Polling] Error fetching meeting:', error);
            // On error, retry with backoff (don't stop)
            attemptRef.current += 1;
            const delay = getDelay(attemptRef.current);
            intervalRef.current = setTimeout(poll, delay);
        }
    }, [getDelay, stopPolling]); // Stable deps only — no meetingId/enabled

    // Start/Stop polling — only reacts to meetingId + enabled changes
    useEffect(() => {
        if (!meetingId || !enabled) {
            stopPolling();
            return;
        }

        setIsPolling(true);
        attemptRef.current = 0;

        // Initial poll after 5s delay (give backend time to start processing)
        intervalRef.current = setTimeout(poll, 5000);

        return () => {
            stopPolling();
        };
        // poll is now stable (no meetingId/enabled in its deps), so this
        // useEffect only re-runs when meetingId or enabled actually change.
    }, [meetingId, enabled, poll, stopPolling]);

    // Page Visibility API — pause when tab is hidden, resume when visible
    useEffect(() => {
        const handleVisibilityChange = () => {
            isPageVisibleRef.current = !document.hidden;

            if (!document.hidden && meetingIdRef.current && enabledRef.current) {
                // Tab became visible — do an immediate fetch then resume polling
                attemptRef.current = 0; // Reset backoff on visibility change
                if (intervalRef.current) {
                    clearTimeout(intervalRef.current);
                }
                intervalRef.current = setTimeout(poll, 500); // Near-immediate fetch
            } else if (document.hidden) {
                // Tab hidden — stop scheduled polls
                if (intervalRef.current) {
                    clearTimeout(intervalRef.current);
                    intervalRef.current = null;
                }
            }
        };

        document.addEventListener('visibilitychange', handleVisibilityChange);
        return () => {
            document.removeEventListener('visibilitychange', handleVisibilityChange);
        };
    }, [poll]); // poll is stable, so this effect is stable

    return { isPolling, stopPolling };
}
