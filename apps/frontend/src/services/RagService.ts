import { api } from '@/lib/api';

export interface RagReference {
    meeting_id: string;
    meeting_title: string;
    speaker?: string;
    start_time?: number;
    end_time?: number;
    content: string;
    similarity: number;
}

export interface RagResponse {
    answer: string;
    citations: RagReference[];
    segments_searched: number;
    question: string;
}

export class RagService {
    /**
     * Ask a question to the RAG system
     */
    static async askQuestion(
        question: string,
        userUpn: string = 'test@company.com',
        topK: number = 3
    ): Promise<RagResponse> {
        try {
            // Re-using the ApiClient's fetch wrapper but we need access to it.
            // Since `api` has a private fetch, we might need a workaround or add a generic post method to api.ts.
            // However, we can also use fetch directly wrapped by API_BASE_URL.
            const baseUrl = api.getBaseUrl();
            const response = await fetch(`${baseUrl}/api/v1/rag/ask`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    question,
                    user_upn: userUpn,
                    top_k: topK
                })
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Failed to fetch RAG answer' }));
                throw new Error(err.detail || 'RAG API error');
            }

            return await response.json();
        } catch (error) {
            console.error('RagService API Error:', error);
            throw error;
        }
    }
}
