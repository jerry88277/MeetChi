const API_BASE_URL = '/api';

export interface Meeting {
    id: string;
    title: string;
    status: string;
    created_at: string;
    duration?: number;
    language: string;
    template_name: string;
    transcript_segments?: TranscriptSegment[];
    summary_json?: string;
}

export interface TranscriptSegment {
    id?: string;
    order: number;
    start_time: number;
    end_time: number;
    speaker?: string;
    content_raw: string;
    content_polished?: string;
    content_translated?: string;
    is_final: boolean;
}

export const api = {
    async createMeeting(title: string, language: string = 'zh', template_name: string = 'general'): Promise<Meeting> {
        const res = await fetch(`${API_BASE_URL}/meetings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, language, template_name }),
        });
        if (!res.ok) throw new Error('Failed to create meeting');
        return res.json();
    },

    async addSegments(meetingId: string, segments: TranscriptSegment[]): Promise<void> {
        const res = await fetch(`${API_BASE_URL}/meetings/${meetingId}/add_segments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(segments),
        });
        if (!res.ok) throw new Error('Failed to add segments');
    },

    async getMeetings(skip: number = 0, limit: number = 100): Promise<Meeting[]> {
        const res = await fetch(`${API_BASE_URL}/meetings?skip=${skip}&limit=${limit}`);
        if (!res.ok) throw new Error('Failed to fetch meetings');
        return res.json();
    },

    async getMeeting(id: string): Promise<Meeting> {
        const res = await fetch(`${API_BASE_URL}/meetings/${id}`);
        if (!res.ok) throw new Error('Failed to fetch meeting details');
        return res.json();
    },

    async generateSummary(meetingId: string, template_type: string = 'general', context: string = '', length: string = '', style: string = ''): Promise<{ message: string, task_id: string }> {
        const params = new URLSearchParams({ template_type });
        if (context) params.append('context', context);
        if (length) params.append('length', length);
        if (style) params.append('style', style);
        const res = await fetch(`${API_BASE_URL}/meetings/${meetingId}/generate-summary?${params.toString()}`, {
            method: 'POST',
        });
        if (!res.ok) throw new Error('Failed to trigger summary generation');
        return res.json();
    },

    async deleteMeeting(id: string): Promise<void> {
        const res = await fetch(`${API_BASE_URL}/meetings/${id}`, {
            method: 'DELETE',
        });
        if (!res.ok) throw new Error('Failed to delete meeting');
    },

    async getCorrections(): Promise<Record<string, string>> {
        const res = await fetch(`${API_BASE_URL}/settings/corrections`);
        if (!res.ok) return {};
        return res.json();
    },

    async updateCorrections(corrections: Record<string, string>): Promise<void> {
        const res = await fetch(`${API_BASE_URL}/settings/corrections`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(corrections),
        });
        if (!res.ok) throw new Error('Failed to update corrections');
    }
};
