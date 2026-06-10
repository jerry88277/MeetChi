"use client";

import { useState, useRef, useCallback, useMemo } from 'react';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';

// Phase 9.1: Upload State Machine — replaces boolean isUploading
export type UploadState = 'idle' | 'uploading' | 'processing' | 'done' | 'error';

export function useRecording() {
    // 2026-05-22 (feedback #9 RAG)：原硬編 user_upn: sessionUpn 導致
    // 上傳會議 owner=test@company.com，但 RAG 用 session email 查 →
    // meeting_participants JOIN 不到 → RAG「未找到相關段落」。
    // 改用 session.user.email 讓 owner 與 RAG query 對齊。
    const { data: session } = useSession();
    const sessionUpn = session?.user?.email ?? 'test@company.com';

    const [recordingMeetingId, setRecordingMeetingId] = useState<string | null>(null);
    const [recordingTitle, setRecordingTitle] = useState('新會議');
    const [uploadState, setUploadState] = useState<UploadState>('idle');
    const [lastUploadedMeetingId, setLastUploadedMeetingId] = useState<string | null>(null);
    // 2026-05-12 (feedback)：上傳進度 0-100；大檔上傳時讓 user 知道還剩多少
    const [uploadProgress, setUploadProgress] = useState(0);
    // 上傳檔名 + 大小，給 overlay 顯示
    const [uploadFileName, setUploadFileName] = useState<string>('');
    const [uploadFileSize, setUploadFileSize] = useState<number>(0);
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
        const meeting = await api.createMeeting({ title, user_upn: sessionUpn });
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
        // C1: Guard against duplicate uploads — prevent parallel uploads
        if (uploadState !== 'idle') return;
        setUploadState('uploading');
        setLastUploadedMeetingId(null);
        setUploadProgress(0);
        setUploadFileName(file.name);
        setUploadFileSize(file.size);
        // Hoist meeting ref so catch block can clean up orphan on upload failure
        let createdMeetingId: string | undefined;
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
                user_upn: sessionUpn,
                is_confidential: isConfidential,
            });
            createdMeetingId = meeting.id;
            
            const { uploadUrl } = await api.getUploadUrl(meeting.id, file.name, file.type || 'application/octet-stream');
            // Try direct GCS first; fall back through proxy, then chunked upload
            try {
                await api.uploadToGcs(uploadUrl, file, (percent) => {
                    setUploadProgress(percent);
                });
            } catch (directErr) {
                console.warn('[MeetChi] Direct GCS upload failed, trying chunked upload:', directErr);
                await api.chunkedUpload(meeting.id, file, (percent) => {
                    setUploadProgress(percent);
                });
            }

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
            // Sanitize raw infrastructure errors (GCS bucket URLs, googleapis, etc.)
            const rawMsg = err instanceof Error ? err.message : '';
            const isInfraError = /gcs|bucket|googleapis|storage\.cloud|signed.url|cors|access denied/i.test(rawMsg);
            onError(isInfraError
                ? '音檔上傳失敗，請確認網路連線後重試。若持續發生請透過回報功能通知管理員。'
                : (rawMsg || '上傳檔案失敗'));
            // Clean up orphan meeting if it was created but upload failed.
            // Prevents confusing "failed" card appearing after an upload error.
            if (createdMeetingId) {
                api.deleteMeeting(createdMeetingId, sessionUpn).catch((delErr) => {
                    console.warn('[MeetChi] Orphan meeting cleanup failed:', delErr);
                });
            }
        }
    }, [uploadState, sessionUpn]);

    // Called by parent when polling detects completion
    const resetUploadState = useCallback(() => {
        setUploadState('idle');
        setLastUploadedMeetingId(null);
        setUploadProgress(0);
        setUploadFileName('');
        setUploadFileSize(0);
    }, []);

    return {
        recordingMeetingId,
        recordingTitle,
        isUploading,          // backward-compatible boolean
        uploadState,          // Phase 9.1: fine-grained state
        uploadProgress,       // 2026-05-12: 0-100 byte 進度，給 overlay 顯示
        uploadFileName,       // 2026-05-12: 上傳檔名，給 overlay 顯示
        uploadFileSize,       // 2026-05-12: 上傳檔案大小（bytes），給 overlay 顯示
        lastUploadedMeetingId, // Phase 9.1: for parent to start polling
        fileInputRef,
        startRecording,
        triggerFileInput,
        uploadFile,
        resetUploadState,     // Phase 9.1: reset after polling completes
    };
}
