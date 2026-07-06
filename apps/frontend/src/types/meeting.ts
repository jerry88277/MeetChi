// --- Meeting Types ---

export interface ActionItem {
    id: number;
    text: string;
    assignee: string;
    due: string;
}

export interface TranscriptLine {
    time: string;
    speaker: string;
    text: string;
}

// Feature #2 (2026-07-06): 逐段編輯模式用的「原始 segment」（未聚合，帶 id）
export interface RawSegment {
    id: string;
    order: number;
    time: string;       // 顯示用（mm:ss）
    startTime: number;  // 秒
    speaker: string;    // 原始說話者標籤（raw label）
    text: string;
}

// Phase 8.1.3: Speaker Mapping
export interface SpeakerMapping {
    display_name: string;
    role: string;
    color: string;
}

export type SpeakerMappings = Record<string, SpeakerMapping>;

// PR23 (Sprint 2b) IA 重設計：對齊 PR21 backend summary 新欄位
export interface KeyQuote {
    speaker: string;            // SPEAKER_xx；render 走 SpeakerName transform
    text: string;
    time?: number;              // V2 (2026-05-11)：秒數
}

// Summary V2 (Q1-Q8 落地，2026-05-11)
export interface SubChapter {
    timeStart: number;
    timeEnd: number;
    summary: string;
    bullets: string[];
    keyQuotes: KeyQuote[];
}

export interface Chapter {
    title: string;
    summary: string;
    bullets: string[];
    keyQuotes: KeyQuote[];
    subChapters: SubChapter[];
}

export interface SpeakerContribution {
    speaker: string;
    role?: string;
    speakTimePct: number;
    mainTopics: string[];
    keyContribution: string;
}

export interface NextStep {
    task: string;
    assignee?: string;
    due?: string;
    followUpMeeting?: string;
}

export interface CrossMeetingRef {
    topic: string;
    relatedMeetingId: string;
    relatedMeetingTitle: string;
    url: string;
    similarity: number;
}

export interface Meeting {
    id: string;
    title: string;
    date: string;
    createdAt: string;
    updatedAt?: string;  // 2026-05-22 (feedback #7)：用於顯示「轉錄完成時間」
    completedAt?: string | null;  // Processing completion timestamp (不受後續 edit 影響)
    duration: string;
    status: "completed" | "processing" | "failed" | "pending" | "transcribed";
    summary: string;
    actionItems: ActionItem[];
    transcript: TranscriptLine[];
    rawSegments?: RawSegment[];         // Feature #2: 逐段編輯模式用（未聚合）
    speakerMappings?: SpeakerMappings;  // Phase 8.1.3
    audio_url?: string | null;          // Phase D: Audio Playback Sync
    // PR23 — 卡片與詳情頁顆粒度由大→小所需的新欄位（皆 optional fallback）
    tldr?: string;                      // 100-200 字 TL;DR 結論先行
    decisions?: string[];               // 結論卡片：核心決策
    risks?: string[];                   // 結論卡片：風險
    keyQuotes?: KeyQuote[];             // 精選原音引言（含 speaker + 時間後綴）
    templateName?: string;              // 模板分類 (general/sales_bant/...)
    speakerCount?: number;              // 講者數（卡片顯示 dot 用）
    isConfidential?: boolean;           // Sprint 2e Phase 1：機密會議旗標
    failureReason?: string | null;      // 2026-05-25 (Y7)：FAILED 時的具體原因
    durationSeconds?: number | null;    // 原始音訊秒數（ETA 計算用）
    processingStage?: "queued" | "transcribing" | "diarizing" | "summarizing" | null;  // 2026-06-18
    // Summary V2 (2026-05-11)
    chapters?: Chapter[];
    speakerContributions?: SpeakerContribution[];
    nextSteps?: NextStep[];
    crossMeetingRefs?: CrossMeetingRef[];
    audioStats?: AudioStats | null;     // 2026-07-03：上傳音檔健康報告
}

// 2026-07-03：上傳音檔「原始狀態」健康報告（後端 app/audio_stats.py 產生）
export interface AudioStats {
    duration_sec?: number | null;
    channels?: number | null;
    sample_rate?: number | null;
    codec?: string | null;
    peak_dbfs?: number | null;
    mean_dbfs?: number | null;
    clip_ratio?: number | null;
    health?: "ok" | "silent" | "low_volume" | "clipping" | "unknown";
    health_label_zh?: string;
    warnings?: string[];
    analyzed_at?: string;
}
