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
    audio_url?: string | null;       // Phase D: Audio Playback Sync
}
