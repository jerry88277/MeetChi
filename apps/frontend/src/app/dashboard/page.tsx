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
import { DashboardView } from '@/components/DashboardView';
import { DetailView } from '@/components/DetailView';
import { RecordingView } from '@/components/RecordingView';
import { SettingsView } from '@/components/SettingsView';
import { TemplateGallery } from '@/components/TemplateGallery';
import { RagWorkspace } from '@/components/rag/RagWorkspace';
import { RagDrawer } from '@/components/rag/RagDrawer';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useMeetings } from '@/hooks/useMeetings';
import { useRecording } from '@/hooks/useRecording';
import { useSummary } from '@/hooks/useSummary';
import { useMeetingPolling } from '@/hooks/useMeetingPolling';
import { installConsoleErrorHook } from '@/lib/feedback-metadata';
import { useState } from 'react';
import { toast } from 'sonner';

// --- Main App Component ---
export default function DashboardPage() {
    const { data: session } = useSession();
    const [currentView, setCurrentView] = useState<'dashboard' | 'record' | 'detail' | 'settings' | 'templates' | 'admin' | 'rag'>('dashboard');
    const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    const [isRagSidebarOpen, setIsRagSidebarOpen] = useState(false);

    // Custom hooks
    const {
        meetings, isLoading, error, setError, isConnected,
        successMessage, fetchMeetings, showSuccess, deleteMeeting,
    } = useMeetings();

    const {
        recordingMeetingId, recordingTitle, isUploading, uploadState,
        lastUploadedMeetingId, fileInputRef, startRecording, triggerFileInput,
        uploadFile, resetUploadState,
    } = useRecording();

    // Phase C: Upload template & context selection
    const [uploadTemplateName, setUploadTemplateName] = useState('general');
    const [uploadContext, setUploadContext] = useState('');
    const [availableTemplates, setAvailableTemplates] = useState<import('@/lib/api').TemplateDTO[]>([]);

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

    // Phase 9.1: Polling hook — watches lastUploadedMeetingId
    // Root fix: enabled driven by ACTUAL meeting data state, not just UI state
    const hasProcessingMeeting = meetings.some(
        m => m.status === 'processing' || m.status === 'pending'
    );

    const handlePollingStatusChange = useCallback(async (completedMeeting: { id: string; title?: string | null }) => {
        await fetchMeetings();
        resetUploadState();
        // PR19: 帶「查看」action 讓 user 可一鍵跳到 detail
        const completedId = completedMeeting?.id;
        toast.success('會議摘要已生成完成！', {
            description: completedId ? '點選「查看」即可進入詳情頁。' : undefined,
            action: completedId
                ? {
                      label: '查看',
                      onClick: () => {
                          const m = meetings.find((x) => x.id === completedId);
                          if (m) {
                              setSelectedMeeting(m);
                              setCurrentView('detail');
                          }
                      },
                  }
                : undefined,
        });
    }, [fetchMeetings, resetUploadState, meetings]);

    useMeetingPolling(
        lastUploadedMeetingId,
        hasProcessingMeeting || uploadState === 'processing',
        handlePollingStatusChange,
    );

    const { isRegenerating, regenerateSummary, regenerateTranscript } = useSummary(fetchMeetings);

    // Sync session token with API client
    useEffect(() => {
        if (session?.idToken) {
            api.setToken(session.idToken);
        } else {
            api.setToken(null);
        }
    }, [session?.idToken]);

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

    // D3-2: Smart Interval Safety Net (v15)
    // Only activates when there's a processing meeting but NO active single-meeting poll.
    // This handles: (1) page refresh losing lastUploadedMeetingId, (2) uploads from other devices.
    // When useMeetingPolling is active, this stays dormant to avoid double polling.
    const needsSafetyNet = hasProcessingMeeting && !lastUploadedMeetingId;
    useEffect(() => {
        if (!needsSafetyNet) return;

        // Immediate fetch on activation, then every 60s
        fetchMeetings();
        const id = setInterval(() => {
            if (!document.hidden) {
                fetchMeetings();
            }
        }, 60_000); // 60s interval — pure safety net, not primary mechanism

        return () => clearInterval(id);
    }, [needsSafetyNet, fetchMeetings]);

    // D3-3: selectedMeeting sync — update detail view when meetings list refreshes
    const prevMeetingsRef = useRef(meetings);
    useEffect(() => {
        if (prevMeetingsRef.current !== meetings && selectedMeeting) {
            const updated = meetings.find(m => m.id === selectedMeeting.id);
            if (updated && (
                updated.status !== selectedMeeting.status ||
                updated.summary !== selectedMeeting.summary ||
                updated.transcript !== selectedMeeting.transcript
            )) {
                setSelectedMeeting(updated);
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

    const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;
        event.target.value = '';

        const executeUpload = async (f: File) => {
            await uploadFile(
                f,
                (fileName) => {
                    showSuccess(`上傳成功！檔案「${fileName}」已開始處理。`);
                    fetchMeetings();
                },
                (msg) => setError(msg),
                uploadTemplateName,
                uploadContext,
            );
        };

        // Phase C.2: Audio duration prediction/warning
        if (file.type.startsWith('audio/') || file.type.startsWith('video/')) {
            const url = URL.createObjectURL(file);
            const media = new Audio(url);
            
            media.addEventListener('loadedmetadata', () => {
                URL.revokeObjectURL(url);
                const durationMinutes = media.duration / 60;
                
                // Warn if longer than 120 minutes
                if (durationMinutes > 120) {
                    if(!window.confirm(`警告：音檔長度約 ${Math.round(durationMinutes)} 分鐘。處理時間可能需要 20 分鐘以上，是否確定繼續上傳？`)) {
                        return;
                    }
                }
                executeUpload(file);
            });
            
            media.addEventListener('error', () => {
                // Ignore errors (unsupported formats by browser) and just upload
                URL.revokeObjectURL(url);
                executeUpload(file);
            });
        } else {
            // General files (like if someone tries uploading a supported but non-media file)
            executeUpload(file);
        }
    };

    const handleViewDetail = (meeting: Meeting) => {
        setSelectedMeeting(meeting);
        setCurrentView('detail');
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
    };

    const handleDeleteMeeting = (meetingId: string) => {
        // PR19: 取代 useMeetings 內已移除的 confirm()，改 ConfirmDialog
        setPendingDelete({ meetingId });
    };

    const executeDeleteMeeting = async (meetingId: string) => {
        const success = await deleteMeeting(meetingId);
        if (success) handleBackToDashboard();
    };

    const handleRecovery = async (key: string) => {
        setIsRecovering(true);
        try {
            const blob = await get(key);
            if (blob) {
                const meetingId = key.replace('meeting_audio_', '');
                toast.info('開始恢復音檔上傳，請稍候...');
                const file = new File([blob], 'audio.webm', { type: blob.type || 'audio/webm' });
                const { uploadUrl } = await api.getUploadUrl(meetingId, 'audio.webm', blob.type || 'audio/webm');
                await api.uploadToGcs(uploadUrl, file);
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
        } else if (tab === 'templates') {
            setCurrentView('templates');
        } else if (tab === 'admin') {
            setCurrentView('admin');
        } else if (tab === 'rag') {
            setCurrentView('rag');
        } else {
            handleBackToDashboard();
        }
    };

    return (
        <div className="flex h-screen bg-surface font-sans text-foreground overflow-hidden relative">
            {/* Global FAB for RagSidebar */}
            <button 
                onClick={() => setIsRagSidebarOpen(true)}
                className="fixed bottom-6 right-6 z-40 bg-[#0052cc] text-white p-4 rounded-full shadow-[0_8px_32px_rgba(0,82,204,0.3)] hover:scale-105 hover:bg-[#0040a2] transition-transform flex items-center justify-center group"
                title="召喚智能助理"
            >
                <MessageSquare className="w-6 h-6" />
                <span className="max-w-0 overflow-hidden whitespace-nowrap group-hover:max-w-xs group-hover:ml-3 transition-all duration-300 font-medium text-sm">
                    智能助理
                </span>
            </button>
            
            <RagDrawer
                isOpen={isRagSidebarOpen}
                onClose={() => setIsRagSidebarOpen(false)}
                onExpand={() => {
                    setIsRagSidebarOpen(false);
                    setCurrentView('rag');
                }}
            />
            {currentView !== 'record' && currentView !== 'rag' && (
                <Sidebar
                    activeTab={currentView === 'detail' ? 'dashboard' : currentView}
                    setActiveTab={handleTabChange}
                    isMobileOpen={isMobileMenuOpen}
                    setIsMobileOpen={setIsMobileMenuOpen}
                    isConnected={isConnected}
                    user={session?.user}
                />
            )}

            <main className="flex-1 flex flex-col relative overflow-hidden">
                {currentView !== 'record' && currentView !== 'rag' && (
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
                            <input
                                type="file"
                                accept="audio/*"
                                className="hidden"
                                ref={fileInputRef}
                                onChange={handleFileUpload}
                            />
                            
                            {/* Crash Recovery UI */}
                            {orphanedBackups.length > 0 && (
                                <div className="mx-6 mt-6 mb-2 bg-amber-50 border border-amber-200 rounded-xl p-4 shadow-sm">
                                    <div className="flex items-start gap-4">
                                        <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center flex-shrink-0 text-amber-600">
                                            <AlertTriangle size={24} />
                                        </div>
                                        <div className="flex-1">
                                            <h3 className="text-amber-800 font-bold text-lg">發現未完成的錄音檔</h3>
                                            <p className="text-amber-700 text-sm mt-1">
                                                您的裝置上保留了以防中斷而暫存的會議音檔（共 {orphanedBackups.length} 筆）。您可以嘗試手動重傳，或將其放棄。
                                            </p>
                                            <div className="mt-4 flex flex-col gap-3">
                                                {orphanedBackups.map(key => (
                                                    <div key={key} className="flex items-center gap-3 bg-white/50 rounded-lg p-3 border border-amber-200/50">
                                                        <UploadCloud size={16} className="text-amber-600" />
                                                        <span className="text-sm font-medium text-amber-800 flex-1 truncate">{key.replace('meeting_audio_', '')}</span>
                                                        <button 
                                                            onClick={() => handleRecovery(key)}
                                                            disabled={isRecovering}
                                                            className="px-3 py-1.5 text-xs font-semibold bg-amber-600 text-white rounded hover:bg-amber-700 transition"
                                                        >
                                                            {isRecovering ? '恢復中...' : '恢復並上傳'}
                                                        </button>
                                                        <button 
                                                            onClick={() => handleDiscardBackup(key)}
                                                            disabled={isRecovering}
                                                            className="px-3 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-100 rounded transition"
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
                                const freshMeetings = await api.listMeetings();
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
                        />
                    )}

                    {currentView === 'settings' && (
                        <SettingsView
                            onBack={handleBackToDashboard}
                            isConnected={isConnected}
                        />
                    )}

                    {currentView === 'templates' && (
                        <TemplateGallery onBack={handleBackToDashboard} />
                    )}

                    {currentView === 'admin' && (
                        <div className="p-6 md:p-8 max-w-5xl mx-auto overflow-auto">
                            <div className="mb-8">
                                <h1 className="text-2xl font-bold text-foreground mb-2">管理</h1>
                                <p className="text-muted-foreground">系統管理與用戶設定</p>
                            </div>

                            {/* User Profile Card */}
                            <div className="bg-card rounded-xl border border-border p-6 mb-6">
                                <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                                    <Shield size={20} className="text-brand-cta" />
                                    當前用戶
                                </h2>
                                <div className="flex items-center gap-4">
                                    {session?.user?.image ? (
                                        <img
                                            src={session.user.image}
                                            alt={session.user.name || 'User'}
                                            className="w-16 h-16 rounded-full"
                                        />
                                    ) : (
                                        <div className="w-16 h-16 rounded-full bg-gradient-to-br from-brand-cta to-brand-accent flex items-center justify-center text-white text-2xl font-bold">
                                            {session?.user?.name?.charAt(0) || '?'}
                                        </div>
                                    )}
                                    <div>
                                        <p className="text-lg font-medium text-foreground">{session?.user?.name || '未登入'}</p>
                                        <p className="text-muted-foreground">{session?.user?.email || '-'}</p>
                                        <span className="inline-flex items-center gap-1 mt-1 px-2 py-0.5 text-xs bg-brand-cta/15 text-brand-cta rounded-full">
                                            <Shield size={12} />
                                            管理員
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Stats Grid */}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                                <div className="bg-card rounded-xl border border-border p-5">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-brand-cta/15 rounded-lg flex items-center justify-center text-brand-cta">
                                            <FileText size={20} />
                                        </div>
                                        <div>
                                            <p className="text-2xl font-bold text-foreground">{meetings.length}</p>
                                            <p className="text-sm text-muted-foreground">會議記錄</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="bg-card rounded-xl border border-border p-5">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-status-success/15 rounded-lg flex items-center justify-center text-status-success">
                                            <CheckCircle2 size={20} />
                                        </div>
                                        <div>
                                            <p className="text-2xl font-bold text-foreground">{meetings.filter(m => m.status === 'completed').length}</p>
                                            <p className="text-sm text-muted-foreground">已完成摘要</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="bg-card rounded-xl border border-border p-5">
                                    <div className="flex items-center gap-3">
                                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${isConnected ? 'bg-status-success/15 text-status-success' : 'bg-status-error/15 text-status-error'}`}>
                                            {isConnected ? <Wifi size={20} /> : <WifiOff size={20} />}
                                        </div>
                                        <div>
                                            <p className="text-2xl font-bold text-foreground">{isConnected ? 'Online' : 'Offline'}</p>
                                            <p className="text-sm text-muted-foreground">後端狀態</p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Coming Soon */}
                            <div className="bg-card rounded-xl border border-border p-6">
                                <h2 className="text-lg font-semibold text-foreground mb-4">功能規劃</h2>
                                <div className="space-y-3">
                                    {[
                                        { icon: Shield, label: 'Entra ID 整合', desc: '企業 SSO 認證', color: 'status-warning' },
                                        { icon: Settings, label: '用戶管理', desc: '角色權限設定', color: 'brand-accent' },
                                        { icon: Calendar, label: '會議分析', desc: '統計報表、趨勢分析', color: 'brand-cta' },
                                    ].map((item, i) => (
                                        <div key={i} className="flex items-center gap-3 p-3 bg-muted rounded-lg">
                                            <div className={`w-8 h-8 bg-${item.color}/15 rounded-lg flex items-center justify-center text-${item.color}`}>
                                                <item.icon size={16} />
                                            </div>
                                            <div className="flex-1">
                                                <p className="font-medium text-foreground/80">{item.label}</p>
                                                <p className="text-xs text-muted-foreground">{item.desc}</p>
                                            </div>
                                            <span className={`px-2 py-1 text-xs bg-${item.color}/15 text-${item.color} rounded`}>規劃中</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
                
                {/* Global Processing Queue Indicator */}
                {(uploadState === 'uploading' || uploadState === 'processing' || Object.values(isRegenerating).filter(Boolean).length > 0) && (
                    <div className="fixed bottom-6 right-6 z-50 animate-in slide-in-from-bottom-5">
                        <div className="bg-white/95 backdrop-blur-md shadow-xl border border-brand-cta/20 rounded-full px-4 py-2.5 flex items-center gap-3 cursor-pointer hover:bg-brand-cta/5 transition-colors"
                             title={uploadState === 'uploading' ? '有音檔正在上傳' : 'AI 正在背景處理會議摘要'}>
                            <div className="relative flex items-center justify-center">
                                <Loader2 size={18} className="text-brand-cta animate-spin" />
                            </div>
                            <span className="text-sm font-bold text-slate-700 pr-1">
                                處理中佇列 ({
                                    (uploadState === 'uploading' || uploadState === 'processing' ? 1 : 0) + 
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
                description="此操作將同時移除音檔、逐字稿與摘要，且無法復原。"
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
        </div>
    );
}
