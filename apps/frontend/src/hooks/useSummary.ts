"use client";

import { useState, useCallback } from 'react';
import { api } from '@/lib/api';
import type { Meeting } from '@/types/meeting';
import { transformMeeting } from '@/lib/transform';

export function useSummary(
    fetchMeetings: () => Promise<void>,
) {
    const [isRegenerating, setIsRegenerating] = useState(false);

    const regenerateSummary = useCallback(async (
        meetingId: string,
        selectedMeeting: Meeting | null,
        setSelectedMeeting: (m: Meeting) => void,
    ) => {
        setIsRegenerating(true);
        try {
            await api.regenerateSummary(meetingId, 'general');
            await fetchMeetings();

            if (selectedMeeting && selectedMeeting.id === meetingId) {
                const apiMeetings = await api.listMeetings();
                const updatedMeeting = apiMeetings.find(m => m.id === meetingId);
                if (updatedMeeting) {
                    setSelectedMeeting(transformMeeting(updatedMeeting));
                }
            }
        } finally {
            setIsRegenerating(false);
        }
    }, [fetchMeetings]);

    return {
        isRegenerating,
        regenerateSummary,
    };
}
