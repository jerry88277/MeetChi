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
    status: "recording" | "processing" | "completed" | "failed" | "pending" | "transcribed";
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
    completed_at: string | null;  // Processing completion timestamp
    transcript_segments: TranscriptSegment[];
    is_confidential?: boolean;  // Sprint 2e Phase 1 (2026-05-11)
    failure_reason?: string | null;  // 2026-05-25 Y7
    processing_stage?: "queued" | "transcribing" | "diarizing" | "summarizing" | null;  // 2026-06-18
    audio_stats?: string | null;  // 2026-07-03：上傳音檔健康報告 (JSON 字串)
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
    async listMeetings(skip = 0, limit = 100, userUpn?: string, keyword?: string, dateFrom?: string, dateTo?: string): Promise<Meeting[]> {
        const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
        if (userUpn) params.set('user_upn', userUpn);
        if (keyword) params.set('keyword', keyword);
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo) params.set('date_to', dateTo);
        return this.fetch<Meeting[]>(`/api/v1/meetings?${params.toString()}`);
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
        signal?: AbortSignal,
    ): Promise<void> {
        return new Promise<void>((resolve, reject) => {
            if (signal?.aborted) {
                reject(new DOMException('Upload aborted', 'AbortError'));
                return;
            }
            const xhr = new XMLHttpRequest();
            xhr.open('PUT', uploadUrl, true);
            xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
            if (signal) signal.addEventListener('abort', () => xhr.abort(), { once: true });

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
     * Get a GCS resumable upload session URI.
     * Much faster than signed PUT for large files (>10MB).
     */
    async getResumableUploadSession(meetingId: string, filename: string, contentType: string): Promise<{ session_uri: string }> {
        return this.fetch(`/api/v1/meetings/${meetingId}/upload-resumable`, {
            method: 'POST',
            body: JSON.stringify({ filename, contentType }),
        });
    }

    /**
     * Upload a file using GCS resumable upload protocol.
     * Uploads in 8MB chunks directly to GCS (bypasses backend for data transfer).
     * Supports progress tracking and automatic resume on failure.
     */
    async resumableUpload(
        sessionUri: string,
        file: File,
        onProgress?: (percent: number, loaded: number, total: number) => void,
        signal?: AbortSignal,
    ): Promise<void> {
        const CHUNK_SIZE = 8 * 1024 * 1024; // 8MB chunks (GCS minimum is 256KB)
        const totalSize = file.size;
        let offset = 0;

        while (offset < totalSize) {
            if (signal?.aborted) throw new DOMException('Upload aborted', 'AbortError');
            const end = Math.min(offset + CHUNK_SIZE, totalSize);
            const chunk = file.slice(offset, end);
            const isLast = end === totalSize;

            const contentRange = `bytes ${offset}-${end - 1}/${totalSize}`;

            const response = await fetch(sessionUri, {
                method: 'PUT',
                headers: {
                    'Content-Length': String(end - offset),
                    'Content-Range': contentRange,
                },
                body: chunk,
                signal,
            });

            if (isLast && response.status === 200) {
                // Upload complete
                if (onProgress) onProgress(100, totalSize, totalSize);
                return;
            } else if (!isLast && (response.status === 308 || response.status === 200)) {
                // Chunk accepted, continue
                offset = end;
                if (onProgress) {
                    const percent = Math.floor((offset / totalSize) * 100);
                    onProgress(percent, offset, totalSize);
                }
            } else if (response.status >= 500) {
                // Server error — retry this chunk after brief delay
                await new Promise(r => setTimeout(r, 2000));
                // Don't advance offset, retry same chunk
            } else {
                throw new Error(`Resumable upload failed at offset ${offset}: HTTP ${response.status}`);
            }
        }
    }

    /**
     * Get audio playback URL — uses backend streaming proxy to bypass
     * enterprise firewall/proxy that may block direct GCS access.
     */
    async getAudioPlaybackUrl(meetingId: string): Promise<{ audio_url: string }> {
        // Use backend proxy stream endpoint (same origin, no CORS/firewall issues)
        return { audio_url: `${this.baseUrl}/api/v1/meetings/${meetingId}/audio-stream` };
    }

    /**
     * Upload audio via backend proxy (multipart POST → backend → GCS).
     * Use this instead of getUploadUrl+uploadToGcs when direct GCS access is
     * blocked by corporate proxies.
     */
    async proxyUpload(
        meetingId: string,
        file: File,
        onProgress?: (percent: number, loaded: number, total: number) => void,
    ): Promise<void> {
        return new Promise<void>((resolve, reject) => {
            const formData = new FormData();
            formData.append('file', file);

            const xhr = new XMLHttpRequest();
            xhr.open('POST', `${this.baseUrl}/api/v1/meetings/${meetingId}/upload`, true);

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
                    reject(new Error(`Upload failed. Status: ${xhr.status} — ${xhr.responseText}`));
                }
            };
            xhr.onerror = () => reject(new Error('Network error during proxy upload'));
            xhr.onabort = () => reject(new Error('Upload aborted'));

            xhr.send(formData);
        });
    }

    /**
     * Chunked upload: split file into 2 MB pieces and POST each piece to the backend
     * as raw application/octet-stream. Uploads CONCURRENCY chunks in parallel with
     * per-chunk retry to handle transient proxy drops.
     */
    async chunkedUpload(
        meetingId: string,
        file: File,
        onProgress?: (percent: number, loaded: number, total: number) => void,
        signal?: AbortSignal,
    ): Promise<void> {
        const CHUNK_SIZE = 8 * 1024 * 1024; // 8 MB per chunk (was 2MB)
        const CONCURRENCY = 4;              // 4 parallel (was 2)
        const MAX_RETRIES = 3;
        const totalChunks = Math.max(1, Math.ceil(file.size / CHUNK_SIZE));

        const uploadedBytes = new Array<number>(totalChunks).fill(0);

        const reportProgress = () => {
            if (!onProgress) return;
            const loaded = uploadedBytes.reduce((a, b) => a + b, 0);
            onProgress(Math.min(99, Math.floor(loaded / file.size * 100)), loaded, file.size);
        };

        const uploadChunkOnce = (i: number, chunk: Blob, url: string): Promise<void> =>
            new Promise<void>((resolve, reject) => {
                if (signal?.aborted) {
                    reject(new DOMException('Upload aborted', 'AbortError'));
                    return;
                }
                const xhr = new XMLHttpRequest();
                xhr.open('POST', url, true);
                xhr.setRequestHeader('Content-Type', 'application/octet-stream');
                if (signal) signal.addEventListener('abort', () => xhr.abort(), { once: true });

                xhr.upload.onprogress = (e: ProgressEvent) => {
                    if (e.lengthComputable && e.total > 0) {
                        uploadedBytes[i] = e.loaded;
                        reportProgress();
                    }
                };
                xhr.onload = () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        const start = i * CHUNK_SIZE;
                        const end = Math.min(start + CHUNK_SIZE, file.size);
                        uploadedBytes[i] = end - start;
                        reportProgress();
                        resolve();
                    } else {
                        reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText.slice(0, 200)}`));
                    }
                };
                xhr.onerror = () => reject(new Error('Network error'));
                xhr.onabort = () => reject(new Error('Aborted'));
                xhr.send(chunk);
            });

        const uploadChunkWithRetry = async (i: number): Promise<void> => {
            const start = i * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, file.size);
            const chunk = file.slice(start, end);
            const url = `${this.baseUrl}/api/v1/meetings/${meetingId}/upload-chunk` +
                `?index=${i}&total=${totalChunks}&filename=${encodeURIComponent(file.name)}`;

            let lastErr: Error | null = null;
            for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
                if (signal?.aborted) throw new DOMException('Upload aborted', 'AbortError');
                if (attempt > 0) {
                    // Exponential back-off: 1s, 2s
                    await new Promise(r => setTimeout(r, 1000 * attempt));
                    uploadedBytes[i] = 0; // reset progress for this chunk on retry
                }
                try {
                    await uploadChunkOnce(i, chunk, url);
                    return;
                } catch (err) {
                    lastErr = err as Error;
                    console.warn(`[MeetChi] Chunk ${i}/${totalChunks} attempt ${attempt + 1} failed:`, err);
                }
            }
            throw new Error(`Chunk ${i}/${totalChunks} failed after ${MAX_RETRIES} attempts: ${lastErr?.message}`);
        };

        // Upload with controlled concurrency: keep CONCURRENCY slots busy
        let nextChunk = 0;
        const runSlot = async (): Promise<void> => {
            while (nextChunk < totalChunks) {
                const i = nextChunk++;
                await uploadChunkWithRetry(i);
            }
        };
        const slots = Array.from({ length: Math.min(CONCURRENCY, totalChunks) }, runSlot);
        await Promise.all(slots);

        if (onProgress) onProgress(100, file.size, file.size);
    }

    /**
     * Trigger the background transcription and summarization task
     */
    async startTranscriptionTask(meetingId: string, templateType = 'general', context = '', length = 'medium', style = 'formal'): Promise<{ status: string }> {
        return this.fetch('/api/v1/tasks/enqueue-transcription', {
            method: 'POST',
            body: JSON.stringify({
                meeting_id: meetingId,
                template_type: templateType,
                context,
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

    async deleteTemplate(id: string, force = false): Promise<{ deleted?: boolean; warning?: boolean; message?: string }> {
        const query = force ? '?force=true' : '';
        return this.fetch(`/api/v1/templates/${id}${query}`, { method: 'DELETE' });
    }

    // --- Phase 8.1.3: Speaker Mapping Edit ---

    async updateSpeakerMappings(meetingId: string, mappings: Record<string, SpeakerMappingDTO>): Promise<{ message: string }> {
        return this.fetch(`/api/v1/meetings/${meetingId}/speakers`, {
            method: 'PATCH',
            body: JSON.stringify({ mappings }),
        });
    }

    // --- Feature #2 (2026-07-06): 逐段重指派說話者 ---
    async updateSegmentSpeakers(
        meetingId: string,
        updates: Record<string, string>,
    ): Promise<{ message: string; changed: number }> {
        return this.fetch(`/api/v1/meetings/${meetingId}/segments/speakers`, {
            method: 'PATCH',
            body: JSON.stringify({ updates }),
        });
    }

    // --- Feature #3 (2026-07-06): 以最新說話者標籤同步摘要（LLM 快掃 + 建議重生）---
    async resyncSummarySpeakers(
        meetingId: string,
    ): Promise<{ updated: boolean; summary: string | null; recommend_regenerate: boolean; reason: string | null; changed_count: number }> {
        return this.fetch(`/api/v1/meetings/${meetingId}/resync-summary-speakers`, {
            method: 'POST',
        });
    }

    async renameMeeting(meetingId: string, title: string): Promise<{ message: string; new_title: string }> {
        return this.fetch(`/api/v1/meetings/${meetingId}/title`, {
            method: 'PATCH',
            body: JSON.stringify({ title }),
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

    async listAdminFeedback(requesterUpn: string, statusFilter?: string, issueType?: string, skip = 0, limit = 100): Promise<FeedbackRead[]> {
        const q = new URLSearchParams({ requester_upn: requesterUpn, skip: String(skip), limit: String(limit) });
        if (statusFilter) q.set('status', statusFilter);
        if (issueType) q.set('issue_type', issueType);
        return this.fetch(`/api/v1/feedback/admin?${q.toString()}`);
    }

    async patchFeedback(id: string, requesterUpn: string, patch: { status?: string; assigned_to?: string; admin_notes?: string }): Promise<FeedbackRead> {
        const q = new URLSearchParams({ requester_upn: requesterUpn });
        return this.fetch(`/api/v1/feedback/${id}?${q.toString()}`, {
            method: 'PATCH',
            body: JSON.stringify(patch),
        });
    }

    // --- RAG API ---
    /**
     * 2026-05-25 Y5：取得使用者 RAG 查詢歷史
     * frontend 看 90 天；backend 保留 10 年
     */
    async getRagHistory(userUpn: string, days: number = 90, limit: number = 100): Promise<RagHistoryItem[]> {
        const q = new URLSearchParams({ user_upn: userUpn, days: String(days), limit: String(limit) });
        return this.fetch(`/api/v1/rag/history?${q.toString()}`);
    }

    getRagGreeting(userUpn: string): Promise<RagGreetingResponse> {
        const q = new URLSearchParams({ user_upn: userUpn });
        return this.fetch(`/api/v1/rag/greeting?${q.toString()}`);
    }

    async askRag(question: string, userUpn: string, history?: RagChatMessage[], meetingIds?: string[], signal?: AbortSignal): Promise<RagResponse> {
        if (!userUpn) {
            // R-E3: 移除危險預設 'global_test@company.com'——未登入直接擋，避免跨租戶資料外洩
            throw new Error('未登入或無法取得使用者識別，無法查詢。');
        }
        return this.fetch('/api/v1/rag/ask', {
            method: 'POST',
            body: JSON.stringify({
                question,
                history: history || [],
                user_upn: userUpn,
                meeting_ids: meetingIds,
                top_k: 10
            }),
            signal,
        });
    }

    // ==========================================
    // Glossary API (C1: Global + Local terminology)
    // ==========================================

    async listGlobalGlossary(userUpn: string): Promise<GlossaryEntry[]> {
        return this.fetch(`/api/v1/glossary/global?user_upn=${encodeURIComponent(userUpn)}`);
    }

    async createGlobalEntry(userUpn: string, wrongText: string, correctText: string, category = 'company'): Promise<GlossaryEntry> {
        return this.fetch(`/api/v1/glossary/global?user_upn=${encodeURIComponent(userUpn)}`, {
            method: 'POST',
            body: JSON.stringify({ wrong_text: wrongText, correct_text: correctText, category }),
        });
    }

    async deleteGlobalEntry(userUpn: string, entryId: string): Promise<void> {
        return this.fetch(`/api/v1/glossary/global/${entryId}?user_upn=${encodeURIComponent(userUpn)}`, {
            method: 'DELETE',
        });
    }

    async updateGlobalEntry(userUpn: string, entryId: string, wrongText: string, correctText: string, category: string): Promise<GlossaryEntry> {
        return this.fetch(`/api/v1/glossary/global/${entryId}?user_upn=${encodeURIComponent(userUpn)}`, {
            method: 'PUT',
            body: JSON.stringify({ wrong_text: wrongText, correct_text: correctText, category }),
        });
    }

    async listMeetingGlossary(meetingId: string): Promise<GlossaryEntry[]> {
        return this.fetch(`/api/v1/glossary/meeting/${meetingId}`);
    }

    async createMeetingEntry(meetingId: string, wrongText: string, correctText: string): Promise<GlossaryEntry> {
        return this.fetch(`/api/v1/glossary/meeting/${meetingId}`, {
            method: 'POST',
            body: JSON.stringify({ wrong_text: wrongText, correct_text: correctText }),
        });
    }

    async deleteMeetingEntry(meetingId: string, entryId: string): Promise<void> {
        return this.fetch(`/api/v1/glossary/meeting/${meetingId}/${entryId}`, {
            method: 'DELETE',
        });
    }

    async applyGlossaryCorrection(meetingId: string, userUpn: string): Promise<{ meeting_id: string; segments_corrected: number }> {
        return this.fetch(`/api/v1/glossary/apply/${meetingId}?user_upn=${encodeURIComponent(userUpn)}`, {
            method: 'POST',
        });
    }

    // ==========================================
    // Ops Admin API
    // ==========================================

    async getMyRole(): Promise<{ email: string; role: string }> {
        return this.fetch('/api/v1/ops/my-role');
    }

    async getOpsOverview(): Promise<OpsOverview> {
        return this.fetch('/api/v1/ops/overview');
    }

    async listOpsMeetings(params?: {
        user_upn?: string;
        status_filter?: string;
        date_from?: string;
        date_to?: string;
        keyword?: string;
        skip?: number;
        limit?: number;
    }): Promise<OpsMeetingItem[]> {
        const sp = new URLSearchParams();
        if (params?.user_upn) sp.set('user_upn', params.user_upn);
        if (params?.status_filter) sp.set('status_filter', params.status_filter);
        if (params?.date_from) sp.set('date_from', params.date_from);
        if (params?.date_to) sp.set('date_to', params.date_to);
        if (params?.keyword) sp.set('keyword', params.keyword);
        sp.set('skip', String(params?.skip ?? 0));
        sp.set('limit', String(params?.limit ?? 50));
        return this.fetch(`/api/v1/ops/meetings?${sp.toString()}`);
    }

    async listOpsUsers(): Promise<OpsUserStats[]> {
        return this.fetch('/api/v1/ops/users');
    }

    async getOpsMeetingFull(meetingId: string): Promise<any> {
        return this.fetch(`/api/v1/ops/meetings/${meetingId}/full`);
    }

    async updateUserRole(userUpn: string, role: string): Promise<{ message: string }> {
        return this.fetch('/api/v1/ops/roles', {
            method: 'POST',
            body: JSON.stringify({ user_upn: userUpn, role }),
        });
    }

    async resetStuckMeeting(
        meetingId: string,
        opts?: { force?: boolean; reenqueue?: boolean },
    ): Promise<{
        meeting_id: string;
        previous_status: string;
        new_status: string;
        stuck_minutes: number | null;
        reenqueued: boolean;
        message: string;
    }> {
        const sp = new URLSearchParams();
        if (opts?.force) sp.set('force', 'true');
        if (opts?.reenqueue === false) sp.set('reenqueue', 'false');
        const qs = sp.toString();
        return this.fetch(
            `/api/v1/ops/meetings/${meetingId}/reset-stuck${qs ? `?${qs}` : ''}`,
            { method: 'POST' },
        );
    }
}
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
    owner_upn?: string;
    usage_count?: number;
}

export interface CreateTemplateDTO {
    name?: string;
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

// Glossary Types (C1)
export interface GlossaryEntry {
    id: string;
    wrong_text: string;
    correct_text: string;
    category?: string | null;
    usage_count?: number;
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
    /** Y3：LLM 自評信心度 high / medium / low / no_answer */
    confidence?: 'high' | 'medium' | 'low' | 'no_answer';
}

// 2026-05-25 (Y5) RAG 查詢歷史
export interface RagHistoryItem {
    id: string;
    query: string;
    answer_preview: string | null;
    citation_count: number;
    confidence: string | null;
    response_time_ms: number | null;
    created_at: string;
    // R-A1 (2026-07-01)：完整引用來源，供歷史對話載入時還原可點擊的 citations
    citations?: RagCitation[];
}

export interface LastMeetingSummary {
    title: string;
    date: string;
    key_actions: string[];
}

export interface RagGreetingResponse {
    display_name: string;
    meeting_count: number;
    top_topics: string[];
    last_meeting: LastMeetingSummary | null;
    pending_action_count: number;
    greeting_text: string;
    suggested_questions: string[];
}

// Ops Admin types
export interface OpsOverview {
    total_users: number;
    total_meetings: number;
    meetings_completed: number;
    meetings_processing: number;
    meetings_failed: number;
    total_audio_hours: number;
    total_segments: number;
    estimated_monthly_cost_usd: number;
}

export interface OpsMeetingItem {
    id: string;
    title: string;
    status: string;
    owner_upn: string | null;
    created_at: string | null;
    updated_at: string | null;
    duration: number | null;
    segment_count: number;
    processing_stage?: string | null;
    stuck_minutes?: number | null;
    is_stuck?: boolean;
    upload_completed_at: string | null;
    transcription_started_at: string | null;
    transcription_completed_at: string | null;
    embedding_completed_at: string | null;
    total_processing_seconds: number | null;
    failure_reason: string | null;
}

export interface OpsUserStats {
    user_upn: string;
    display_name: string | null;
    meeting_count: number;
    total_audio_seconds: number;
    last_upload_at: string | null;
    estimated_cost_usd: number;
}

// Export singleton instance
export const api = new ApiClient(API_BASE_URL);

// Export API_BASE_URL for display in UI
export { API_BASE_URL };
