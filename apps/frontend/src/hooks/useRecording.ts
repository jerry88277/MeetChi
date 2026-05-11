"use client";

import { useState, useRef, useCallback, useMemo } from 'react';
import { api } from '@/lib/api';

// Phase 9.1: Upload State Machine — replaces boolean isUploading
export type UploadState = 'idle' | 'uploading' | 'processing' | 'done' | 'error';

export function useRecording() {
    const [recordingMeetingId, setRecordingMeetingId] = useState<string | null>(null);
    const [recordingTitle, setRecordingTitle] = useState('新會議');
    const [uploadState, setUploadState] = useState<UploadState>('idle');
    const [lastUploadedMeetingId, setLastUploadedMeetingId] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Backward-compatible computed property
    const isUploading = useMemo(
        () => uploadState === 'uploading' || uploadState === 'processing',
        [uploadState]
    );

    const startRecording = useCallback(async () => {
        const title = prompt(
            '請輸入會議標題：',
            `會議 ${new Date().toLocaleDateString('zh-TW')}`
        ) || `會議 ${new Date().toLocaleDateString('zh-TW')}`;
        setRecordingTitle(title);
        const meeting = await api.createMeeting({ title, user_upn: 'test@company.com' });
        setRecordingMeetingId(meeting.id);
        return meeting.id;
    }, []);

    const triggerFileInput = useCallback(() => {
        fileInputRef.current?.click();
    }, []);

    const uploadFile = useCallback(async (
        file: File,
        onSuccess: (fileName: string) => void,
        onError: (msg: string) => void,
        templateName = 'general',
        context = '',
        isConfidential = false,
    ) => {
        setUploadState('uploading');
        setLastUploadedMeetingId(null);
        try {
            // Get audio duration using HTMLAudioElement
            const getDuration = (file: File): Promise<number> => {
                return new Promise((resolve) => {
                    const objectUrl = URL.createObjectURL(file);
                    const audio = new Audio();
                    audio.onloadedmetadata = () => {
                        resolve(audio.duration);
                        URL.revokeObjectURL(objectUrl);
                    };
                    audio.onerror = () => {
                        resolve(0); // fallback if unable to parse
                        URL.revokeObjectURL(objectUrl);
                    };
                    audio.src = objectUrl;
                });
            };
            
            const duration = await getDuration(file);
            const title = file.name.replace(/\.[^/.]+$/, "");
            
            const meeting = await api.createMeeting({
                title,
                template_name: templateName,
                duration,
                custom_context: context,
                user_upn: 'test@company.com',
                is_confidential: isConfidential,
            });
            
            const { uploadUrl } = await api.getUploadUrl(meeting.id, file.name, file.type || 'application/octet-stream');
            await api.uploadToGcs(uploadUrl, file);

            // Phase 9.1 Fix: Set state BEFORE triggering task so polling starts immediately.
            // The backend endpoint is synchronous (blocks until processing completes),
            // so we must not await it — otherwise UI freezes for 2-4 minutes.
            setUploadState('processing');
            setLastUploadedMeetingId(meeting.id);

            // Fire-and-forget: let polling track PROCESSING → COMPLETED transition
            // Phase C: Pass user-selected templateName and context through the chain
            api.startTranscriptionTask(meeting.id, templateName, context).catch((err) => {
                console.error('Transcription task trigger failed:', err);
                // Polling will detect FAILED status from backend
            });

            onSuccess(file.name);
        } catch (err) {
            console.error('Upload failed:', err);
            setUploadState('error');
            onError(err instanceof Error ? err.message : '上傳檔案失敗');
        }
    }, []);

    // Called by parent when polling detects completion
    const resetUploadState = useCallback(() => {
        setUploadState('idle');
        setLastUploadedMeetingId(null);
    }, []);

    return {
        recordingMeetingId,
        recordingTitle,
        isUploading,          // backward-compatible boolean
        uploadState,          // Phase 9.1: fine-grained state
        lastUploadedMeetingId, // Phase 9.1: for parent to start polling
        fileInputRef,
        startRecording,
        triggerFileInput,
        uploadFile,
        resetUploadState,     // Phase 9.1: reset after polling completes
    };
}
