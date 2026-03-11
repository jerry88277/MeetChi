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
}
