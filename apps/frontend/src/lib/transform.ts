import { Meeting as ApiMeeting, MeetingSummary, KeyQuote as ApiKeyQuote } from '@/lib/api';
import type { Meeting, ActionItem, TranscriptLine, SpeakerMappings, KeyQuote } from '@/types/meeting';

export function formatSeconds(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

/**
 * PR23 fallback：舊摘要沒 tldr 欄位時，從 summary 抓首句作 TL;DR。
 * 中英混合句末標點 (。！？.!?) 取首句並 cap 200 字。
 */
function extractFirstSentence(text: string, maxLen = 200): string {
    if (!text) return "";
    const trimmed = text.trim();
    const match = trimmed.match(/^[\s\S]+?[。！？.!?]/);
    const first = match ? match[0] : trimmed;
    return first.length > maxLen ? first.slice(0, maxLen).trim() + "…" : first.trim();
}

/** 用 transcript_segments 算 distinct speaker 數量 */
function countDistinctSpeakers(apiMeeting: ApiMeeting): number {
    const segments = apiMeeting.transcript_segments || [];
    const speakers = new Set<string>();
    for (const s of segments) {
        if (s.speaker && s.speaker.trim()) speakers.add(s.speaker);
    }
    return speakers.size;
}

// Transform API meeting to UI format
export function transformMeeting(apiMeeting: ApiMeeting): Meeting {
    // Parse summary JSON if available
    let summary = "";
    let actionItems: ActionItem[] = [];
    let tldr: string | undefined;
    let decisions: string[] = [];
    let risks: string[] = [];
    let keyQuotes: KeyQuote[] = [];

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
            // PR21 backend 新欄位
            tldr = summaryData.tldr || undefined;
            decisions = summaryData.decisions || [];
            risks = summaryData.risks || [];
            keyQuotes = (summaryData.key_quotes || []).map((q: ApiKeyQuote) => ({
                speaker: q.speaker,
                text: q.text,
            }));
        } catch {
            summary = apiMeeting.summary_json;
        }
    }

    // PR23 fallback：舊摘要沒 tldr → 取 summary 首句
    if (!tldr && summary) {
        tldr = extractFirstSentence(summary);
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
        speakerMappings,
        audio_url: apiMeeting.audio_url ?? null,
        // PR23 新欄位
        tldr,
        decisions,
        risks,
        keyQuotes,
        templateName: apiMeeting.template_name,
        speakerCount: countDistinctSpeakers(apiMeeting),
    };
}
