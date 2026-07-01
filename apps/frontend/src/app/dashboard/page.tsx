"use client";

import React, { useEffect, useCallback, useRef } from 'react';
import { useSession } from 'next-auth/react';
import {
    Mic,
    Clock,
    FileText,
    CheckCircle2,
    Settings,
    Menu,
    AlertCircle,
    Wifi,
    WifiOff,
    Shield,
    Calendar,
    AlertTriangle,
    UploadCloud,
    MessageSquare,
    Loader2
} from 'lucide-react';
import { api } from '@/lib/api';
import { keys, get, del } from 'idb-keyval';
import type { Meeting } from '@/types/meeting';
import { transformMeeting } from '@/lib/transform';
import { Sidebar } from '@/components/Sidebar';
import { UATBanner } from '@/components/UATBanner';
import { TourOverlay } from '@/components/TourOverlay';
import { DashboardView } from '@/components/DashboardView';
import { DetailView } from '@/components/DetailView';
import { RecordingView } from '@/components/RecordingView';
import { SettingsView } from '@/components/SettingsView';
import { TemplateGallery } from '@/components/TemplateGallery';
import { RagWorkspace } from '@/components/rag/RagWorkspace';
import { RagDrawer } from '@/components/rag/RagDrawer';
import { UploadTray } from '@/components/UploadTray';
import { UploadSettingsModal, type UploadSettings } from '@/components/UploadSettingsModal';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { FeedbackModal } from '@/components/FeedbackModal';
import { AdminFeedbackPanel } from '@/components/AdminFeedbackPanel';
import { OpsAdminPanel } from '@/components/OpsAdminPanel';
import { useMeetings } from '@/hooks/useMeetings';
import { useRecording } from '@/hooks/useRecording';
import { useUploadQueue } from '@/hooks/useUploadQueue';
import { useSummary } from '@/hooks/useSummary';
import { useMeetingPolling } from '@/hooks/useMeetingPolling';
import { useFontSize } from '@/hooks/useFontSize';
import { installConsoleErrorHook } from '@/lib/feedback-metadata';
import { useState } from 'react';
import { toast } from 'sonner';
import { TOUR_STORAGE_KEY } from '@/lib/config';

// --- Main App Component ---
export default function DashboardPage() {
    const { data: session } = useSession();

    // Read initial view from URL ?view= param (for direct links and browser back/forward)
    const getInitialView = (): 'dashboard' | 'record' | 'detail' | 'settings' | 'templates' | 'admin' | 'rag' => {
        if (typeof window === 'undefined') return 'dashboard';
        const v = new URLSearchParams(window.location.search).get('view');
        if (v === 'settings' || v === 'templates' || v === 'rag' || v === 'admin') return v;
        return 'dashboard';
    };

    const [currentView, setCurrentView] = useState<'dashboard' | 'record' | 'detail' | 'settings' | 'templates' | 'admin' | 'rag'>(getInitialView);
    const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    const [isRagSidebarOpen, setIsRagSidebarOpen] = useState(false);
    const [tourOpen, setTourOpen] = useState(false);
    const [isAdmin, setIsAdmin] = useState(false);

    // State-driven confirm dialog to replace window.confirm
    const [confirmState, setConfirmState] = useState<{
        title: string; description: string; variant?: "destructive" | "primary";
        resolve: (ok: boolean) => void;
    } | null>(null);
    const showConfirm = React.useCallback((title: string, description: string, variant: "destructive" | "primary" = "primary"): Promise<boolean> => {
        return new Promise(resolve => {
            setConfirmState({ title, description, variant, resolve });
        });
    }, []);

    // Auto-open tour for first-time users
    React.useEffect(() => {
        const done = localStorage.getItem(TOUR_STORAGE_KEY);
        if (!done) setTourOpen(true);
    }, []);

    // Check admin status
    const [userRole, setUserRole] = useState<string>('user');
    React.useEffect(() => {
        const email = session?.user?.email;
        if (!email) return;
        // Check role via ops API
        api.getMyRole()
            .then(({ role }) => {
                setUserRole(role);
                setIsAdmin(role === 'admin' || role === 'super_admin');
            })
            .catch(() => {
                // Fallback: check old admin feedback API
                api.listAdminFeedback(email, undefined, undefined, 0, 1)
                    .then(() => setIsAdmin(true))
                    .catch(() => setIsAdmin(false));
            });
    }, [session?.user?.email]);

    // Custom hooks
    const {
        meetings, isLoading, error, setError, isConnected,
        successMessage, fetchMeetings, fetchMeetingsWithFilter, showSuccess, deleteMeeting,
    } = useMeetings();

    const {
        recordingMeetingId, recordingTitle, isUploading, uploadState,
        uploadProgress, uploadFileName, uploadFileSize,
        lastUploadedMeetingId, fileInputRef, startRecording, triggerFileInput,
        uploadFile, resetUploadState,
    } = useRecording();

    // Upload queue (Google Drive-style concurrent uploads)
    const uploadQueue = useUploadQueue();

    // Phase C: Upload template & context selection
    const [uploadTemplateName, setUploadTemplateName] = useState('general');
    const [uploadContext, setUploadContext] = useState('');
    // Sprint 2e Phase 1 (2026-05-11): 機密會議旗標，上傳/錄音時 user 切換
    const [uploadConfidential, setUploadConfidential] = useState(false);
    // 國台英語言選擇 (Plan B)：預設「國英」，可選「國台英混合」
    const [uploadLanguage, setUploadLanguage] = useState<'zh' | 'zh-nan'>('zh');
    const [availableTemplates, setAvailableTemplates] = useState<import('@/lib/api').TemplateDTO[]>([]);

    // 2026-05-24 (request #2)：初始化字體大小 hook（從 localStorage 還原），
    // 一進 dashboard 就同步套上 root font-size，所有 rem 單位元素跟著縮放。
    useFontSize();

    useEffect(() => {
        api.getTemplates()
            .then(setAvailableTemplates)
            .catch(() => {/* graceful degradation */});
        // PR24: 啟動 console.error / unhandledrejection 緩衝，給 feedback modal 用
        installConsoleErrorHook();
    }, []);

    // Phase 3: Crash Recovery — Check for stranded recordings in IndexedDB
    const [orphanedBackups, setOrphanedBackups] = useState<string[]>([]);
    const [isRecovering, setIsRecovering] = useState(false);

    const checkOrphanedBackups = useCallback(async () => {
        try {
            const allKeys = await keys();
            const meetingKeys = allKeys.filter(k => typeof k === 'string' && k.startsWith('meeting_audio_')) as string[];
            setOrphanedBackups(meetingKeys);
        } catch (e) {
            console.error('Failed to check IDB keys:', e);
        }
    }, []);

    useEffect(() => {
        if (currentView === 'dashboard') {
            checkOrphanedBackups();
        }
    }, [currentView, checkOrphanedBackups]);

    // PR19: Toast 改用 sonner 統一管理；移除舊 inline banner
    // Confirm dialog state — 取代 confirm() / window.confirm()
    const [pendingDelete, setPendingDelete] = useState<{ meetingId: string } | null>(null);
    const [pendingDiscard, setPendingDiscard] = useState<{ key: string } | null>(null);
    // 2026-05-24 (request #1)：拖曳框選批次刪除 confirm state
    const [pendingBulkDelete, setPendingBulkDelete] = useState<{ meetingIds: string[] } | null>(null);
    const [isBulkDeleting, setIsBulkDeleting] = useState(false);

    // 2026-05-11: FeedbackModal 升級到 page 層；context 含 meetingId 時自動帶入
    const [feedbackContext, setFeedbackContext] = useState<
        { meetingId?: string } | null
    >(null);

    // R-C1：ChatPanel 錯誤氣泡透過全域事件開啟回報視窗（手機看不到 sidebar 回報鈕）
    useEffect(() => {
        const handler = () => setFeedbackContext({});
        window.addEventListener('meetchi:open-feedback', handler);
        return () => window.removeEventListener('meetchi:open-feedback', handler);
    }, []);

    // Phase 9.1: Polling hook — watches lastUploadedMeetingId
    // Root fix: enabled driven by ACTUAL meeting data state, not just UI state
    const hasProcessingMeeting = meetings.some(
        m => m.status === 'processing' || m.status === 'pending'
    );

    const handlePollingStatusChange = useCallback(async (completedMeeting: { id: string; title?: string | null }) => {
        await fetchMeetings();
        resetUploadState();
        // PR19: 帶「查看」action 讓 user 可一鍵跳到 detail
        // 2026-05-11 fix: 點「查看」改用 detail endpoint refetch 取得完整
        // transcript_segments，避免 list 資料缺逐字稿
        const completedId = completedMeeting?.id;
        toast.success('會議摘要已生成完成！', {
            description: completedId ? '點選「查看」即可進入詳情頁。' : undefined,
            action: completedId
                ? {
                      label: '查看',
                      onClick: async () => {
                          try {
                              const full = await api.getMeeting(completedId);
                              setSelectedMeeting(transformMeeting(full));
                              setCurrentView('detail');
                          } catch (err) {
                              console.error('Failed to fetch meeting on toast action:', err);
                              // graceful fallback：用 list 資料切過去（逐字稿區會
                              // 透過 DetailView 既有的空狀態提示）
                              const m = meetings.find((x) => x.id === completedId);
                              if (m) {
                                  setSelectedMeeting(m);
                                  setCurrentView('detail');
                              }
                          }
                      },
                  }
                : undefined,
        });
    }, [fetchMeetings, resetUploadState, meetings]);

    useMeetingPolling(
        lastUploadedMeetingId,
        hasProcessingMeeting || uploadState === 'processing' || uploadQueue.tasks.some(t => t.status === 'processing'),
        handlePollingStatusChange,
    );

    const { isRegenerating, regenerateSummary, regenerateTranscript } = useSummary(fetchMeetings, session?.user?.email || undefined);

    // Sync session token with API client; re-fetch meetings after token is updated
    // so the new account's data is loaded with the correct auth credential.
    useEffect(() => {
        if (session?.idToken) {
            api.setToken(session.idToken);
            fetchMeetings();
        } else if (session !== undefined) {
            api.setToken(null);
        }
    }, [session?.idToken, fetchMeetings]);

    // --- Dashboard Refresh D3 Fix ---
    // D3-1: Visibility Refresh — refetch when tab becomes visible
    useEffect(() => {
        const handleVisibility = () => {
            if (!document.hidden) {
                fetchMeetings();
            }
        };
        document.addEventListener('visibilitychange', handleVisibility);
        return () => document.removeEventListener('visibilitychange', handleVisibility);
    }, [fetchMeetings]);

    // 2026-05-25 (Y1, feedback 7ea78e1a)：詳情頁按瀏覽器上一頁，URL 變了但畫面沒變。
    //   原因：handleViewDetail 用 history.pushState 改 URL 進 SPA detail；返回時瀏覽器
    //   把 URL 回退一格，但沒有任何 React state 監聽，畫面停留在 detail。
    //   修法：popstate event 同步 URL 與 currentView。
    //     URL 變回 /dashboard → setCurrentView('dashboard') + 清空 selectedMeeting
    //     URL 進 /dashboard/meetings/{id} → setCurrentView('detail')（前進按鈕）
    //     URL 帶 ?view=xxx → 回到對應 tab
    useEffect(() => {
        if (typeof window === 'undefined') return;
        const handler = () => {
            const path = window.location.pathname;
            const search = window.location.search;
            const m = path.match(/^\/dashboard\/meetings\/([0-9a-f-]{36})/i);
            if (m) {
                const targetId = m[1];
                if (selectedMeeting?.id === targetId) {
                    setCurrentView('detail');
                } else {
                    api.getMeeting(targetId)
                        .then(full => {
                            setSelectedMeeting(transformMeeting(full));
                            setCurrentView('detail');
                        })
                        .catch(() => setCurrentView('dashboard'));
                }
            } else {
                const viewParam = new URLSearchParams(search).get('view');
                if (viewParam === 'settings' || viewParam === 'templates' || viewParam === 'rag') {
                    setCurrentView(viewParam);
                } else {
                    setSelectedMeeting(null);
                    setCurrentView('dashboard');
                }
            }
        };
        window.addEventListener('popstate', handler);
        return () => window.removeEventListener('popstate', handler);
    }, [selectedMeeting]);

    // 2026-05-12 (feedback)：dashboard 入口檔案上傳防誤操作。
    //   原本 beforeunload 只寫在 RecordingView 內，dashboard 上傳不會生效。
    //   數位時代 70+ MB 影片上傳需數分鐘，使用者很容易誤重整 → 整個 PUT 中斷。
    //   uploadState='uploading' 期間阻擋 reload / close tab（顯示瀏覽器原生
    //   confirm dialog）。'processing' 不必擋——audio 已在 GCS，重整不會丟。
    // beforeunload protection: block when any upload is in progress (old hook OR new queue)
    useEffect(() => {
        if (uploadState !== 'uploading' && !uploadQueue.hasActiveUploads) return;
        const handler = (e: BeforeUnloadEvent) => {
            // 現代瀏覽器不再顯示自訂訊息，但 returnValue 必須設才會跳確認 dialog
            e.preventDefault();
            e.returnValue = '';
        };
        window.addEventListener('beforeunload', handler);
        return () => window.removeEventListener('beforeunload', handler);
    }, [uploadState, uploadQueue.hasActiveUploads]);

    // 2026-06-11: 上傳完成進入 processing 時，立即清除全屏 overlay 並顯示 toast。
    // 讓會議卡片的 "AI 處理中" badge + polling 接管狀態追蹤。
    // 消除使用者疑惑：overlay 擋住畫面 → 無法確認卡片是否已出現。
    // Note: 不呼叫 resetUploadState (會清 lastUploadedMeetingId 導致 polling 停止)
    //       僅將 uploadState 視為 idle（overlay 已移除，不需額外處理）。
    const processingToastShown = useRef(false);
    useEffect(() => {
        if (uploadState === 'processing' && !processingToastShown.current) {
            processingToastShown.current = true;
            fetchMeetings();
            toast.info('音檔已上傳完成', {
                description: 'AI 正在背景處理轉錄與摘要，完成後會通知您。可安全離開或重新整理頁面。',
                duration: 6000,
            });
        }
        if (uploadState === 'idle') {
            processingToastShown.current = false;
        }
    }, [uploadState, fetchMeetings]);

    // D3-2: Smart Interval Safety Net (v15)
    // Only activates when there's a processing meeting but NO active single-meeting poll.
    // This handles: (1) page refresh losing lastUploadedMeetingId, (2) uploads from other devices.
    // When useMeetingPolling is active, this stays dormant to avoid double polling.
    const needsSafetyNet = hasProcessingMeeting && !lastUploadedMeetingId;
    useEffect(() => {
        if (!needsSafetyNet) return;

        // Immediate fetch on activation, then every 10s (P0 fix: heartbeat feedback)
        fetchMeetings();
        const id = setInterval(() => {
            if (!document.hidden) {
                fetchMeetings();
            }
        }, 10_000); // 10s interval — frequent polling for processing state updates

        return () => clearInterval(id);
    }, [needsSafetyNet, fetchMeetings]);

    // F2 (P0): Tab title notification — show completion count when processing
    const completedCount = meetings.filter(m => m.status === 'completed').length;
    const processingCount = meetings.filter(m => m.status === 'processing' || m.status === 'pending').length;
    useEffect(() => {
        if (processingCount > 0) {
            document.title = `(${completedCount} 完成 / ${processingCount} 處理中) MeetChi`;
        } else if (completedCount > 0 && document.title.includes('處理中')) {
            // All done — flash completion
            document.title = `(✓ 全部完成) MeetChi`;
            setTimeout(() => { document.title = 'MeetChi'; }, 5000);
        } else {
            document.title = 'MeetChi';
        }
    }, [completedCount, processingCount]);

    // D3-3: selectedMeeting sync — update detail view when meetings list refreshes
    //
    // 2026-05-11 fix: list endpoint (PR #26 perf) 不回 transcript_segments，所以
    // 直接用 list 內的 meeting 覆蓋 selectedMeeting 會把已 refetch 的 segments
    // 蓋掉 → 詳情頁逐字稿區塊變空。修法：
    //   1. 若 status 從非 completed → completed，呼叫 detail endpoint refetch
    //      完整版（含 segments）
    //   2. 一般狀態變化（summary 更新等）仍用 list 資料 patch，但**保留**
    //      原本的 transcript（避免被 list 的空陣列覆蓋）
    const prevMeetingsRef = useRef(meetings);
    useEffect(() => {
        if (prevMeetingsRef.current !== meetings && selectedMeeting) {
            const updated = meetings.find(m => m.id === selectedMeeting.id);
            if (updated) {
                const justCompleted =
                    updated.status === 'completed' && selectedMeeting.status !== 'completed';
                if (justCompleted) {
                    // refetch full detail to pick up transcript_segments
                    api.getMeeting(updated.id)
                        .then((full) => {
                            const fullTransformed = transformMeeting(full);
                            setSelectedMeeting((prev) =>
                                prev?.id === fullTransformed.id ? fullTransformed : prev
                            );
                        })
                        .catch((err) =>
                            console.error('D3-3: refetch on completion failed:', err)
                        );
                } else if (
                    updated.status !== selectedMeeting.status ||
                    updated.summary !== selectedMeeting.summary
                ) {
                    // 一般 patch：保留 transcript 避免被 list 的空陣列覆蓋
                    setSelectedMeeting({
                        ...updated,
                        transcript: selectedMeeting.transcript?.length
                            ? selectedMeeting.transcript
                            : updated.transcript,
                    });
                }
            }
        }
        prevMeetingsRef.current = meetings;
    }, [meetings, selectedMeeting]);

    // --- Handlers ---
    const handleStartRecord = async () => {
        try {
            await startRecording();
            setCurrentView('record');
        } catch (err) {
            console.error('Failed to create meeting:', err);
            setError(err instanceof Error ? err.message : '建立會議失敗');
        }
    };

    // Upload queue-based file handler (Google Drive style: concurrent, non-blocking)
    const [batchProgress, setBatchProgress] = useState<{ current: number; total: number } | null>(null);
    // U-A2: 選檔後暫存，開啟「上傳設定」視窗（模板/語言/情境/機密），確認才入列
    const [pendingUploadFiles, setPendingUploadFiles] = useState<File[] | null>(null);

    const MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024; // 2GB 上限

    const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
        const fileList = event.target.files;
        if (!fileList || fileList.length === 0) return;
        const files = Array.from(fileList);
        event.target.value = '';
        // 先開設定視窗，讓使用者選模板/語言/情境/機密後再上傳
        setPendingUploadFiles(files);
    };

    const confirmUpload = async (settings: UploadSettings) => {
        const files = pendingUploadFiles;
        setPendingUploadFiles(null);
        if (!files || files.length === 0) return;

        // 記住這次選擇，作為下次預設
        setUploadTemplateName(settings.templateName);
        setUploadLanguage(settings.language);
        setUploadContext(settings.context);
        setUploadConfidential(settings.isConfidential);

        const filesToQueue: File[] = [];
        for (const file of files) {
            // U-C3: 格式檢查 — 有 MIME 但非 audio/video 直接擋下
            if (file.type && !file.type.startsWith('audio/') && !file.type.startsWith('video/')) {
                toast.error(`「${file.name}」不是音訊或影片檔，已略過。`, {
                    description: '支援格式：mp3 / m4a / wav / mp4 等音訊或影片。',
                });
                continue;
            }
            // U-C1: 檔案大小上限
            if (file.size > MAX_UPLOAD_BYTES) {
                toast.error(`「${file.name}」超過 2GB 上限，已略過。`, {
                    description: '請壓縮或分割檔案後再上傳。',
                });
                continue;
            }
            // 大型檔案（>120 分鐘）確認
            if (file.type.startsWith('audio/') || file.type.startsWith('video/')) {
                const duration = await new Promise<number>((resolve) => {
                    const url = URL.createObjectURL(file);
                    const media = new Audio(url);
                    media.addEventListener('loadedmetadata', () => {
                        URL.revokeObjectURL(url);
                        resolve(media.duration / 60);
                    });
                    media.addEventListener('error', () => {
                        URL.revokeObjectURL(url);
                        resolve(0);
                    });
                });
                if (duration > 120) {
                    const confirmed = await showConfirm(
                        '大型檔案提醒',
                        `${file.name} 長度約 ${Math.round(duration)} 分鐘。處理時間可能 20+ 分鐘，是否繼續？`,
                        'primary'
                    );
                    if (!confirmed) continue;
                }
            }
            filesToQueue.push(file);
        }

        if (filesToQueue.length > 0) {
            uploadQueue.enqueueFiles(filesToQueue, settings.templateName, settings.context, settings.isConfidential, settings.language);
            // Refresh meeting list after a delay to pick up new PENDING meetings
            setTimeout(() => fetchMeetings(), 2000);
        }
    };

    const handleViewDetail = async (meeting: Meeting) => {
        // 立即切換到 detail 頁顯示 list 帶來的 metadata (status/title/summary/decisions/risks/keyQuotes)
        setSelectedMeeting(meeting);
        setCurrentView('detail');
        // 2026-05-22 (feedback #8)：URL 加上會議 ID 讓使用者可分享 / 重整保留位置。
        // 使用 history.pushState 不觸發 Next.js 路由重渲染（SPA 內部繼續顯示），
        // 但若 user 重整，Next 會載入 /dashboard/meetings/[meeting_id]/page.tsx
        // deep-link 路由（已存在）→ 看到同樣的詳情頁。
        if (typeof window !== 'undefined') {
            window.history.pushState(null, '', `/dashboard/meetings/${meeting.id}`);
        }

        // 背景補拉完整 transcript_segments — list endpoint 為了效能不回 segments (PR #26)
        // 使用者會先看到 TL;DR 與結論摘要，逐字稿在 1~2s 後到位
        if (meeting.status === 'completed') {
            try {
                const full = await api.getMeeting(meeting.id);
                const fullTransformed = transformMeeting(full);
                // 期間 user 若已點別的會議，避免覆蓋
                setSelectedMeeting(prev =>
                    prev?.id === fullTransformed.id ? fullTransformed : prev
                );
            } catch (err) {
                console.error('Failed to fetch full meeting detail:', err);
                // graceful — list metadata 已顯示，逐字稿區塊保持空狀態提示
            }
        }
    };

    const handleRegenerateSummary = async (meetingId: string, templateName?: string) => {
        try {
            await regenerateSummary(meetingId, selectedMeeting, setSelectedMeeting, templateName);
        } catch (err) {
            console.error('Failed to regenerate summary:', err);
            setError(err instanceof Error ? err.message : '重新生成摘要失敗');
        }
    };

    const handleRegenerateTranscript = async (meetingId: string, templateName?: string) => {
        try {
            await regenerateTranscript(meetingId, selectedMeeting, setSelectedMeeting, templateName);
        } catch (err) {
            console.error('Failed to regenerate transcript:', err);
            setError(err instanceof Error ? err.message : '重新整理與轉錄失敗');
        }
    };

    const handleBackToDashboard = () => {
        setSelectedMeeting(null);
        setCurrentView('dashboard');
        if (typeof window !== 'undefined') {
            const loc = window.location;
            if (loc.pathname.startsWith('/dashboard/meetings/') || loc.search.includes('view=')) {
                window.history.pushState(null, '', '/dashboard');
            }
        }
    };

    const handleRenameMeeting = async (meetingId: string, newTitle: string) => {
        try {
            await api.renameMeeting(meetingId, newTitle);
            // Update local state
            if (selectedMeeting?.id === meetingId) {
                setSelectedMeeting(prev => prev ? { ...prev, title: newTitle } : prev);
            }
            fetchMeetings();
            toast.success(`已更名為「${newTitle}」`);
        } catch (err) {
            console.error('Rename failed:', err);
            toast.error('修改名稱失敗');
        }
    };

    // 2026-05-24 (request #1) 批次刪除執行：與單筆 delete 同樣的 optimistic
    // local splice 模式，但用 api.bulkDeleteMeetings 一次 API call。
    const executeBulkDelete = async (meetingIds: string[]) => {
        if (meetingIds.length === 0) return;
        setIsBulkDeleting(true);
        try {
            const result = await api.bulkDeleteMeetings(
                meetingIds,
                session?.user?.email ?? undefined,
            );
            // optimistic：把已刪 ID 從 list 拿掉
            const deletedSet = new Set(
                meetingIds.filter(id => !result.not_found.includes(id))
            );
            // 直接 refetch 以取得後端最新狀態（含 audit log timestamps 等）
            await fetchMeetings();
            const msg = result.not_found.length > 0
                ? `已刪除 ${result.deleted} 筆會議（${result.not_found.length} 筆找不到）`
                : `已刪除 ${result.deleted} 筆會議`;
            toast.success(msg, {
                description: result.skipped_already_deleted > 0
                    ? `${result.skipped_already_deleted} 筆已是刪除狀態，跳過。資料保留 30 天供 IT 還原。`
                    : '資料保留 30 天供 IT 還原。',
                duration: 5000,
            });
            // 不必手動清 selectedIds，DashboardView 重新 render 時若 meeting 不在
            // 已自動消失（hook 只在 selectedIds 用 setSelectedIdsState 改變）
            return deletedSet;
        } catch (err) {
            console.error('Bulk delete failed:', err);
            toast.error('批次刪除失敗，請稍候再試', {
                description: err instanceof Error ? err.message : undefined,
                duration: 8000,
            });
        } finally {
            setIsBulkDeleting(false);
        }
    };

    const handleDeleteMeeting = (meetingId: string) => {
        // PR19: 取代 useMeetings 內已移除的 confirm()，改 ConfirmDialog
        setPendingDelete({ meetingId });
    };

    const executeDeleteMeeting = async (meetingId: string) => {
        // 2026-05-12 UX 優化（方案 C）：
        //   先 navigate 回 dashboard，再背景 await delete API。
        //   感知延遲 ~2-3s → ~0ms（dialog 關閉、立即返回列表）。
        //   失敗時 toast.error 會跳出，且該 meeting 仍會被 fetchMeetings
        //   重新載入時帶回來（因為背景刪除已失敗，後端仍有資料）。
        //
        // 2026-05-12 UX (feedback 617bb614)：刪除失敗 toast 加「立即回報」action，
        // 點下去直接開 FeedbackModal 並帶 meeting_id 給 IT 追查。
        handleBackToDashboard();
        const success = await deleteMeeting(meetingId, (failedMeetingId) => {
            setFeedbackContext({ meetingId: failedMeetingId });
        });
        if (!success) {
            // 刪除失敗 → 重抓 list 確保畫面與後端一致
            fetchMeetings();
        }
    };

    const handleRecovery = async (key: string) => {
        setIsRecovering(true);
        try {
            const blob = await get(key);
            if (blob) {
                const meetingId = key.replace('meeting_audio_', '');
                toast.info('開始恢復音檔上傳，請稍候...');
                const file = new File([blob], 'audio.webm', { type: blob.type || 'audio/webm' });
                try {
                    const { uploadUrl } = await api.getUploadUrl(meetingId, 'audio.webm', blob.type || 'audio/webm');
                    await api.uploadToGcs(uploadUrl, file);
                } catch (directErr) {
                    console.warn('[MeetChi] Recovery direct upload failed, using chunked:', directErr);
                    await api.chunkedUpload(meetingId, file);
                }
                await api.regenerateSummary(meetingId, 'general');
                await del(key);
                showSuccess('音檔恢復成功！預計幾分鐘後產出總結摘要。');
                checkOrphanedBackups();
                fetchMeetings();
            }
        } catch (e) {
            console.error('Recovery failed:', e);
            setError('恢復上傳失敗，請稍後重試。');
        } finally {
            setIsRecovering(false);
        }
    };

    const handleDiscardBackup = (key: string) => {
        // PR19: 改用 ConfirmDialog 取代瀏覽器原生 confirm()
        setPendingDiscard({ key });
    };

    const executeDiscardBackup = async (key: string) => {
        await del(key);
        checkOrphanedBackups();
        toast.success('未完成音檔已清除');
    };

    const handleTabChange = (tab: string) => {
        if (tab === 'settings') {
            setCurrentView('settings');
            window.history.pushState(null, '', '/dashboard?view=settings');
        } else if (tab === 'templates') {
            setCurrentView('templates');
            window.history.pushState(null, '', '/dashboard?view=templates');
        } else if (tab === 'admin') {
            setCurrentView('admin');
            window.history.pushState(null, '', '/dashboard?view=admin');
        } else if (tab === 'rag') {
            setCurrentView('rag');
            window.history.pushState(null, '', '/dashboard?view=rag');
        } else {
            handleBackToDashboard();
        }
    };

    // 2026-05-12 (feedback)：上傳中全屏 overlay
    //   - 解使用者反映「上傳數位時代時前端沒顯示提醒，誤重整取消整個流程」
    //   - 含 % 進度條（XHR upload.onprogress）+ 「請勿關閉/重整」警告
    //   - 'uploading' 階段：PUT 到 GCS，顯示進度
    //   - 'processing' 階段：提示 AI 處理中
    //   - 'error' 階段：重試/取消按鈕
    //   - 配合 beforeunload handler 雙重保護
    const uploadingOverlay =
        uploadState === 'uploading' ? (
            <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-sm flex items-center justify-center p-6" role="status" aria-live="polite">
                <div className="bg-card rounded-2xl shadow-2xl border border-border max-w-md w-full p-6 text-center">
                    <Loader2 className="w-12 h-12 text-brand-cta animate-spin mx-auto mb-4" />
                    <h2 className="text-xl font-bold text-foreground mb-1">
                        {batchProgress
                            ? `批次上傳中（${batchProgress.current} / ${batchProgress.total}）`
                            : '音檔上傳中'}
                    </h2>
                    <p className="text-sm text-muted-foreground mb-4">
                        請<strong className="text-status-error">勿關閉視窗或重新整理</strong>，否則整個上傳會中斷。
                        {batchProgress && batchProgress.total > 1 && (
                            <span className="block text-xs mt-1 opacity-80">
                                目前處理第 {batchProgress.current} 個檔案；剩餘 {batchProgress.total - batchProgress.current} 個排隊中。
                            </span>
                        )}
                    </p>
                    {uploadFileName && (
                        <p className="text-xs font-mono text-muted-foreground/80 mb-3 break-all">
                            {uploadFileName}
                            {uploadFileSize > 0 && (
                                <span className="ml-2 opacity-70">
                                    ({(uploadFileSize / 1024 / 1024).toFixed(1)} MB)
                                </span>
                            )}
                        </p>
                    )}
                    {/* Progress bar */}
                    <div className="w-full bg-muted rounded-full h-3 overflow-hidden mb-2">
                        <div
                            className="bg-brand-cta h-full transition-all duration-300 ease-out"
                            style={{ width: `${uploadProgress}%` }}
                        />
                    </div>
                    <p className="text-sm font-semibold text-brand-cta tabular-nums">
                        {uploadProgress}%
                    </p>
                    <p className="text-xs text-muted-foreground/70 mt-4">
                        傳輸完成後會自動開始 AI 處理，可安心去做其他事。
                    </p>
                </div>
            </div>
        ) : uploadState === 'error' ? (
            <div className="fixed inset-0 z-[200] bg-black/50 backdrop-blur-sm flex items-center justify-center p-6" role="alert" aria-live="assertive">
                <div className="bg-card rounded-2xl shadow-2xl border border-status-error/30 max-w-md w-full p-6 text-center">
                    <div className="w-12 h-12 rounded-full bg-status-error/10 flex items-center justify-center mx-auto mb-4">
                        <AlertCircle className="w-6 h-6 text-status-error" />
                    </div>
                    <h2 className="text-xl font-bold text-foreground mb-1">上傳失敗</h2>
                    <p className="text-sm text-muted-foreground mb-4">
                        {error || '音檔上傳過程發生錯誤，請檢查網路連線後重試。'}
                    </p>
                    <div className="flex items-center justify-center gap-3">
                        <button
                            onClick={() => { resetUploadState(); setError(null); }}
                            className="px-4 py-2 text-sm font-medium text-muted-foreground bg-muted hover:bg-muted/80 rounded-lg transition-colors"
                        >
                            取消
                        </button>
                        <button
                            onClick={() => { resetUploadState(); setError(null); triggerFileInput(); }}
                            className="px-4 py-2 text-sm font-medium text-white bg-brand-cta hover:bg-brand-cta/90 rounded-lg transition-colors shadow-sm"
                        >
                            重新上傳
                        </button>
                    </div>
                </div>
            </div>
        ) : null;

    return (
        <div className="flex h-screen bg-surface font-sans text-foreground overflow-hidden relative">
            {uploadingOverlay}
            {/* Upload Queue Tray (Google Drive-style, bottom-right) */}
            <UploadTray
                tasks={uploadQueue.tasks}
                isOpen={uploadQueue.isTrayOpen}
                onToggle={() => uploadQueue.setIsTrayOpen(v => !v)}
                onRetry={uploadQueue.retryTask}
                onRemove={uploadQueue.removeTask}
                onCancel={uploadQueue.cancelTask}
                onClearCompleted={uploadQueue.clearCompleted}
            />
            {/* State-driven confirm dialog (replaces window.confirm) */}
            <ConfirmDialog
                open={!!confirmState}
                title={confirmState?.title || ''}
                description={confirmState?.description}
                variant={confirmState?.variant || 'primary'}
                onConfirm={() => { confirmState?.resolve(true); setConfirmState(null); }}
                onCancel={() => { confirmState?.resolve(false); setConfirmState(null); }}
            />
            {/* FAB removed — ChiMemo accessible via sidebar only (UX audit V2: 單一入口原則) */}
            
            <RagDrawer
                isOpen={isRagSidebarOpen}
                onClose={() => setIsRagSidebarOpen(false)}
                onExpand={() => {
                    setIsRagSidebarOpen(false);
                    setCurrentView('rag');
                }}
            />
            {currentView !== 'record' && (
                <Sidebar
                    activeTab={currentView === 'detail' ? 'dashboard' : currentView}
                    setActiveTab={handleTabChange}
                    isMobileOpen={isMobileMenuOpen}
                    setIsMobileOpen={setIsMobileMenuOpen}
                    isConnected={isConnected}
                    isAdmin={isAdmin}
                    user={session?.user}
                    provider={(session as { provider?: string } | null)?.provider}
                    onOpenFeedback={() => setFeedbackContext({})}
                    onStartTour={() => { setCurrentView('dashboard'); setTimeout(() => setTourOpen(true), 100); }}
                />
            )}

            <main className="flex-1 flex flex-col relative overflow-hidden">
                <UATBanner />
                <TourOverlay open={tourOpen} onClose={() => setTourOpen(false)} />
                {pendingUploadFiles && pendingUploadFiles.length > 0 && (
                    <UploadSettingsModal
                        files={pendingUploadFiles}
                        availableTemplates={availableTemplates}
                        initial={{
                            templateName: uploadTemplateName,
                            language: uploadLanguage,
                            context: uploadContext,
                            isConfidential: uploadConfidential,
                        }}
                        onConfirm={confirmUpload}
                        onCancel={() => setPendingUploadFiles(null)}
                    />
                )}
                {currentView !== 'record' && (
                    <div className="md:hidden bg-background border-b border-border p-4 flex items-center justify-between z-20">
                        <div className="flex items-center gap-2">
                            <div className="w-6 h-6 bg-brand-cta rounded flex items-center justify-center">
                                <span className="font-bold text-white text-xs">M</span>
                            </div>
                            <span className="font-bold">MeetChi</span>
                        </div>
                        <div className="flex items-center gap-4">
                            <button onClick={() => setIsRagSidebarOpen(true)} className="text-brand-cta">
                                <MessageSquare size={20} />
                            </button>
                            <button onClick={() => setIsMobileMenuOpen(true)}>
                                <Menu className="text-muted-foreground" />
                            </button>
                        </div>
                    </div>
                )}

                <div className="flex-1 overflow-auto bg-surface">
                    {currentView === 'dashboard' && (
                        <>
                            {/* 2026-05-25 (Y6)：multiple 支援批次上傳 */}
                            <input
                                type="file"
                                accept="audio/*,video/*"
                                multiple
                                className="hidden"
                                ref={fileInputRef}
                                onChange={handleFileUpload}
                            />
                            
                            {/* Crash Recovery UI — DDG token：用 status-warning 而不是 raw amber */}
                            {orphanedBackups.length > 0 && (
                                <div className="mx-6 mt-6 mb-2 bg-status-warning/10 border border-status-warning/30 rounded-xl p-4 shadow-sm">
                                    <div className="flex items-start gap-4">
                                        <div className="w-10 h-10 bg-status-warning/20 rounded-full flex items-center justify-center flex-shrink-0 text-status-warning">
                                            <AlertTriangle size={24} />
                                        </div>
                                        <div className="flex-1">
                                            <h3 className="text-foreground font-bold text-lg">發現未完成的錄音檔</h3>
                                            <p className="text-muted-foreground text-sm mt-1">
                                                您的裝置上保留了以防中斷而暫存的會議音檔（共 {orphanedBackups.length} 筆）。您可以嘗試手動重傳，或將其放棄。
                                            </p>
                                            <div className="mt-4 flex flex-col gap-3">
                                                {orphanedBackups.map(key => (
                                                    <div key={key} className="flex items-center gap-3 bg-card rounded-lg p-3 border border-border">
                                                        <UploadCloud size={16} className="text-status-warning" />
                                                        <span className="text-sm font-medium text-foreground flex-1 truncate">{key.replace('meeting_audio_', '')}</span>
                                                        <button
                                                            onClick={() => handleRecovery(key)}
                                                            disabled={isRecovering}
                                                            className="px-3 py-1.5 text-xs font-semibold bg-status-warning text-white rounded hover:bg-status-warning/90 transition"
                                                        >
                                                            {isRecovering ? '恢復中...' : '恢復並上傳'}
                                                        </button>
                                                        <button
                                                            onClick={() => handleDiscardBackup(key)}
                                                            disabled={isRecovering}
                                                            className="px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:bg-muted rounded transition"
                                                        >
                                                            放棄
                                                        </button>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            <DashboardView
                                meetings={meetings}
                                isLoading={isLoading}
                                isUploading={isUploading}
                                uploadState={uploadState}
                                error={error}
                                successMessage={successMessage}
                                onSelectMeeting={handleViewDetail}
                                onCreateMeeting={handleStartRecord}
                                onUploadClick={triggerFileInput}
                                onRefresh={fetchMeetings}
                                availableTemplates={availableTemplates}
                                selectedTemplateName={uploadTemplateName}
                                onTemplateChange={setUploadTemplateName}
                                uploadContext={uploadContext}
                                onUploadContextChange={setUploadContext}
                                uploadConfidential={uploadConfidential}
                                onUploadConfidentialChange={setUploadConfidential}
                                uploadLanguage={uploadLanguage}
                                onUploadLanguageChange={setUploadLanguage}
                                onBulkDelete={(ids) => setPendingBulkDelete({ meetingIds: ids })}
                                onRename={handleRenameMeeting}
                                onServerFilter={fetchMeetingsWithFilter}
                            />
                        </>
                    )}

                    {currentView === 'rag' && (
                        <div className="h-full relative">
                            {/* Desktop top-right assistant button toggle when in specific views but RagWorkspace itself is the full view so maybe no toggle needed here */}
                            <RagWorkspace onBack={handleBackToDashboard} />
                        </div>
                    )}

                    {currentView === 'record' && (
                        <RecordingView
                            meetingId={recordingMeetingId}
                            meetingTitle={recordingTitle}
                            onBack={handleBackToDashboard}
                            onFinish={async (mid) => {
                                await fetchMeetings();
                                const freshMeetings = await api.listMeetings(0, 100, session?.user?.email || undefined);
                                const target = freshMeetings.find(m => m.id === mid);
                                if (target) {
                                    handleViewDetail(transformMeeting(target));
                                } else {
                                    handleBackToDashboard();
                                }
                            }}
                        />
                    )}

                    {currentView === 'detail' && (
                        <DetailView
                            meeting={selectedMeeting}
                            onBack={handleBackToDashboard}
                            onRegenerateSummary={handleRegenerateSummary}
                            onRegenerateTranscript={handleRegenerateTranscript}
                            isRegenerating={isRegenerating}
                            onDelete={handleDeleteMeeting}
                            isDeleting={false}
                            onRename={handleRenameMeeting}
                            onReportThisMeeting={(meetingId) => setFeedbackContext({ meetingId })}
                        />
                    )}

                    {currentView === 'settings' && (
                        <SettingsView
                            onBack={handleBackToDashboard}
                            isConnected={isConnected}
                            isLoadingConnection={isLoading}
                            userEmail={session?.user?.email || undefined}
                        />
                    )}

                    {currentView === 'templates' && (
                        <TemplateGallery onBack={handleBackToDashboard} />
                    )}

                    {currentView === 'admin' && (
                        <div className="overflow-auto">
                            {/* Ops Admin Panel (system operations dashboard) */}
                            <OpsAdminPanel userRole={userRole} />

                            {/* Admin Feedback Panel */}
                            <div className="p-6 md:p-8 max-w-7xl mx-auto">
                                <div className="bg-card rounded-xl border border-border p-6">
                                    <AdminFeedbackPanel userUpn={session?.user?.email || ''} />
                                </div>
                            </div>
                        </div>
                    )}
                </div>
                
                {/* Global Processing Queue Indicator — only show during active uploads or regeneration */}
                {(uploadState === 'uploading' || Object.values(isRegenerating).filter(Boolean).length > 0) && (
                    <div className="fixed bottom-6 right-6 z-50 animate-in slide-in-from-bottom-5">
                        <div className="bg-white/95 backdrop-blur-md shadow-xl border border-brand-cta/20 rounded-full px-4 py-2.5 flex items-center gap-3 cursor-pointer hover:bg-brand-cta/5 transition-colors"
                             title={uploadState === 'uploading' ? '有音檔正在上傳' : 'AI 正在背景處理會議摘要'}>
                            <div className="relative flex items-center justify-center">
                                <Loader2 size={18} className="text-brand-cta animate-spin" />
                            </div>
                            <span className="text-sm font-bold text-slate-700 pr-1">
                                處理中佇列 ({
                                    (uploadState === 'uploading' ? 1 : 0) + 
                                    Object.values(isRegenerating).filter(Boolean).length
                                })
                            </span>
                        </div>
                    </div>
                )}
            </main>

            {/* PR19: ConfirmDialog 取代瀏覽器原生 confirm() */}
            <ConfirmDialog
                open={!!pendingDelete}
                title="確定要刪除這個會議記錄嗎？"
                description="此操作將移除音檔、逐字稿與摘要。資料保留 30 天供 IT 還原，期間可與 IT 聯絡恢復。"
                confirmText="刪除"
                cancelText="取消"
                variant="destructive"
                onConfirm={async () => {
                    if (pendingDelete) {
                        await executeDeleteMeeting(pendingDelete.meetingId);
                        setPendingDelete(null);
                    }
                }}
                onCancel={() => setPendingDelete(null)}
            />

            <ConfirmDialog
                open={!!pendingDiscard}
                title="確定要放棄此未完成的音檔嗎？"
                description="清除後將永久刪除尚未上傳的本機備份，無法復原。"
                confirmText="放棄音檔"
                cancelText="保留"
                variant="destructive"
                onConfirm={async () => {
                    if (pendingDiscard) {
                        await executeDiscardBackup(pendingDiscard.key);
                        setPendingDiscard(null);
                    }
                }}
                onCancel={() => setPendingDiscard(null)}
            />

            {/* 2026-05-24 (request #1)：拖曳框選後批次刪除確認 */}
            <ConfirmDialog
                open={!!pendingBulkDelete}
                title={`確定要刪除 ${pendingBulkDelete?.meetingIds.length ?? 0} 筆會議記錄嗎？`}
                description={
                    `此操作將同時移除這些會議的音檔、逐字稿與摘要。` +
                    `\n資料保留 30 天供 IT 還原，期間請與 IT 聯絡可恢復。`
                }
                confirmText={isBulkDeleting ? '刪除中…' : `刪除 ${pendingBulkDelete?.meetingIds.length ?? 0} 筆`}
                cancelText="取消"
                variant="destructive"
                onConfirm={async () => {
                    if (pendingBulkDelete) {
                        await executeBulkDelete(pendingBulkDelete.meetingIds);
                        setPendingBulkDelete(null);
                    }
                }}
                onCancel={() => setPendingBulkDelete(null)}
            />

            {/* 2026-05-11: 全域 FeedbackModal — Sidebar 點開: 無 meeting context；
                DetailView 「回報這個會議」: 自動帶 meeting_id 讓 IT 精準 debug */}
            <FeedbackModal
                isOpen={feedbackContext !== null}
                onClose={() => setFeedbackContext(null)}
                userUpn={session?.user?.email || 'anonymous@meetchi.test'}
                meetingId={feedbackContext?.meetingId}
            />
        </div>
    );
}
