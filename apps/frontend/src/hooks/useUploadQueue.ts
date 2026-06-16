"use client";

import { useState, useRef, useCallback } from 'react';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';

export type UploadTaskStatus = 'queued' | 'uploading' | 'processing' | 'done' | 'error';

export interface UploadTask {
    id: string;
    fileName: string;
    fileSize: number;
    status: UploadTaskStatus;
    progress: number; // 0-100 for upload phase
    meetingId?: string;
    error?: string;
    templateName: string;
    context: string;
    isConfidential: boolean;
    // Internal — not exposed to UI
    _file?: File;
}

const MAX_CONCURRENT = 2;

/**
 * useUploadQueue — Google Drive-style concurrent upload manager.
 * 
 * Replaces single-task upload logic in useRecording.
 * Users can add files at any time; they queue up and upload concurrently (max 2).
 * Transcription tasks fire-and-forget after each upload completes (backend queues them).
 */
export function useUploadQueue() {
    const { data: session } = useSession();
    const sessionUpn = session?.user?.email ?? '';

    const [tasks, setTasks] = useState<UploadTask[]>([]);
    const [isTrayOpen, setIsTrayOpen] = useState(true);
    const activeCountRef = useRef(0);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Helpers to update a single task
    const updateTask = useCallback((taskId: string, patch: Partial<UploadTask>) => {
        setTasks(prev => prev.map(t => t.id === taskId ? { ...t, ...patch } : t));
    }, []);

    const processQueue = useCallback(async (currentTasks?: UploadTask[]) => {
        // Use the latest tasks from state
        setTasks(prev => {
            const queued = prev.filter(t => t.status === 'queued');
            const slotsAvailable = MAX_CONCURRENT - activeCountRef.current;
            if (slotsAvailable <= 0 || queued.length === 0) return prev;

            const toStart = queued.slice(0, slotsAvailable);
            const updated = prev.map(t =>
                toStart.find(s => s.id === t.id)
                    ? { ...t, status: 'uploading' as UploadTaskStatus }
                    : t
            );

            // Launch uploads outside setState
            toStart.forEach(task => {
                activeCountRef.current++;
                executeUpload(task.id, task._file!, task.templateName, task.context, task.isConfidential);
            });

            return updated;
        });
    }, []);

    const executeUpload = useCallback(async (
        taskId: string,
        file: File,
        templateName: string,
        context: string,
        isConfidential: boolean,
    ) => {
        let createdMeetingId: string | undefined;
        try {
            // Get duration
            const duration = await new Promise<number>((resolve) => {
                if (!(file.type.startsWith('audio/') || file.type.startsWith('video/'))) {
                    resolve(0);
                    return;
                }
                const url = URL.createObjectURL(file);
                const audio = new Audio();
                audio.onloadedmetadata = () => { resolve(audio.duration); URL.revokeObjectURL(url); };
                audio.onerror = () => { resolve(0); URL.revokeObjectURL(url); };
                audio.src = url;
            });

            const title = file.name.replace(/\.[^/.]+$/, "").trim() || "未命名會議";
            const meeting = await api.createMeeting({
                title,
                template_name: templateName,
                duration,
                custom_context: context,
                user_upn: sessionUpn,
                is_confidential: isConfidential,
            });
            createdMeetingId = meeting.id;
            updateTask(taskId, { meetingId: meeting.id });

            const contentType = file.type || 'application/octet-stream';
            const progressCb = (percent: number) => {
                updateTask(taskId, { progress: percent });
            };

            // Upload strategy: Resumable (fastest) → Signed PUT → Chunked (fallback)
            let uploaded = false;

            // Strategy 1: GCS Resumable Upload (8MB chunks, direct to GCS)
            try {
                const { session_uri } = await api.getResumableUploadSession(meeting.id, file.name, contentType);
                await api.resumableUpload(session_uri, file, progressCb);
                uploaded = true;
            } catch (resumableErr) {
                console.warn('[MeetChi] Resumable upload failed, trying signed PUT:', resumableErr);
            }

            // Strategy 2: Signed URL PUT (single request)
            if (!uploaded) {
                try {
                    const { uploadUrl } = await api.getUploadUrl(meeting.id, file.name, contentType);
                    await api.uploadToGcs(uploadUrl, file, progressCb);
                    uploaded = true;
                } catch (directErr) {
                    console.warn('[MeetChi] Signed PUT failed, trying chunked:', directErr);
                }
            }

            // Strategy 3: Chunked via backend (most compatible, slowest)
            if (!uploaded) {
                await api.chunkedUpload(meeting.id, file, progressCb);
            }

            // Upload done → trigger transcription (fire-and-forget)
            updateTask(taskId, { status: 'processing', progress: 100, _file: undefined });
            api.startTranscriptionTask(meeting.id, templateName, context).catch((err) => {
                console.error('Transcription task trigger failed:', err);
            });

        } catch (err) {
            console.error(`Upload ${taskId} failed:`, err);
            const rawMsg = err instanceof Error ? err.message : '';
            const isInfraError = /gcs|bucket|googleapis|storage\.cloud|signed.url|cors|access denied/i.test(rawMsg);
            updateTask(taskId, {
                status: 'error',
                _file: file, // keep file ref for retry
                error: isInfraError
                    ? '上傳失敗，請確認網路連線後重試。'
                    : (rawMsg || '上傳檔案失敗'),
            });
            // Clean up orphan
            if (createdMeetingId) {
                api.deleteMeeting(createdMeetingId, sessionUpn).catch(() => {});
            }
        } finally {
            activeCountRef.current--;
            // Process next in queue
            setTimeout(() => processQueue(), 0);
        }
    }, [sessionUpn, updateTask, processQueue]);

    /**
     * Add files to the upload queue. Can be called at any time.
     */
    const enqueueFiles = useCallback((
        files: File[],
        templateName = 'general',
        context = '',
        isConfidential = false,
    ) => {
        const newTasks: UploadTask[] = files.map(file => ({
            id: `upload-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            fileName: file.name,
            fileSize: file.size,
            status: 'queued' as UploadTaskStatus,
            progress: 0,
            templateName,
            context,
            isConfidential,
            _file: file,
        }));

        setTasks(prev => [...prev, ...newTasks]);
        setIsTrayOpen(true);

        // Kick off processing after state update
        setTimeout(() => processQueue(), 0);
    }, [processQueue]);

    /**
     * Retry a failed upload task.
     */
    const retryTask = useCallback((taskId: string) => {
        setTasks(prev => prev.map(t =>
            t.id === taskId && t.status === 'error'
                ? { ...t, status: 'queued' as UploadTaskStatus, progress: 0, error: undefined }
                : t
        ));
        setTimeout(() => processQueue(), 0);
    }, [processQueue]);

    /**
     * Remove a task from the queue (only if queued or error or done).
     */
    const removeTask = useCallback((taskId: string) => {
        setTasks(prev => prev.filter(t => {
            if (t.id !== taskId) return true;
            // Can't remove actively uploading tasks
            return t.status === 'uploading' || t.status === 'processing';
        }));
    }, []);

    /**
     * Clear all completed/error tasks from the tray.
     */
    const clearCompleted = useCallback(() => {
        setTasks(prev => prev.filter(t => t.status === 'uploading' || t.status === 'processing' || t.status === 'queued'));
    }, []);

    const triggerFileInput = useCallback(() => {
        fileInputRef.current?.click();
    }, []);

    // Computed — only 'uploading' counts as "active" for beforeunload protection.
    // 'processing' means file is already on GCS; safe to refresh.
    const hasActiveUploads = tasks.some(t => t.status === 'uploading');
    const activeCount = tasks.filter(t => t.status === 'uploading').length;
    const totalCount = tasks.length;
    const completedCount = tasks.filter(t => t.status === 'done').length;

    return {
        tasks,
        enqueueFiles,
        retryTask,
        removeTask,
        clearCompleted,
        triggerFileInput,
        fileInputRef,
        hasActiveUploads,
        activeCount,
        totalCount,
        completedCount,
        isTrayOpen,
        setIsTrayOpen,
    };
}
