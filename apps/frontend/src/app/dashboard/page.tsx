"use client";

import React, { useEffect } from 'react';
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
} from 'lucide-react';
import { api } from '@/lib/api';
import type { Meeting } from '@/types/meeting';
import { transformMeeting } from '@/lib/transform';
import { Sidebar } from '@/components/Sidebar';
import { DashboardView } from '@/components/DashboardView';
import { DetailView } from '@/components/DetailView';
import { RecordingView } from '@/components/RecordingView';
import { SettingsView } from '@/components/SettingsView';
import { useMeetings } from '@/hooks/useMeetings';
import { useRecording } from '@/hooks/useRecording';
import { useSummary } from '@/hooks/useSummary';
import { useState } from 'react';

// --- Main App Component ---
export default function DashboardPage() {
    const { data: session } = useSession();
    const [currentView, setCurrentView] = useState<'dashboard' | 'record' | 'detail' | 'settings' | 'templates' | 'admin'>('dashboard');
    const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    // Custom hooks
    const {
        meetings, isLoading, error, setError, isConnected,
        successMessage, fetchMeetings, showSuccess, deleteMeeting,
    } = useMeetings();

    const {
        recordingMeetingId, recordingTitle, isUploading,
        fileInputRef, startRecording, triggerFileInput, uploadFile,
    } = useRecording();

    const { isRegenerating, regenerateSummary } = useSummary(fetchMeetings);

    // Sync session token with API client
    useEffect(() => {
        if (session?.idToken) {
            api.setToken(session.idToken);
        } else {
            api.setToken(null);
        }
    }, [session?.idToken]);

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

        await uploadFile(
            file,
            (fileName) => {
                showSuccess(`上傳成功！檔案「${fileName}」已開始處理。`);
                fetchMeetings();
            },
            (msg) => setError(msg),
        );
    };

    const handleViewDetail = (meeting: Meeting) => {
        setSelectedMeeting(meeting);
        setCurrentView('detail');
    };

    const handleRegenerateSummary = async (meetingId: string) => {
        try {
            await regenerateSummary(meetingId, selectedMeeting, setSelectedMeeting);
        } catch (err) {
            console.error('Failed to regenerate summary:', err);
            setError(err instanceof Error ? err.message : '重新生成摘要失敗');
        }
    };

    const handleBackToDashboard = () => {
        setSelectedMeeting(null);
        setCurrentView('dashboard');
    };

    const handleDeleteMeeting = async (meetingId: string) => {
        const success = await deleteMeeting(meetingId);
        if (success) handleBackToDashboard();
    };

    const handleTabChange = (tab: string) => {
        if (tab === 'record') {
            handleStartRecord();
        } else if (tab === 'settings') {
            setCurrentView('settings');
        } else if (tab === 'templates') {
            setCurrentView('templates');
        } else if (tab === 'admin') {
            setCurrentView('admin');
        } else {
            handleBackToDashboard();
        }
    };

    return (
        <div className="flex h-screen bg-surface font-sans text-foreground overflow-hidden">
            {currentView !== 'record' && (
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
                {currentView !== 'record' && (
                    <div className="md:hidden bg-background border-b border-border p-4 flex items-center justify-between z-20">
                        <div className="flex items-center gap-2">
                            <div className="w-6 h-6 bg-brand-cta rounded flex items-center justify-center">
                                <span className="font-bold text-white text-xs">M</span>
                            </div>
                            <span className="font-bold">MeetChi</span>
                        </div>
                        <button onClick={() => setIsMobileMenuOpen(true)}>
                            <Menu className="text-muted-foreground" />
                        </button>
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
                            <DashboardView
                                meetings={meetings}
                                isLoading={isLoading}
                                isUploading={isUploading}
                                error={error}
                                successMessage={successMessage}
                                onSelectMeeting={handleViewDetail}
                                onCreateMeeting={handleStartRecord}
                                onUploadClick={triggerFileInput}
                                onRefresh={fetchMeetings}
                            />
                        </>
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
                        <div className="p-6 md:p-8 max-w-5xl mx-auto overflow-auto">
                            <div className="mb-8">
                                <h1 className="text-2xl font-bold text-foreground mb-2">模板管理</h1>
                                <p className="text-muted-foreground">選擇適合會議類型的摘要模板（生成摘要時可指定）</p>
                            </div>

                            <div className="bg-status-warning/10 border border-status-warning/30 rounded-xl p-4 mb-6 flex items-start gap-3">
                                <AlertCircle className="text-status-warning flex-shrink-0 mt-0.5" size={20} />
                                <div>
                                    <p className="font-medium text-status-warning">模板管理功能開發中</p>
                                    <p className="text-sm text-status-warning/70 mt-1">以下是後端已支援的模板。自訂模板 CRUD 功能尚未開放。</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {[
                                    { name: 'general', label: '一般會議', desc: '通用模板，含摘要、待辦、決議', color: 'brand-cta', icon: FileText, tags: ['摘要', '待辦事項', '決議'] },
                                    { name: 'sales_bant', label: '業務會議 (BANT)', desc: 'Budget / Authority / Need / Timeline', color: 'status-warning', icon: Clock, tags: ['預算', '決策者', '需求', '時程'] },
                                    { name: 'hr_star', label: '面試評估 (STAR)', desc: 'Situation / Task / Action / Result', color: 'status-success', icon: CheckCircle2, tags: ['情境', '任務', '行動', '結果'] },
                                    { name: 'rd', label: '研發會議', desc: '技術決策與進度追蹤', color: 'brand-accent', icon: Mic, tags: ['技術決策', '進度', '風險'] },
                                ].map(tpl => (
                                    <div key={tpl.name} className="bg-card rounded-xl border border-border p-6 transition-all">
                                        <div className="flex items-start gap-4">
                                            <div className={`w-12 h-12 bg-${tpl.color}/15 rounded-xl flex items-center justify-center text-${tpl.color}`}>
                                                <tpl.icon size={24} />
                                            </div>
                                            <div className="flex-1">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <h3 className="font-semibold text-foreground">{tpl.label}</h3>
                                                    {tpl.name === 'general' && <span className="px-2 py-0.5 text-xs bg-brand-cta/15 text-brand-cta rounded-full">預設</span>}
                                                </div>
                                                <p className="text-sm text-muted-foreground mb-3">{tpl.desc}</p>
                                                <div className="flex flex-wrap gap-2">
                                                    {tpl.tags.map(tag => (
                                                        <span key={tag} className="px-2 py-1 text-xs bg-muted text-muted-foreground rounded">{tag}</span>
                                                    ))}
                                                </div>
                                                <p className="text-xs text-muted-foreground/50 mt-3 font-mono">template_name: &quot;{tpl.name}&quot;</p>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
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
            </main>
        </div>
    );
}
