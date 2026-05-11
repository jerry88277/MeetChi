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

// Phase 8.1.3: Speaker Mapping
export interface SpeakerMapping {
    display_name: string;
    role: string;
    color: string;
}

export type SpeakerMappings = Record<string, SpeakerMapping>;

// PR23 (Sprint 2b) IA 重設計：對齊 PR21 backend summary 新欄位
export interface KeyQuote {
    speaker: string;
    text: string;
}

export interface Meeting {
    id: string;
    title: string;
    date: string;
    createdAt: string;
    duration: string;
    status: "completed" | "processing" | "failed" | "pending";
    summary: string;
    actionItems: ActionItem[];
    transcript: TranscriptLine[];
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
}
