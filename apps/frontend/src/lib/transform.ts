import { Meeting as ApiMeeting, MeetingSummary } from '@/lib/api';
import type { Meeting, ActionItem, TranscriptLine, SpeakerMappings } from '@/types/meeting';

export function formatSeconds(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Transform API meeting to UI format
export function transformMeeting(apiMeeting: ApiMeeting): Meeting {
    // Parse summary JSON if available
    let summary = "";
    let actionItems: ActionItem[] = [];

    if (apiMeeting.summary_json) {
        try {
            const summaryData: MeetingSummary = JSON.parse(apiMeeting.summary_json);
            summary = summaryData.summary || "";
            actionItems = (summaryData.action_items || []).map((text, idx) => ({
                id: idx + 1,
                text,
                assignee: "待分配",
                due: "待定"
            }));
        } catch {
            summary = apiMeeting.summary_json;
        }
    }

    // Transform transcript segments
    const transcript: TranscriptLine[] = (apiMeeting.transcript_segments || []).map(seg => ({
        time: formatSeconds(seg.start_time),
        speaker: seg.speaker || "Unknown",
        text: seg.content_polished || seg.content_raw
    }));

    // Parse speaker mappings (Phase 8.1.3)
    let speakerMappings: SpeakerMappings | undefined;
    if (apiMeeting.speaker_mappings) {
        try {
            speakerMappings = JSON.parse(apiMeeting.speaker_mappings);
        } catch {
            speakerMappings = undefined;
        }
    }

    // Format duration
    const durationStr = apiMeeting.duration
        ? formatSeconds(apiMeeting.duration)
        : "00:00";

    return {
        id: apiMeeting.id,
        title: apiMeeting.title,
        date: new Date(apiMeeting.created_at).toISOString().split('T')[0],
        createdAt: apiMeeting.created_at,
        duration: durationStr,
        status: apiMeeting.status?.toLowerCase() === "completed" ? "completed"
            : apiMeeting.status?.toLowerCase() === "failed" ? "failed"
                : apiMeeting.status?.toLowerCase() === "pending" ? "pending"
                    : "processing",
        summary,
        actionItems,
        transcript,
        speakerMappings
    };
}
