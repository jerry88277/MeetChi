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
    status: "recording" | "processing" | "completed" | "failed";
    created_at: string;
    updated_at: string;
    duration: number | null;
    audio_url: string | null;
    language: string;
    template_name: string;
    transcript_raw: string | null;
    transcript_polished: string | null;
    summary_json: string | null;
    transcript_segments: TranscriptSegment[];
}

export interface MeetingSummary {
    summary: string;
    action_items: string[];
    decisions: string[];
    risks: string[];
}

export interface MeetingCreate {
    title: string;
    language?: string;
    template_name?: string;
}

export interface ApiError {
    detail: string;
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

            return response.json();
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
}

// Export singleton instance
export const api = new ApiClient(API_BASE_URL);

// Export API_BASE_URL for display in UI
export { API_BASE_URL };
