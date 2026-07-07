import { Meeting as ApiMeeting, MeetingSummary, KeyQuote as ApiKeyQuote } from '@/lib/api';
import type { Meeting, ActionItem, TranscriptLine, RawSegment, SpeakerMappings, KeyQuote } from '@/types/meeting';

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
    // Summary V2 (2026-05-11)
    let chapters: import('@/types/meeting').Chapter[] = [];
    let speakerContributions: import('@/types/meeting').SpeakerContribution[] = [];
    let nextSteps: import('@/types/meeting').NextStep[] = [];
    let crossMeetingRefs: import('@/types/meeting').CrossMeetingRef[] = [];
    // 2026-07-07 策略(a)：模板專屬區塊（非 V2 通用欄位）
    let extraSections: Record<string, unknown> = {};

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
                time: typeof q.time === 'number' ? q.time : undefined,
            }));

            // V2: chapters → camelCase 映射
            chapters = (summaryData.chapters || []).map((c) => ({
                title: c.title,
                summary: c.summary,
                bullets: c.bullets || [],
                keyQuotes: (c.key_quotes || []).map((q) => ({
                    speaker: q.speaker, text: q.text,
                    time: typeof q.time === 'number' ? q.time : undefined,
                })),
                subChapters: (c.sub_chapters || []).map((sc) => ({
                    timeStart: sc.time_start,
                    timeEnd: sc.time_end,
                    summary: sc.summary,
                    bullets: sc.bullets || [],
                    keyQuotes: (sc.key_quotes || []).map((q) => ({
                        speaker: q.speaker, text: q.text,
                        time: typeof q.time === 'number' ? q.time : undefined,
                    })),
                })),
            }));

            speakerContributions = (summaryData.speaker_contributions || []).map((s) => ({
                speaker: s.speaker,
                role: s.role,
                speakTimePct: s.speak_time_pct,
                mainTopics: s.main_topics || [],
                keyContribution: s.key_contribution,
            }));

            // next_steps 在 sales_bant 模板可能是 List[str]（向後相容）
            const rawNextSteps = summaryData.next_steps_v2 || summaryData.next_steps;
            if (Array.isArray(rawNextSteps)) {
                nextSteps = rawNextSteps.map((item) => {
                    if (typeof item === 'string') {
                        return { task: item };
                    }
                    return {
                        task: item.task,
                        assignee: item.assignee,
                        due: item.due,
                        followUpMeeting: item.follow_up_meeting,
                    };
                });
            }

            crossMeetingRefs = (summaryData.cross_meeting_refs || []).map((r) => ({
                topic: r.topic,
                relatedMeetingId: r.related_meeting_id,
                relatedMeetingTitle: r.related_meeting_title,
                url: r.url,
                similarity: r.similarity,
            }));

            // 2026-07-07 策略(a)：擷取模板專屬區塊。
            // V2 通用欄位由上方明確處理；其餘 output_key（模板自訂）收進 extraSections，
            // 供 DetailView 依模板定義動態渲染。空值/空陣列略過避免渲染空區塊。
            const UNIVERSAL_KEYS = new Set([
                'summary', 'action_items', 'tldr', 'decisions', 'risks', 'key_quotes',
                'chapters', 'speaker_contributions', 'next_steps', 'next_steps_v2',
                'cross_meeting_refs', 'speaker_roles',
            ]);
            for (const [k, v] of Object.entries(summaryData)) {
                if (UNIVERSAL_KEYS.has(k)) continue;
                if (v === null || v === undefined || v === '') continue;
                if (Array.isArray(v) && v.length === 0) continue;
                if (typeof v === 'object' && !Array.isArray(v) && Object.keys(v as object).length === 0) continue;
                extraSections[k] = v;
            }
        } catch {
            summary = apiMeeting.summary_json;
        }
    }

    // PR23 fallback：舊摘要沒 tldr → 取 summary 首句
    if (!tldr && summary) {
        tldr = extractFirstSentence(summary);
    }

    // Transform transcript segments — aggregate consecutive same-speaker segments
    // into paragraphs (target 150-250 chars) for better readability.
    // Each paragraph retains the start_time of the first segment.
    const rawSegments = (apiMeeting.transcript_segments || []);
    const transcript: TranscriptLine[] = [];
    // Feature #2: 逐段編輯模式用的未聚合 segment（帶 id）
    const editableSegments: RawSegment[] = rawSegments.map((seg, idx) => ({
        id: seg.id,
        order: typeof seg.order === "number" ? seg.order : idx,
        time: formatSeconds(seg.start_time),
        startTime: seg.start_time,
        speaker: seg.speaker || "Unknown",
        text: seg.content_polished || seg.content_raw || "",
    }));
    const PARA_MIN_CHARS = 100;
    const PARA_MAX_CHARS = 300;

    let paraText = "";
    let paraStartTime = 0;
    let paraSpeaker = "";

    for (let i = 0; i < rawSegments.length; i++) {
        const seg = rawSegments[i];
        const segText = seg.content_polished || seg.content_raw || "";
        const segSpeaker = seg.speaker || "Unknown";

        if (paraText === "") {
            // Start a new paragraph
            paraText = segText;
            paraStartTime = seg.start_time;
            paraSpeaker = segSpeaker;
        } else if (segSpeaker === paraSpeaker && paraText.length + segText.length <= PARA_MAX_CHARS) {
            // Same speaker and within char limit — append
            paraText += segText;
        } else {
            // Flush current paragraph
            transcript.push({
                time: formatSeconds(paraStartTime),
                speaker: paraSpeaker,
                text: paraText
            });
            // Start new paragraph with current segment
            paraText = segText;
            paraStartTime = seg.start_time;
            paraSpeaker = segSpeaker;
        }

        // Force flush if paragraph exceeds min and next segment is different speaker
        const nextSeg = rawSegments[i + 1];
        if (paraText.length >= PARA_MIN_CHARS && nextSeg && (nextSeg.speaker || "Unknown") !== paraSpeaker) {
            transcript.push({
                time: formatSeconds(paraStartTime),
                speaker: paraSpeaker,
                text: paraText
            });
            paraText = "";
        }
    }
    // Flush final paragraph
    if (paraText) {
        transcript.push({
            time: formatSeconds(paraStartTime),
            speaker: paraSpeaker,
            text: paraText
        });
    }

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
        date: new Date(apiMeeting.created_at).toLocaleDateString('sv-SE', { timeZone: 'Asia/Taipei' }),
        createdAt: apiMeeting.created_at,
        updatedAt: apiMeeting.updated_at,  // 2026-05-22 feedback #7
        completedAt: apiMeeting.completed_at ?? null,
        duration: durationStr,
        status: apiMeeting.status?.toLowerCase() === "completed" ? "completed"
            : apiMeeting.status?.toLowerCase() === "failed" ? "failed"
                : apiMeeting.status?.toLowerCase() === "pending" ? "pending"
                    : apiMeeting.status?.toLowerCase() === "transcribed" ? "transcribed"
                        : "processing",
        summary,
        actionItems,
        transcript,
        rawSegments: editableSegments,
        speakerMappings,
        audio_url: apiMeeting.audio_url ?? null,
        // PR23 新欄位
        tldr,
        decisions,
        risks,
        keyQuotes,
        templateName: apiMeeting.template_name,
        speakerCount: countDistinctSpeakers(apiMeeting),
        isConfidential: apiMeeting.is_confidential ?? false,
        failureReason: apiMeeting.failure_reason ?? null,
        durationSeconds: apiMeeting.duration ?? null,
        processingStage: apiMeeting.processing_stage ?? null,
        // 2026-07-03：上傳音檔健康報告（後端存 JSON 字串，前端解析為物件）
        audioStats: (() => {
            if (!apiMeeting.audio_stats) return null;
            try {
                return JSON.parse(apiMeeting.audio_stats);
            } catch {
                return null;
            }
        })(),
        // Summary V2
        chapters,
        speakerContributions,
        nextSteps,
        crossMeetingRefs,
        extraSections,
    };
}
