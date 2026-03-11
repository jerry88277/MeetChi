"use client";

import { useState, useRef, useCallback } from 'react';
import { api } from '@/lib/api';

export function useRecording() {
    const [recordingMeetingId, setRecordingMeetingId] = useState<string | null>(null);
    const [recordingTitle, setRecordingTitle] = useState('新會議');
    const [isUploading, setIsUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const startRecording = useCallback(async () => {
        const title = prompt(
            '請輸入會議標題：',
            `會議 ${new Date().toLocaleDateString('zh-TW')}`
        ) || `會議 ${new Date().toLocaleDateString('zh-TW')}`;
        setRecordingTitle(title);
        const meeting = await api.createMeeting({ title });
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
    ) => {
        setIsUploading(true);
        try {
            const title = file.name.replace(/\.[^/.]+$/, "");
            const meeting = await api.createMeeting({ title });
            const { uploadUrl } = await api.getUploadUrl(meeting.id, file.name, file.type || 'application/octet-stream');
            await api.uploadToGcs(uploadUrl, file);
            await api.startTranscriptionTask(meeting.id);
            onSuccess(file.name);
        } catch (err) {
            console.error('Upload failed:', err);
            onError(err instanceof Error ? err.message : '上傳檔案失敗');
        } finally {
            setIsUploading(false);
        }
    }, []);

    return {
        recordingMeetingId,
        recordingTitle,
        isUploading,
        fileInputRef,
        startRecording,
        triggerFileInput,
        uploadFile,
    };
}
