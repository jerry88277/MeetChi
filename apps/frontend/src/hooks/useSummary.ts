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
        templateName = 'general',
    ) => {
        setIsRegenerating(true);
        try {
            await api.regenerateSummary(meetingId, templateName);
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

    const regenerateTranscript = useCallback(async (
        meetingId: string,
        selectedMeeting: Meeting | null,
        setSelectedMeeting: (m: Meeting) => void,
        templateName = 'general',
    ) => {
        setIsRegenerating(true);
        try {
            await api.startTranscriptionTask(meetingId, templateName);
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
        regenerateTranscript,
    };
}
