/**
 * MeetChi API Client
 * Handles all API requests to the backend service
 */

// API Base URL - set via environment variable or default to localhost
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// ==========================================
// Types
// ==========================================

export interface TranscriptSegment {
    id: string;
    order: number;
    start_time: number;
    end_time: number;
    speaker: string | null;
    content_raw: string;
    content_polished: string | null;
    content_translated: string | null;
    is_final: boolean;
}

export interface Meeting {
    id: string;
    title: string;
    status: "recording" | "processing" | "completed" | "failed" | "pending";
    created_at: string;
    updated_at: string;
    duration: number | null;
    audio_url: string | null;
    language: string;
    template_name: string;
    transcript_raw: string | null;
    transcript_polished: string | null;
    summary_json: string | null;
    speaker_mappings: string | null;  // Phase 8.1.3
    transcript_segments: TranscriptSegment[];
    is_confidential?: boolean;  // Sprint 2e Phase 1 (2026-05-11)
    failure_reason?: string | null;  // 2026-05-25 Y7
}

// Sprint 2c (PR21) extended: backend summary_json 加新欄位後，frontend 對齊。
// 舊摘要缺欄位也不會爆 — 全 optional。
export interface KeyQuote {
    speaker: string;            // SPEAKER_xx；render 時走 SpeakerName 元件 transform 為 display_name (Q4)
    text: string;
    time?: number;              // V2 (2026-05-11)：秒數，點時戳跳音檔
}

// Summary V2 schema (SUMMARY_FINAL_SPEC.md / Q1-Q8, 2026-05-11)
export interface SubChapter {
    time_start: number;         // 秒
    time_end: number;           // 秒
    summary: string;            // 30-50 字
    bullets: string[];
    key_quotes: KeyQuote[];
}

export interface Chapter {
    title: string;
    summary: string;            // 100-150 字主題摘要
    bullets: string[];
    key_quotes: KeyQuote[];
    sub_chapters: SubChapter[]; // Layer 3 展開
}

export interface SpeakerContribution {
    speaker: string;            // SPEAKER_xx；前端 transform display_name
    role?: string;
    speak_time_pct: number;     // 0-100
    main_topics: string[];
    key_contribution: string;
}

export interface NextStep {
    task: string;
    assignee?: string;
    due?: string;               // ISO date
    follow_up_meeting?: string;
}

export interface CrossMeetingRef {
    topic: string;
    related_meeting_id: string;
    related_meeting_title: string;
    url: string;                // /dashboard/meetings/{id}
    similarity: number;         // 0.0-1.0
}

export interface MeetingSummary {
    summary: string;
    action_items: string[];
    decisions: string[];
    risks: string[];
    // PR21 新欄位（皆 optional 給 backward compat）
    tldr?: string;
    key_quotes?: KeyQuote[];
    // Summary V2 新欄位（Q1-Q8 落地，2026-05-11）
    chapters?: Chapter[];
    speaker_contributions?: SpeakerContribution[];
    next_steps_v2?: NextStep[];           // 注意：sales_bant 模板的舊 next_steps: string[] 可能仍存在
    cross_meeting_refs?: CrossMeetingRef[];
    // sales_bant 額外
    deal_signal?: string;
    objections?: string[];
    BANT?: Record<string, unknown>;
    next_steps?: string[] | NextStep[];   // 向後相容：舊 List[str]，新 List[NextStep]
    // hr_star 額外
    candidate_summary?: string;
    STAR_stories?: unknown[];
    key_strengths?: string[];
    red_flags?: string[];
    fit_score?: number | null;
    // rd 額外
    technical_decisions?: unknown[];
    challenges?: unknown[];
}

export interface MeetingCreate {
    title: string;
    language?: string;
    template_name?: string;
    duration?: number;
    custom_context?: string;
    user_upn?: string;
    is_confidential?: boolean;
}

export interface ApiError {
    detail: string;
}

// PR24 — Sprint 2d frontend: Feedback intake
export type FeedbackIssueType =
    | "transcript_inaccurate"
    | "summary_wrong"
    | "ui_clunky"
    | "system_error"
    | "other";

export type FeedbackSeverity = "minor" | "workaround" | "blocker";

export type FeedbackFrequency = "first" | "rare" | "common" | "always";

export type FeedbackStatus =
    | "open"
    | "in_progress"
    | "fixed"
    | "wontfix"
    | "duplicate";

export interface FeedbackCreate {
    user_upn: string;
    issue_type: FeedbackIssueType;
    summary: string;
    severity: FeedbackSeverity;
    expected?: string;
    actual?: string;
    repro_steps?: string;
    frequency?: FeedbackFrequency;
    attachment_url?: string;
    meeting_id?: string;
    page_url?: string;
    browser_info?: string;
    session_id?: string;
    frontend_version?: string;
    backend_version?: string;
    console_errors?: Array<Record<string, unknown>>;
}

export interface FeedbackRead {
    id: string;
    user_upn: string;
    issue_type: string;
    summary: string;
    severity: string;
    expected?: string | null;
    actual?: string | null;
    repro_steps?: string | null;
    frequency?: string | null;
    attachment_url?: string | null;
    meeting_id?: string | null;
    page_url?: string | null;
    browser_info?: string | null;
    status: string;
    assigned_to?: string | null;
    resolved_at?: string | null;
    admin_notes?: string | null;
    created_at: string;
    updated_at: string;
}

// ==========================================
// API Client
// ==========================================

class ApiClient {
    private baseUrl: string;
    private token: string | null = null;

    constructor(baseUrl: string) {
        this.baseUrl = baseUrl;
    }

    /**
     * Set authentication token for API requests
     */
    setToken(token: string | null): void {
        this.token = token;
    }

    /**
     * Get base URL (for debugging)
     */
    getBaseUrl(): string {
        return this.baseUrl;
    }

    /**
     * Get WebSocket URL (converts http(s) to ws(s))
     */
    getWebSocketUrl(): string {
        return this.baseUrl.replace(/^http/, 'ws');
    }

    /**
     * Generic fetch wrapper with error handling
     */
    private async fetch<T>(
        endpoint: string,
        options: RequestInit = {}
    ): Promise<T> {
        const url = `${this.baseUrl}${endpoint}`;

        // Build headers with optional Authorization
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
            ...(options.headers as Record<string, string>),
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers,
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            // Handle void responses (204 No Content or empty body)
            if (response.status === 204 || response.headers.get('content-length') === '0') {
                return undefined as T;
            }

            // Try to parse JSON, fallback to undefined for empty bodies
            const text = await response.text();
            if (!text) {
                return undefined as T;
            }
            const data = JSON.parse(text);

            // L1 Boundary Normalization: status → lowercase at the source
            // Prevents case mismatch bugs (Backend: "PROCESSING" vs Frontend: "processing")
            // This has caused 3 incidents — normalize here so ALL consumers get lowercase.
            if (data && typeof data === 'object') {
                if ('status' in data && typeof data.status === 'string') {
                    data.status = data.status.toLowerCase();
                }
                // Handle arrays (e.g., GET /meetings returns Meeting[])
                if (Array.isArray(data)) {
                    for (const item of data) {
                        if (item && typeof item === 'object' && 'status' in item && typeof item.status === 'string') {
                            item.status = item.status.toLowerCase();
                        }
                    }
                }
            }

            return data as T;
        } catch (error) {
            if (error instanceof TypeError && error.message === 'Failed to fetch') {
                throw new Error('無法連接到後端服務。請確認服務已啟動。');
            }
            throw error;
        }
    }

    // ==========================================
    // Health Check
    // ==========================================

    /**
     * Check backend health status
     */
    async checkHealth(): Promise<{ status: string; service: string }> {
        return this.fetch('/health');
    }

    // ==========================================
    // Meetings API
    // ==========================================

    /**
     * List all meetings
     */
    async listMeetings(skip = 0, limit = 100): Promise<Meeting[]> {
        return this.fetch<Meeting[]>(`/api/v1/meetings?skip=${skip}&limit=${limit}`);
    }

    /**
     * Get a single meeting by ID
     */
    async getMeeting(meetingId: string): Promise<Meeting> {
        return this.fetch<Meeting>(`/api/v1/meetings/${meetingId}`);
    }

    /**
     * Create a new meeting
     */
    async createMeeting(data: MeetingCreate): Promise<Meeting> {
        return this.fetch<Meeting>('/api/v1/meetings', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    /**
     * Generate summary for a meeting
     */
    async generateSummary(
        meetingId: string,
        templateType = 'general',
        context = '',
        length = 'medium',
        style = 'formal'
    ): Promise<{ message: string; task_id: string }> {
        const params = new URLSearchParams({
            template_type: templateType,
            context,
            length,
            style,
        });
        return this.fetch(`/api/v1/meetings/${meetingId}/generate-summary?${params}`, {
            method: 'POST',
        });
    }

    /**
     * Soft-delete a meeting by ID.
     *
     * 2026-05-11 update: 後端改為 soft delete + audit log；傳 requester_upn
     * 讓 audit 能寫進「誰刪了它」。空字串 fallback 為 anonymous。
     */
    async deleteMeeting(meetingId: string, requesterUpn?: string): Promise<void> {
        const q = requesterUpn ? `?requester_upn=${encodeURIComponent(requesterUpn)}` : '';
        await this.fetch(`/api/v1/meetings/${meetingId}${q}`, {
            method: 'DELETE',
        });
    }

    /**
     * Get a signed URL for direct GCS upload
     */
    async getUploadUrl(meetingId: string, filename: string, contentType: string): Promise<{ uploadUrl: string }> {
        return this.fetch(`/api/v1/meetings/${meetingId}/upload-url`, {
            method: 'POST',
            body: JSON.stringify({ filename, contentType }),
        });
    }

    /**
     * Upload a file directly to GCS using a signed URL.
     *
     * 2026-05-12：原本用 `fetch` PUT，但 fetch API 缺 upload progress event，
     * 無法顯示 % 進度。改用 XHR 取得 upload.onprogress。
     *
     * @param onProgress 可選回呼，回傳已上傳 bytes / 總 bytes（0-100 整數 percent）
     */
    async uploadToGcs(
        uploadUrl: string,
        file: File,
        onProgress?: (percent: number, loaded: number, total: number) => void,
    ): Promise<void> {
        return new Promise<void>((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open('PUT', uploadUrl, true);
            xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');

            if (onProgress) {
                xhr.upload.onprogress = (e: ProgressEvent) => {
                    if (e.lengthComputable && e.total > 0) {
                        const percent = Math.min(100, Math.floor((e.loaded / e.total) * 100));
                        onProgress(percent, e.loaded, e.total);
                    }
                };
            }

            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    if (onProgress) onProgress(100, file.size, file.size);
                    resolve();
                } else {
                    reject(new Error(`Failed to upload file. Status: ${xhr.status}`));
                }
            };
            xhr.onerror = () => reject(new Error('Network error during upload'));
            xhr.onabort = () => reject(new Error('Upload aborted'));

            xhr.send(file);
        });
    }

    /**
     * Get a signed URL for audio playback
     */
    async getAudioPlaybackUrl(meetingId: string): Promise<{ audio_url: string }> {
        return this.fetch(`/api/v1/meetings/${meetingId}/audio-url`);
    }

    /**
     * Trigger the background transcription and summarization task
     */
    async startTranscriptionTask(meetingId: string, templateType = 'general', context = '', length = 'medium', style = 'formal'): Promise<{ status: string }> {
        return this.fetch('/api/v1/tasks/transcription', {
            method: 'POST',
            body: JSON.stringify({
                meeting_id: meetingId,
                template_type: templateType,
                context,
                length,
                style
            }),
        });
    }

    /**
     * Regenerate summary for a meeting (triggers background task)
     */
    async regenerateSummary(
        meetingId: string,
        templateName = 'general',
        context = ''
    ): Promise<{ message: string }> {
        return this.fetch(`/api/v1/meetings/${meetingId}/regenerate-summary`, {
            method: 'POST',
            body: JSON.stringify({ template_name: templateName, context }),
        });
    }

    // ==========================================
    // Settings API
    // ==========================================

    /**
     * Get correction settings
     */
    async getCorrections(): Promise<Record<string, string>> {
        return this.fetch('/api/v1/settings/corrections');
    }

    /**
     * Update correction settings
     */
    async updateCorrections(corrections: Record<string, string>): Promise<void> {
        await this.fetch('/api/v1/settings/corrections', {
            method: 'POST',
            body: JSON.stringify(corrections),
        });
    }

    // --- Phase 8.2: Template API ---
    
    async getTemplates(): Promise<TemplateDTO[]> {
        return this.fetch('/api/v1/templates');
    }

    async getTemplate(id: string): Promise<TemplateDTO> {
        return this.fetch(`/api/v1/templates/${id}`);
    }

    async createTemplate(data: CreateTemplateDTO): Promise<TemplateDTO> {
        return this.fetch('/api/v1/templates', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    async updateTemplate(id: string, data: UpdateTemplateDTO): Promise<TemplateDTO> {
        return this.fetch(`/api/v1/templates/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    async deleteTemplate(id: string): Promise<void> {
        await this.fetch(`/api/v1/templates/${id}`, { method: 'DELETE' });
    }

    // --- Phase 8.1.3: Speaker Mapping Edit ---

    async updateSpeakerMappings(meetingId: string, mappings: Record<string, SpeakerMappingDTO>): Promise<{ message: string }> {
        return this.fetch(`/api/v1/meetings/${meetingId}/speakers`, {
            method: 'PATCH',
            body: JSON.stringify({ mappings }),
        });
    }

    // --- Phase D: Summary Version History ---

    async getSummaryVersions(meetingId: string): Promise<SummaryVersionDTO[]> {
        return this.fetch(`/api/v1/meetings/${meetingId}/summary-versions`);
    }

    async restoreSummaryVersion(meetingId: string, versionId: string): Promise<{ message: string; template_name: string }> {
        return this.fetch(`/api/v1/meetings/${meetingId}/restore-summary-version/${versionId}`, {
            method: 'POST',
        });
    }

    /**
     * 2026-05-24 (request #1)：批次軟刪除多筆 meeting。
     * Backend: POST /api/v1/meetings/bulk-delete
     */
    async bulkDeleteMeetings(
        meetingIds: string[],
        requesterUpn?: string,
    ): Promise<{ deleted: number; skipped_already_deleted: number; not_found: string[] }> {
        return this.fetch('/api/v1/meetings/bulk-delete', {
            method: 'POST',
            body: JSON.stringify({ meeting_ids: meetingIds, requester_upn: requesterUpn }),
        });
    }

    // --- Feedback API (PR24) ---
    async createFeedback(payload: FeedbackCreate): Promise<FeedbackRead> {
        return this.fetch('/api/v1/feedback', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
    }

    async listMyFeedback(userUpn: string, skip = 0, limit = 50): Promise<FeedbackRead[]> {
        const q = new URLSearchParams({ user_upn: userUpn, skip: String(skip), limit: String(limit) });
        return this.fetch(`/api/v1/feedback?${q.toString()}`);
    }

    // --- RAG API ---
    async askRag(question: string, userUpn: string = 'global_test@company.com', history?: RagChatMessage[], meetingIds?: string[]): Promise<RagResponse> {
        return this.fetch('/api/v1/rag/ask', {
            method: 'POST',
            body: JSON.stringify({
                question,
                history: history || [],
                user_upn: userUpn,
                meeting_ids: meetingIds,
                top_k: 10
            }),
        });
    }
}

// Phase 8.2: Template types
export interface TemplateSectionDTO {
    title: string;
    instruction: string;
    output_key: string;
    output_type: string;
}

export interface TemplateDTO {
    id: string;
    name: string;
    display_name: string;
    description: string;
    category: string;
    icon: string;
    color: string;
    sections: TemplateSectionDTO[];
    tags: string[];
    is_system: boolean;
    is_active: boolean;
}

export interface CreateTemplateDTO {
    name: string;
    display_name: string;
    description?: string;
    category?: string;
    icon?: string;
    color?: string;
    sections?: TemplateSectionDTO[];
    tags?: string[];
    fork_from?: string;
}

export interface UpdateTemplateDTO {
    display_name?: string;
    description?: string;
    category?: string;
    icon?: string;
    color?: string;
    sections?: TemplateSectionDTO[];
    tags?: string[];
    is_active?: boolean;
}

// Phase 8.1.3: Speaker mapping edit
export interface SpeakerMappingDTO {
    display_name: string;
    role?: string;
    color?: string;
}

// Phase D: Summary version history
export interface SummaryVersionDTO {
    id: string;
    template_name: string;
    summary_json: string | null;
    created_at: string | null;
}

// RAG API Type definitions
export interface RagCitation {
    meeting_id: string;
    meeting_title: string;
    speaker: string | null;
    start_time: number | null;
    end_time: number | null;
    content: string;
    similarity: number;
}

export interface RagChatMessage {
    role: string;
    text: string;
}

export interface RagResponse {
    answer: string;
    citations: RagCitation[];
    segments_searched: number;
    question: string;
    /** LLM 自評信心度：high / medium / low / no_answer */
    confidence?: 'high' | 'medium' | 'low' | 'no_answer';
}

// Export singleton instance
export const api = new ApiClient(API_BASE_URL);

// Export API_BASE_URL for display in UI
export { API_BASE_URL };
