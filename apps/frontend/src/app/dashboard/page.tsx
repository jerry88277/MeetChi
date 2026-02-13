"use client";

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useSession, signOut } from 'next-auth/react';
import {
    Mic,
    Upload,
    Search,
    Clock,
    Calendar,
    ChevronRight,
    FileText,
    CheckCircle2,
    Settings,
    Menu,
    X,
    Loader2,
    AlertCircle,
    RefreshCw,
    Wifi,
    WifiOff,
    LogOut,
    Shield,
    LayoutTemplate,
    Trash2,
    Download,
    ChevronDown,
    Square,
    Volume2
} from 'lucide-react';
import { api, API_BASE_URL, Meeting as ApiMeeting, MeetingSummary } from '@/lib/api';

// --- Types ---
interface ActionItem {
    id: number;
    text: string;
    assignee: string;
    due: string;
}

interface TranscriptLine {
    time: string;
    speaker: string;
    text: string;
}

interface Meeting {
    id: string;
    title: string;
    date: string;
    createdAt: string;
    duration: string;
    status: "completed" | "processing" | "failed";
    summary: string;
    actionItems: ActionItem[];
    transcript: TranscriptLine[];
}

// Transform API meeting to UI format
function transformMeeting(apiMeeting: ApiMeeting): Meeting {
    // Parse summary JSON if available
    let summary = "";
    let actionItems: ActionItem[] = [];

    if (apiMeeting.summary_json) {
        try {
            const summaryData: MeetingSummary = JSON.parse(apiMeeting.summary_json);
            summary = summaryData.summary || "";
            actionItems = (summaryData.action_items || []).map((text, idx) => ({
                id: idx + 1,
                text,
                assignee: "待分配",
                due: "待定"
            }));
        } catch {
            summary = apiMeeting.summary_json;
        }
    }

    // Transform transcript segments
    const transcript: TranscriptLine[] = (apiMeeting.transcript_segments || []).map(seg => ({
        time: formatSeconds(seg.start_time),
        speaker: seg.speaker || "Unknown",
        text: seg.content_polished || seg.content_raw
    }));

    // Format duration
    const durationStr = apiMeeting.duration
        ? formatSeconds(apiMeeting.duration)
        : "00:00";

    return {
        id: apiMeeting.id,
        title: apiMeeting.title,
        date: new Date(apiMeeting.created_at).toISOString().split('T')[0],
        createdAt: apiMeeting.created_at,
        duration: durationStr,
        status: apiMeeting.status === "completed" ? "completed"
            : apiMeeting.status === "failed" ? "failed"
                : "processing",
        summary,
        actionItems,
        transcript
    };
}

function formatSeconds(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// --- Export Utilities ---
function downloadFile(content: string, filename: string, mimeType: string) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function exportAsTxt(meeting: Meeting) {
    let content = `${meeting.title}\n${'='.repeat(meeting.title.length)}\n`;
    content += `日期: ${meeting.date}  時長: ${meeting.duration}\n\n`;
    if (meeting.summary) {
        content += `【摘要】\n${meeting.summary}\n\n`;
    }
    if (meeting.actionItems.length > 0) {
        content += `【待辦事項】\n`;
        meeting.actionItems.forEach(item => {
            content += `- ${item.text} (${item.assignee}, Due: ${item.due})\n`;
        });
        content += '\n';
    }
    if (meeting.transcript.length > 0) {
        content += `【逐字稿】\n`;
        meeting.transcript.forEach(line => {
            content += `[${line.time}] ${line.speaker}: ${line.text}\n`;
        });
    }
    downloadFile(content, `${meeting.title}.txt`, 'text/plain;charset=utf-8');
}

function exportAsSrt(meeting: Meeting) {
    if (meeting.transcript.length === 0) return;
    let content = '';
    meeting.transcript.forEach((line, idx) => {
        const startTime = line.time.replace(/^(\d+):(\d+)$/, '00:$1:$2,000');
        content += `${idx + 1}\n`;
        content += `${startTime} --> ${startTime}\n`;
        content += `${line.speaker}: ${line.text}\n\n`;
    });
    downloadFile(content, `${meeting.title}.srt`, 'text/srt;charset=utf-8');
}

function exportAsJson(meeting: Meeting) {
    const data = {
        title: meeting.title,
        date: meeting.date,
        duration: meeting.duration,
        status: meeting.status,
        summary: meeting.summary,
        actionItems: meeting.actionItems,
        transcript: meeting.transcript
    };
    downloadFile(JSON.stringify(data, null, 2), `${meeting.title}.json`, 'application/json;charset=utf-8');
}

// --- Sidebar Component ---
interface SidebarProps {
    activeTab: string;
    setActiveTab: (tab: string) => void;
    isMobileOpen: boolean;
    setIsMobileOpen: (open: boolean) => void;
    isConnected: boolean;
    user?: {
        name?: string | null;
        email?: string | null;
        image?: string | null;
    };
}

const Sidebar = ({ activeTab, setActiveTab, isMobileOpen, setIsMobileOpen, isConnected, user }: SidebarProps) => {
    const menuItems = [
        { id: 'record', icon: Mic, label: '開始錄音', primary: true },
        { id: 'dashboard', icon: FileText, label: '所有會議' },
        { id: 'templates', icon: LayoutTemplate, label: '模板管理' },
        { id: 'admin', icon: Shield, label: '管理' },
        { id: 'settings', icon: Settings, label: '系統設定' },
    ];

    const sidebarClass = `fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-white transform transition-transform duration-300 ease-in-out ${isMobileOpen ? 'translate-x-0' : '-translate-x-full'
        } md:relative md:translate-x-0 flex flex-col`;

    return (
        <>
            {isMobileOpen && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-50 z-40 md:hidden"
                    onClick={() => setIsMobileOpen(false)}
                />
            )}

            <div className={sidebarClass}>
                <div className="p-6 border-b border-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 bg-indigo-500 rounded-lg flex items-center justify-center">
                            <span className="font-bold text-white">M</span>
                        </div>
                        <span className="text-xl font-bold tracking-tight">MeetChi</span>
                    </div>
                    <button onClick={() => setIsMobileOpen(false)} className="md:hidden text-slate-400">
                        <X size={24} />
                    </button>
                </div>

                <nav className="flex-1 p-4 space-y-2">
                    {menuItems.map((item) => (
                        <button
                            key={item.id}
                            onClick={() => {
                                setActiveTab(item.id);
                                setIsMobileOpen(false);
                            }}
                            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${item.primary
                                ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50'
                                : activeTab === item.id
                                    ? 'bg-slate-800 text-white'
                                    : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                                }`}
                        >
                            <item.icon size={20} />
                            <span className="font-medium">{item.label}</span>
                        </button>
                    ))}
                </nav>

                {/* User Profile Section */}
                {user && (
                    <div className="p-4 border-t border-slate-800">
                        <div className="flex items-center gap-3 mb-3">
                            {user.image ? (
                                <img
                                    src={user.image}
                                    alt={user.name || 'User'}
                                    className="w-10 h-10 rounded-full"
                                />
                            ) : (
                                <div className="w-10 h-10 rounded-full bg-indigo-500 flex items-center justify-center text-white font-medium">
                                    {user.name?.charAt(0) || user.email?.charAt(0) || '?'}
                                </div>
                            )}
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-white truncate">{user.name}</p>
                                <p className="text-xs text-slate-400 truncate">{user.email}</p>
                            </div>
                        </div>
                        <button
                            onClick={() => signOut({ callbackUrl: '/login' })}
                            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
                        >
                            <LogOut size={16} />
                            <span>登出</span>
                        </button>
                    </div>
                )}

                {/* Backend Status */}
                <div className="p-4 border-t border-slate-800">
                    <div className="bg-slate-800/50 rounded-xl p-4">
                        <p className="text-xs text-slate-400 mb-2">後端狀態</p>
                        <div className="flex items-center gap-2 mb-1">
                            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`}></div>
                            <span className="text-xs font-mono text-slate-300">
                                {isConnected ? '已連線' : '未連線'}
                            </span>
                        </div>
                        <p className="text-xs text-slate-500 truncate" title={API_BASE_URL}>
                            {API_BASE_URL.replace('https://', '').substring(0, 25)}...
                        </p>
                    </div>
                </div>
            </div>
        </>
    );
};

// --- Recording View Component ---
// 🎤 Real-time WebSocket recording + transcription
interface TranscriptEntry {
    id: string;
    type: 'partial' | 'raw' | 'polished';
    content: string;
    translated?: string;
}

interface RecordingViewProps {
    meetingId: string | null;
    meetingTitle: string;
    onBack: () => void;
    onFinish: (meetingId: string) => void;
}

const RecordingView = ({ meetingId, meetingTitle, onBack, onFinish }: RecordingViewProps) => {
    const [isRecording, setIsRecording] = useState(false);
    const [isPreparing, setIsPreparing] = useState(false);
    const [recordingTime, setRecordingTime] = useState(0);
    const [transcriptEntries, setTranscriptEntries] = useState<TranscriptEntry[]>([]);
    const [volumeLevel, setVolumeLevel] = useState(0);
    const [wsStatus, setWsStatus] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
    const [errorMsg, setErrorMsg] = useState<string | null>(null);
    const [backendReady, setBackendReady] = useState(false);

    const wsRef = useRef<WebSocket | null>(null);
    const audioContextRef = useRef<AudioContext | null>(null);
    const processorRef = useRef<ScriptProcessorNode | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const transcriptEndRef = useRef<HTMLDivElement>(null);

    // P0-C: Preheat — trigger Cloud Run cold start on component mount
    useEffect(() => {
        const preheat = async () => {
            try {
                await fetch(`${api.getBaseUrl()}/health`);
                setBackendReady(true);
            } catch {
                // Silent fail — cold start will happen on WS connect
            }
        };
        preheat();
    }, []);

    // Auto-scroll transcript
    useEffect(() => {
        transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [transcriptEntries]);

    // Format recording time
    const formatTime = (seconds: number) => {
        const m = Math.floor(seconds / 60).toString().padStart(2, '0');
        const s = (seconds % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
    };

    // Downsample audio from source rate to 16kHz
    const downsampleBuffer = (buffer: Float32Array, inputSampleRate: number, outputSampleRate: number): Int16Array => {
        if (inputSampleRate === outputSampleRate) {
            const result = new Int16Array(buffer.length);
            for (let i = 0; i < buffer.length; i++) {
                const s = Math.max(-1, Math.min(1, buffer[i]));
                result[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            return result;
        }
        const ratio = inputSampleRate / outputSampleRate;
        const newLength = Math.round(buffer.length / ratio);
        const result = new Int16Array(newLength);
        for (let i = 0; i < newLength; i++) {
            const index = Math.round(i * ratio);
            const s = Math.max(-1, Math.min(1, buffer[index]));
            result[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        return result;
    };

    const startRecording = async () => {
        if (!meetingId) {
            setErrorMsg('無法建立會議，請重試');
            return;
        }

        setIsPreparing(true);
        setErrorMsg(null);

        try {
            // 1. Get microphone
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: { ideal: 16000 },
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true,
                }
            });
            streamRef.current = stream;

            // 2. Setup AudioContext
            const audioContext = new AudioContext({ sampleRate: 16000 });
            audioContextRef.current = audioContext;
            const source = audioContext.createMediaStreamSource(stream);

            // 3. Setup ScriptProcessor for PCM extraction
            const processor = audioContext.createScriptProcessor(4096, 1, 1);
            processorRef.current = processor;

            // 4. Connect WebSocket
            const wsUrl = `${api.getWebSocketUrl()}/ws/transcribe`;
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;
            setWsStatus('connecting');
            console.log(`[MeetChi] WS connecting to: ${wsUrl}`);

            // ws.onopen is set below (after pendingChunks buffer setup)

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    // P0-B: Handle heartbeat ping/pong
                    if (msg.type === 'ping') {
                        ws.send(JSON.stringify({ type: 'pong' }));
                        return;
                    }
                    if (msg.type === 'pong') {
                        return; // Heartbeat response, ignore
                    }
                    setTranscriptEntries(prev => {
                        const newEntries = [...prev];
                        if (msg.type === 'partial') {
                            // Update or add partial
                            const idx = newEntries.findIndex(e => e.id === msg.id && e.type === 'partial');
                            if (idx >= 0) {
                                newEntries[idx] = { ...newEntries[idx], content: msg.content };
                            } else {
                                newEntries.push({ id: msg.id, type: 'partial', content: msg.content });
                            }
                        } else if (msg.type === 'raw') {
                            // Remove partial, add raw
                            const filtered = newEntries.filter(e => !(e.id === msg.id && e.type === 'partial'));
                            if (msg.content) {
                                filtered.push({ id: msg.id, type: 'raw', content: msg.content });
                            }
                            return filtered;
                        } else if (msg.type === 'polished') {
                            // Replace raw with polished
                            const idx = newEntries.findIndex(e => e.id === msg.id && (e.type === 'raw' || e.type === 'polished'));
                            if (idx >= 0) {
                                newEntries[idx] = { id: msg.id, type: 'polished', content: msg.content, translated: msg.translated };
                            } else {
                                newEntries.push({ id: msg.id, type: 'polished', content: msg.content, translated: msg.translated });
                            }
                        }
                        return newEntries;
                    });
                } catch (e) {
                    console.error('Failed to parse WS message:', e);
                }
            };

            ws.onerror = (ev) => {
                setWsStatus('error');
                setErrorMsg('WebSocket 連線錯誤');
                console.error(`[MeetChi] WS ERROR. Sent: ${chunksSent}, Buffered: ${chunksBuffered}`, ev);
            };

            ws.onclose = (ev) => {
                setWsStatus('disconnected');
                console.log(`[MeetChi] WS CLOSED. Code: ${ev.code}, Reason: ${ev.reason || 'none'}, Sent: ${chunksSent}, Buffered: ${chunksBuffered}`);
            };

            // 5. Process audio chunks
            // P1: Volume calculation is decoupled from WebSocket readiness
            // P2: Pre-connection buffer — queue chunks while WS is connecting
            const pendingChunks: ArrayBufferLike[] = [];
            let chunksSent = 0;
            let chunksBuffered = 0;

            ws.onopen = () => {
                setWsStatus('connected');
                console.log(`[MeetChi] WS OPEN. Flushing ${pendingChunks.length} buffered chunks.`);
                // Flush buffered audio chunks
                for (const chunk of pendingChunks) {
                    ws.send(chunk);
                    chunksSent++;
                }
                pendingChunks.length = 0; // Clear buffer
                // Send config after flush
                ws.send(JSON.stringify({
                    type: 'config',
                    meeting_id: meetingId,
                    source_lang: 'zh',
                    target_lang: 'en',
                    mode: 'transcription',
                    initial_prompt: '',
                }));
            };

            processor.onaudioprocess = (e) => {
                const inputData = e.inputBuffer.getChannelData(0);
                // Volume meter — always calculate, regardless of WS state
                let sum = 0;
                for (let i = 0; i < inputData.length; i++) {
                    sum += inputData[i] * inputData[i];
                }
                setVolumeLevel(Math.sqrt(sum / inputData.length));

                const pcmData = downsampleBuffer(inputData, audioContext.sampleRate, 16000);

                // Send PCM to WebSocket — buffer if not yet connected
                if (wsRef.current?.readyState === WebSocket.OPEN) {
                    wsRef.current.send(pcmData.buffer);
                    chunksSent++;
                } else if (wsRef.current?.readyState === WebSocket.CONNECTING) {
                    // Buffer chunks while WS is connecting (cold start, SSL handshake)
                    pendingChunks.push(pcmData.buffer.slice(0)); // Clone to prevent buffer reuse
                    chunksBuffered++;
                }
                // If CLOSING or CLOSED, drop silently (recording is ending)
            };

            source.connect(processor);
            processor.connect(audioContext.destination);

            // 6. Start timer — immediately (don't wait for WS)
            setRecordingTime(0);
            timerRef.current = setInterval(() => {
                setRecordingTime(t => t + 1);
            }, 1000);

            // P1: Set recording state immediately after audio setup (before WS connect)
            setIsRecording(true);
            setIsPreparing(false);

            // P0-B: Frontend-initiated heartbeat ping (every 25s)
            pingIntervalRef.current = setInterval(() => {
                if (wsRef.current?.readyState === WebSocket.OPEN) {
                    wsRef.current.send(JSON.stringify({ type: 'ping' }));
                }
            }, 25000);

        } catch (err) {
            setIsPreparing(false);
            if (err instanceof DOMException && err.name === 'NotAllowedError') {
                setErrorMsg('請允許麥克風權限後再試');
            } else {
                setErrorMsg(`錄音啟動失敗: ${err instanceof Error ? err.message : '未知錯誤'}`);
            }
        }
    };

    const stopRecording = async () => {
        // Stop heartbeat ping
        if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
        }

        // Stop timer
        if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }

        // Stop audio processing
        if (processorRef.current) {
            processorRef.current.disconnect();
            processorRef.current = null;
        }
        if (audioContextRef.current) {
            await audioContextRef.current.close();
            audioContextRef.current = null;
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(t => t.stop());
            streamRef.current = null;
        }

        // Close WebSocket (triggers backend WAV save)
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }

        setIsRecording(false);
        setVolumeLevel(0);

        // Trigger summary generation & navigate to detail
        if (meetingId) {
            try {
                await api.regenerateSummary(meetingId, 'general');
            } catch (e) {
                console.error('Failed to trigger summary:', e);
            }
            onFinish(meetingId);
        }
    };

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
            if (processorRef.current) processorRef.current.disconnect();
            if (audioContextRef.current) audioContextRef.current.close();
            if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
            if (wsRef.current) wsRef.current.close();
        };
    }, []);

    // Finalized entries only (raw or polished)
    const finalizedEntries = transcriptEntries.filter(e => e.type !== 'partial');
    const currentPartial = transcriptEntries.find(e => e.type === 'partial');

    return (
        <div className="h-full flex flex-col bg-white">
            {/* Header */}
            <div className="border-b border-slate-200 px-6 py-4 flex items-center gap-4 bg-white sticky top-0 z-10">
                <button onClick={() => { if (isRecording) { stopRecording(); } else { onBack(); } }}
                    className="p-2 hover:bg-slate-100 rounded-full text-slate-500 transition-colors">
                    <ChevronRight size={24} className="rotate-180" />
                </button>
                <div className="flex-1">
                    <h2 className="text-xl font-bold text-slate-900">{meetingTitle}</h2>
                    <div className="flex items-center gap-3 text-sm text-slate-500">
                        {isRecording && (
                            <>
                                <span className="flex items-center gap-1.5">
                                    <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                                    錄音中
                                </span>
                                <span className="w-1 h-1 rounded-full bg-slate-300" />
                                <span className="font-mono">{formatTime(recordingTime)}</span>
                            </>
                        )}
                        {wsStatus === 'connecting' && <span className="text-amber-500">連線中...</span>}
                        {wsStatus === 'error' && <span className="text-red-500">連線錯誤</span>}
                    </div>
                </div>
            </div>

            {/* Transcript Area */}
            <div className="flex-1 overflow-y-auto p-6 space-y-3">
                {!isRecording && transcriptEntries.length === 0 && (
                    <div className="flex flex-col items-center justify-center h-full text-center">
                        <div className="w-20 h-20 bg-indigo-50 rounded-full flex items-center justify-center mb-6">
                            <Mic size={40} className="text-indigo-400" />
                        </div>
                        <h3 className="text-lg font-semibold text-slate-700 mb-2">準備開始錄音</h3>
                        <p className="text-slate-500 max-w-sm">點擊下方按鈕開始錄音，系統將即時轉錄你的語音。</p>
                    </div>
                )}

                {errorMsg && (
                    <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-3">
                        <AlertCircle className="text-red-500 flex-shrink-0" size={20} />
                        <p className="text-red-800">{errorMsg}</p>
                    </div>
                )}

                {finalizedEntries.map(entry => (
                    <div key={entry.id} className="bg-slate-50 rounded-xl p-4">
                        <p className="text-slate-900 leading-relaxed">{entry.content}</p>
                        {entry.translated && (
                            <p className="text-slate-500 text-sm mt-1 italic">{entry.translated}</p>
                        )}
                    </div>
                ))}

                {currentPartial && (
                    <div className="bg-indigo-50/50 rounded-xl p-4 border border-indigo-100">
                        <p className="text-indigo-700/70 leading-relaxed">{currentPartial.content}</p>
                    </div>
                )}

                <div ref={transcriptEndRef} />
            </div>

            {/* Control Bar */}
            <div className="border-t border-slate-200 bg-white px-6 py-5">
                <div className="flex items-center justify-center gap-6">
                    {/* Volume Indicator */}
                    <div className="flex items-center gap-2 w-24">
                        <Volume2 size={18} className="text-slate-400" />
                        <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-green-400 rounded-full transition-all duration-100"
                                style={{ width: `${Math.min(100, volumeLevel * 500)}%` }}
                            />
                        </div>
                    </div>

                    {/* Record / Stop Button */}
                    {!isRecording ? (
                        <button
                            onClick={startRecording}
                            disabled={isPreparing}
                            className="w-16 h-16 bg-red-500 hover:bg-red-600 disabled:bg-red-300 rounded-full flex items-center justify-center shadow-lg hover:shadow-xl transition-all duration-200 group"
                        >
                            {isPreparing ? (
                                <Loader2 size={28} className="text-white animate-spin" />
                            ) : (
                                <Mic size={28} className="text-white group-hover:scale-110 transition-transform" />
                            )}
                        </button>
                    ) : (
                        <button
                            onClick={stopRecording}
                            className="w-16 h-16 bg-slate-700 hover:bg-slate-800 rounded-full flex items-center justify-center shadow-lg hover:shadow-xl transition-all duration-200 group"
                        >
                            <Square size={24} className="text-white fill-white group-hover:scale-110 transition-transform" />
                        </button>
                    )}

                    {/* Timer display */}
                    <div className="w-24 text-center">
                        {isRecording && (
                            <span className="font-mono text-lg text-slate-700">{formatTime(recordingTime)}</span>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

// --- Meeting Card Component ---
interface MeetingCardProps {
    meeting: Meeting;
    onClick: (meeting: Meeting) => void;
}

const MeetingCard = ({ meeting, onClick }: MeetingCardProps) => {
    const statusColors = {
        completed: 'bg-emerald-100 text-emerald-700',
        processing: 'bg-amber-100 text-amber-700',
        failed: 'bg-red-100 text-red-700'
    };

    const statusLabels = {
        completed: '已完成',
        processing: 'AI 處理中',
        failed: '處理失敗'
    };

    const statusDescriptions = {
        completed: '',
        processing: '正在轉錄音檔並生成摘要',
        failed: '點擊重試'
    };

    return (
        <div
            onClick={() => onClick(meeting)}
            className="group bg-white border border-slate-200 rounded-xl p-5 cursor-pointer hover:shadow-lg hover:border-indigo-200 transition-all duration-300"
        >
            <div className="flex justify-between items-start mb-3">
                <div>
                    <h3 className="font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">
                        {meeting.title}
                    </h3>
                    <div className="flex items-center gap-3 mt-1 text-sm text-slate-500">
                        <span className="flex items-center gap-1"><Calendar size={14} /> {meeting.date}</span>
                        <span className="flex items-center gap-1"><Clock size={14} /> {meeting.duration}</span>
                    </div>
                </div>
                <div className="flex flex-col items-end">
                    <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${statusColors[meeting.status]}`}>
                        {meeting.status === 'processing' && <Loader2 size={12} className="inline mr-1 animate-spin" />}
                        {statusLabels[meeting.status]}
                    </span>
                    {statusDescriptions[meeting.status] && (
                        <span className="text-[10px] text-slate-400 mt-1">
                            {statusDescriptions[meeting.status]}
                        </span>
                    )}
                </div>
            </div>

            <p className="text-slate-600 text-sm line-clamp-2 leading-relaxed">
                {meeting.status === 'processing'
                    ? '⏳ AI 正在分析會議內容，請稍候...'
                    : meeting.status === 'failed'
                        ? '❌ 處理失敗，請點擊查看詳情並重試'
                        : meeting.summary || '暫無摘要'}
            </p>

            <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                {/* Display transcript segment count or processing indicator */}
                <div className="flex items-center gap-2 text-xs text-slate-400">
                    {meeting.status === 'completed' && meeting.transcript.length > 0 && (
                        <span className="flex items-center gap-1">
                            <FileText size={12} />
                            {meeting.transcript.length} 段落
                        </span>
                    )}
                    {meeting.status === 'processing' && (
                        <span className="flex items-center gap-1 text-amber-500">
                            <Loader2 size={12} className="animate-spin" />
                            處理中
                        </span>
                    )}
                    {meeting.status === 'failed' && (
                        <span className="flex items-center gap-1 text-red-500">
                            <AlertCircle size={12} />
                            需要重試
                        </span>
                    )}
                </div>
                <div className="text-indigo-600 text-sm font-medium flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    查看詳情 <ChevronRight size={16} />
                </div>
            </div>
        </div>
    );
};

// --- Dashboard View Component ---
interface DashboardViewProps {
    meetings: Meeting[];
    isLoading: boolean;
    error: string | null;
    successMessage: string | null;
    onSelectMeeting: (meeting: Meeting) => void;
    onCreateMeeting: () => void;
    onRefresh: () => void;
}

const DashboardView = ({ meetings, isLoading, error, successMessage, onSelectMeeting, onCreateMeeting, onRefresh }: DashboardViewProps) => {
    const [searchQuery, setSearchQuery] = useState('');

    const filteredMeetings = meetings.filter(m =>
        m.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.summary.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">

            {/* Header & Actions */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">我的會議記錄</h1>
                    <p className="text-slate-500">管理並搜尋所有的會議內容</p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={onRefresh}
                        className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50 font-medium transition-colors"
                        disabled={isLoading}
                    >
                        <RefreshCw size={18} className={isLoading ? 'animate-spin' : ''} />
                        <span>重新整理</span>
                    </button>
                </div>
            </div>

            {/* Error Banner */}
            {error && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
                    <AlertCircle className="text-red-500 flex-shrink-0 mt-0.5" size={20} />
                    <div>
                        <p className="font-medium text-red-800">無法載入會議列表</p>
                        <p className="text-sm text-red-600 mt-1">{error}</p>
                    </div>
                </div>
            )}

            {/* Success Banner */}
            <div className={`transition-all duration-500 ease-in-out overflow-hidden ${successMessage ? 'max-h-20 opacity-100' : 'max-h-0 opacity-0'}`}>
                <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-3 mb-0">
                    <CheckCircle2 className="text-green-500 flex-shrink-0" size={20} />
                    <p className="font-medium text-green-800">{successMessage}</p>
                </div>
            </div>

            {/* Search Bar */}
            <div className="relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
                <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="搜尋會議標題、關鍵字或參與者..."
                    className="w-full pl-12 pr-4 py-3 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent shadow-sm transition-all"
                />
            </div>

            {/* Loading State */}
            {isLoading && (
                <div className="text-center py-16">
                    <Loader2 size={48} className="mx-auto text-indigo-500 animate-spin mb-4" />
                    <p className="text-slate-500">載入會議列表中...</p>
                </div>
            )}

            {/* Meeting List */}
            {!isLoading && (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {filteredMeetings.map((meeting, index) => (
                        <div
                            key={meeting.id}
                            style={{ animationDelay: `${index * 0.1}s` }}
                            className="animate-in fade-in slide-in-from-bottom-4 duration-500"
                        >
                            <MeetingCard
                                meeting={meeting}
                                onClick={onSelectMeeting}
                            />
                        </div>
                    ))}
                </div>
            )}

            {/* Empty State */}
            {!isLoading && !error && filteredMeetings.length === 0 && (
                <div className="text-center py-16">
                    <FileText size={48} className="mx-auto text-slate-300 mb-4" />
                    <p className="text-slate-500">
                        {searchQuery ? '沒有找到符合的會議記錄' : '還沒有會議記錄，點擊「開始錄音」開始第一場會議'}
                    </p>
                </div>
            )}
        </div>
    );
};

// --- Detail View Component ---
interface DetailViewProps {
    meeting: Meeting | null;
    onBack: () => void;
    onRegenerateSummary?: (meetingId: string) => void;
    isRegenerating?: boolean;
    onDelete?: (meetingId: string) => void;
    isDeleting?: boolean;
}

const DetailView = ({ meeting, onBack, onRegenerateSummary, isRegenerating = false, onDelete, isDeleting = false }: DetailViewProps) => {
    if (!meeting) return null;

    const canRegenerate = meeting.status !== 'processing' && onRegenerateSummary;
    const needsSummary = !meeting.summary || meeting.status === 'failed';

    return (
        <div className="h-full flex flex-col bg-white">
            <div className="border-b border-slate-200 px-6 py-4 flex items-center gap-4 bg-white sticky top-0 z-10">
                <button onClick={onBack} className="p-2 hover:bg-slate-100 rounded-full text-slate-500 transition-colors">
                    <ChevronRight size={24} className="rotate-180" />
                </button>
                <div className="flex-1">
                    <h2 className="text-xl font-bold text-slate-900">{meeting.title}</h2>
                    <div className="flex items-center gap-3 text-sm text-slate-500">
                        <span>{meeting.date}</span>
                        <span className="w-1 h-1 rounded-full bg-slate-300"></span>
                        <span>{meeting.duration}</span>
                    </div>
                </div>
                {/* Export dropdown */}
                <div className="relative group">
                    <button
                        className="flex items-center gap-1 px-3 py-2 text-sm text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                        title="匯出"
                    >
                        <Download size={18} />
                        <span className="hidden sm:inline">匯出</span>
                        <ChevronDown size={14} />
                    </button>
                    <div className="absolute right-0 top-full mt-1 w-40 bg-white border border-slate-200 rounded-xl shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-20">
                        <button onClick={() => exportAsTxt(meeting)} className="w-full px-4 py-2.5 text-sm text-left text-slate-700 hover:bg-indigo-50 hover:text-indigo-600 rounded-t-xl transition-colors">
                            📄 TXT 純文字
                        </button>
                        <button onClick={() => exportAsSrt(meeting)} disabled={meeting.transcript.length === 0} className="w-full px-4 py-2.5 text-sm text-left text-slate-700 hover:bg-indigo-50 hover:text-indigo-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                            🎬 SRT 字幕
                        </button>
                        <button onClick={() => exportAsJson(meeting)} className="w-full px-4 py-2.5 text-sm text-left text-slate-700 hover:bg-indigo-50 hover:text-indigo-600 rounded-b-xl transition-colors">
                            📋 JSON 結構化
                        </button>
                    </div>
                </div>
                {/* Delete button */}
                {onDelete && (
                    <button
                        onClick={() => onDelete(meeting.id)}
                        disabled={isDeleting}
                        className="p-2 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-full transition-colors disabled:opacity-50"
                        title="刪除會議"
                    >
                        {isDeleting ? <Loader2 size={20} className="animate-spin" /> : <Trash2 size={20} />}
                    </button>
                )}
            </div>

            <div className="flex-1 overflow-hidden flex flex-col md:flex-row">
                <div className="flex-1 overflow-y-auto p-6 md:p-8 border-r border-slate-200 bg-slate-50/50">
                    <div className="max-w-3xl mx-auto space-y-8">
                        <section>
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500 flex items-center gap-2">
                                    <FileText size={16} /> 會議摘要
                                </h3>
                                {canRegenerate && (
                                    <button
                                        onClick={() => onRegenerateSummary(meeting.id)}
                                        disabled={isRegenerating}
                                        className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                    >
                                        {isRegenerating ? (
                                            <>
                                                <Loader2 size={12} className="animate-spin" />
                                                生成中...
                                            </>
                                        ) : (
                                            <>
                                                <RefreshCw size={12} />
                                                {needsSummary ? '生成摘要' : '重新生成'}
                                            </>
                                        )}
                                    </button>
                                )}
                            </div>
                            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm leading-relaxed text-slate-700">
                                {meeting.status === 'processing' ? (
                                    <div className="flex flex-col items-center justify-center py-8 text-slate-400">
                                        <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mb-2" />
                                        <p>AI 正在處理中，請稍候...</p>
                                        <p className="text-xs mt-1">通常需要 1-3 分鐘</p>
                                    </div>
                                ) : meeting.status === 'failed' ? (
                                    <div className="flex flex-col items-center justify-center py-8 text-red-400">
                                        <AlertCircle className="h-8 w-8 mb-2" />
                                        <p>摘要生成失敗</p>
                                        <p className="text-xs mt-1">請點擊「重新生成」按鈕重試</p>
                                    </div>
                                ) : meeting.summary ? (
                                    meeting.summary
                                ) : (
                                    <div className="flex flex-col items-center justify-center py-8 text-slate-400">
                                        <FileText className="h-8 w-8 mb-2" />
                                        <p>尚無摘要</p>
                                        <p className="text-xs mt-1">點擊「生成摘要」開始</p>
                                    </div>
                                )}
                            </div>
                        </section>

                        <section>
                            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500 mb-4 flex items-center gap-2">
                                <CheckCircle2 size={16} /> 待辦事項 (Action Items)
                            </h3>
                            <div className="space-y-3">
                                {meeting.actionItems && meeting.actionItems.length > 0 ? (
                                    meeting.actionItems.map(item => (
                                        <div key={item.id} className="flex items-start gap-3 bg-white p-4 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
                                            <div className="mt-1 w-5 h-5 rounded border-2 border-slate-300 cursor-pointer hover:border-indigo-500 transition-colors"></div>
                                            <div className="flex-1">
                                                <p className="text-slate-800 font-medium">{item.text}</p>
                                                <div className="flex items-center gap-3 mt-2 text-xs">
                                                    <span className="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded font-medium">{item.assignee}</span>
                                                    <span className="text-slate-400">Due: {item.due}</span>
                                                </div>
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    <p className="text-slate-400 text-sm italic ml-2">無待辦事項或尚未生成。</p>
                                )}
                            </div>
                        </section>
                    </div>
                </div>

                <div className="md:w-[400px] lg:w-[480px] flex flex-col bg-white">
                    <div className="p-4 border-b border-slate-200 bg-white">
                        <h3 className="font-bold text-slate-800">逐字稿紀錄</h3>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-6">
                        {meeting.transcript && meeting.transcript.length > 0 ? (
                            meeting.transcript.map((line, idx) => (
                                <div key={idx} className="group flex gap-4">
                                    <div className="w-12 text-xs text-slate-400 font-mono pt-1 text-right flex-shrink-0 group-hover:text-indigo-500 cursor-pointer transition-colors">
                                        {line.time}
                                    </div>
                                    <div>
                                        <div className="text-xs font-bold text-slate-900 mb-1">{line.speaker}</div>
                                        <p className="text-slate-600 text-sm leading-relaxed hover:bg-yellow-50 rounded px-1 -ml-1 transition-colors cursor-pointer">
                                            {line.text}
                                        </p>
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div className="text-center py-10 text-slate-400">
                                <p>尚無逐字稿內容</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

// --- Settings View Component ---
const SettingsView = ({ onBack, isConnected }: { onBack: () => void; isConnected: boolean }) => {
    return (
        <div className="p-6 md:p-8 max-w-4xl mx-auto">
            <div className="flex items-center gap-4 mb-8">
                <button onClick={onBack} className="p-2 hover:bg-slate-100 rounded-full text-slate-500 transition-colors">
                    <ChevronRight size={24} className="rotate-180" />
                </button>
                <h1 className="text-2xl font-bold text-slate-900">系統設定</h1>
            </div>

            <div className="space-y-6">
                <div className="bg-white rounded-xl border border-slate-200 p-6">
                    <h3 className="font-bold text-slate-900 mb-4">API 連線狀態</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                {isConnected ? (
                                    <Wifi className="text-emerald-500" size={24} />
                                ) : (
                                    <WifiOff className="text-red-500" size={24} />
                                )}
                                <div>
                                    <p className="font-medium text-slate-800">
                                        {isConnected ? '已連線到後端服務' : '無法連線到後端服務'}
                                    </p>
                                    <p className="text-sm text-slate-500">
                                        {isConnected ? '所有功能正常運作' : '請檢查網路連線或後端服務狀態'}
                                    </p>
                                </div>
                            </div>
                            <span className={`px-3 py-1 rounded-full text-sm font-medium ${isConnected ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                                }`}>
                                {isConnected ? 'Online' : 'Offline'}
                            </span>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-1">Backend URL</label>
                            <input
                                type="text"
                                value={API_BASE_URL}
                                readOnly
                                className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-600 font-mono text-sm"
                            />
                        </div>
                    </div>
                </div>

                <div className="bg-white rounded-xl border border-slate-200 p-6">
                    <h3 className="font-bold text-slate-900 mb-4">語音辨識設定</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between opacity-60">
                            <div>
                                <p className="font-medium text-slate-800">自動標點符號</p>
                                <p className="text-sm text-slate-500">AI 自動添加逗號、句號</p>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-xs text-slate-400">預設開啟</span>
                                <div className="w-12 h-6 bg-slate-300 rounded-full relative cursor-not-allowed" title="此設定尚未開放調整">
                                    <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full shadow"></div>
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center justify-between opacity-60">
                            <div>
                                <p className="font-medium text-slate-800">說話者分離</p>
                                <p className="text-sm text-slate-500">自動識別不同說話者</p>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-xs text-slate-400">預設開啟</span>
                                <div className="w-12 h-6 bg-slate-300 rounded-full relative cursor-not-allowed" title="此設定尚未開放調整">
                                    <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full shadow"></div>
                                </div>
                            </div>
                        </div>
                        <p className="text-xs text-slate-400 italic mt-2">※ 設定調整功能開發中，目前使用後端預設值</p>
                    </div>
                </div>
            </div>
        </div>
    );
};

// --- Main App Component ---
export default function DashboardPage() {
    const { data: session } = useSession();
    const [currentView, setCurrentView] = useState<'dashboard' | 'record' | 'detail' | 'settings' | 'templates' | 'admin'>('dashboard');
    const [selectedMicDeviceId, setSelectedMicDeviceId] = useState<string>('');
    const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    // API State
    const [meetings, setMeetings] = useState<Meeting[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isConnected, setIsConnected] = useState(false);

    // Sync session token with API client for authenticated requests
    useEffect(() => {
        if (session?.idToken) {
            api.setToken(session.idToken);
        } else {
            api.setToken(null);
        }
    }, [session?.idToken]);

    // Fetch meetings from API
    const fetchMeetings = useCallback(async () => {
        setIsLoading(true);
        setError(null);

        try {
            // Check connection first
            await api.checkHealth();
            setIsConnected(true);

            // Fetch meetings
            const apiMeetings = await api.listMeetings();
            const transformedMeetings = apiMeetings.map(transformMeeting)
                .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
            setMeetings(transformedMeetings);
        } catch (err) {
            setIsConnected(false);
            setError(err instanceof Error ? err.message : '發生未知錯誤');
            setMeetings([]);
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Initial load
    useEffect(() => {
        fetchMeetings();
    }, [fetchMeetings]);

    // Recording state
    const [recordingMeetingId, setRecordingMeetingId] = useState<string | null>(null);
    const [recordingTitle, setRecordingTitle] = useState('新會議');

    const handleStartRecord = async () => {
        try {
            const title = prompt('請輸入會議標題：', `會議 ${new Date().toLocaleDateString('zh-TW')}`) || `會議 ${new Date().toLocaleDateString('zh-TW')}`;
            setRecordingTitle(title);
            const meeting = await api.createMeeting({ title });
            setRecordingMeetingId(meeting.id);
            setCurrentView('record');
        } catch (err) {
            console.error('Failed to create meeting:', err);
            setError(err instanceof Error ? err.message : '建立會議失敗');
        }
    };

    const handleViewDetail = (meeting: Meeting) => {
        setSelectedMeeting(meeting);
        setCurrentView('detail');
    };

    // State for regenerating summary
    const [isRegenerating, setIsRegenerating] = useState(false);

    // Handler for regenerating summary
    const handleRegenerateSummary = useCallback(async (meetingId: string) => {
        setIsRegenerating(true);
        try {
            await api.regenerateSummary(meetingId, 'general');

            // Refresh meetings list to get updated status
            await fetchMeetings();

            // Update selected meeting with new data
            if (selectedMeeting && selectedMeeting.id === meetingId) {
                const apiMeetings = await api.listMeetings();
                const updatedMeeting = apiMeetings.find(m => m.id === meetingId);
                if (updatedMeeting) {
                    setSelectedMeeting(transformMeeting(updatedMeeting));
                }
            }
        } catch (err) {
            console.error('Failed to regenerate summary:', err);
            setError(err instanceof Error ? err.message : '重新生成摘要失敗');
        } finally {
            setIsRegenerating(false);
        }
    }, [fetchMeetings, selectedMeeting]);

    const handleBackToDashboard = () => {
        setSelectedMeeting(null);
        setCurrentView('dashboard');
    };

    // Delete meeting handler
    const [isDeleting, setIsDeleting] = useState(false);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const handleDeleteMeeting = useCallback(async (meetingId: string) => {
        if (!confirm('確定要刪除這個會議記錄嗎？此操作無法復原。')) return;
        setIsDeleting(true);
        try {
            await api.deleteMeeting(meetingId);
            await fetchMeetings();
            handleBackToDashboard();
            setSuccessMessage('會議已成功刪除');
            setTimeout(() => setSuccessMessage(null), 5000);
        } catch (err) {
            console.error('Failed to delete meeting:', err);
            setError(err instanceof Error ? err.message : '刪除會議失敗');
        } finally {
            setIsDeleting(false);
        }
    }, [fetchMeetings]);

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
        <div className="flex h-screen bg-slate-50 font-sans text-slate-900 overflow-hidden">
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
                    <div className="md:hidden bg-white border-b border-slate-200 p-4 flex items-center justify-between z-20">
                        <div className="flex items-center gap-2">
                            <div className="w-6 h-6 bg-indigo-500 rounded flex items-center justify-center">
                                <span className="font-bold text-white text-xs">M</span>
                            </div>
                            <span className="font-bold">MeetChi</span>
                        </div>
                        <button onClick={() => setIsMobileMenuOpen(true)}>
                            <Menu className="text-slate-600" />
                        </button>
                    </div>
                )}

                <div className="flex-1 overflow-auto bg-slate-50">
                    {currentView === 'dashboard' && (
                        <DashboardView
                            meetings={meetings}
                            isLoading={isLoading}
                            error={error}
                            successMessage={successMessage}
                            onSelectMeeting={handleViewDetail}
                            onCreateMeeting={handleStartRecord}
                            onRefresh={fetchMeetings}
                        />
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
                            isDeleting={isDeleting}
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
                                <h1 className="text-2xl font-bold text-slate-900 mb-2">模板管理</h1>
                                <p className="text-slate-500">選擇適合會議類型的摘要模板（生成摘要時可指定）</p>
                            </div>

                            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-6 flex items-start gap-3">
                                <AlertCircle className="text-amber-500 flex-shrink-0 mt-0.5" size={20} />
                                <div>
                                    <p className="font-medium text-amber-800">模板管理功能開發中</p>
                                    <p className="text-sm text-amber-600 mt-1">以下是後端已支援的模板。自訂模板 CRUD 功能尚未開放。</p>
                                </div>
                            </div>

                            {/* Template Cards - read-only display of backend-supported templates */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {[
                                    { name: 'general', label: '一般會議', desc: '通用模板，含摘要、待辦、決議', color: 'indigo', icon: FileText, tags: ['摘要', '待辦事項', '決議'] },
                                    { name: 'sales_bant', label: '業務會議 (BANT)', desc: 'Budget / Authority / Need / Timeline', color: 'amber', icon: Clock, tags: ['預算', '決策者', '需求', '時程'] },
                                    { name: 'hr_star', label: '面試評估 (STAR)', desc: 'Situation / Task / Action / Result', color: 'emerald', icon: CheckCircle2, tags: ['情境', '任務', '行動', '結果'] },
                                    { name: 'rd', label: '研發會議', desc: '技術決策與進度追蹤', color: 'purple', icon: Mic, tags: ['技術決策', '進度', '風險'] },
                                ].map(tpl => (
                                    <div key={tpl.name} className="bg-white rounded-xl border border-slate-200 p-6 transition-all">
                                        <div className="flex items-start gap-4">
                                            <div className={`w-12 h-12 bg-${tpl.color}-100 rounded-xl flex items-center justify-center text-${tpl.color}-600`}>
                                                <tpl.icon size={24} />
                                            </div>
                                            <div className="flex-1">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <h3 className="font-semibold text-slate-900">{tpl.label}</h3>
                                                    {tpl.name === 'general' && <span className="px-2 py-0.5 text-xs bg-indigo-100 text-indigo-600 rounded-full">預設</span>}
                                                </div>
                                                <p className="text-sm text-slate-500 mb-3">{tpl.desc}</p>
                                                <div className="flex flex-wrap gap-2">
                                                    {tpl.tags.map(tag => (
                                                        <span key={tag} className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">{tag}</span>
                                                    ))}
                                                </div>
                                                <p className="text-xs text-slate-400 mt-3 font-mono">template_name: "{tpl.name}"</p>
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
                                <h1 className="text-2xl font-bold text-slate-900 mb-2">管理</h1>
                                <p className="text-slate-500">系統管理與用戶設定</p>
                            </div>

                            {/* User Profile Card */}
                            <div className="bg-white rounded-xl border border-slate-200 p-6 mb-6">
                                <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
                                    <Shield size={20} className="text-indigo-600" />
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
                                        <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center text-white text-2xl font-bold">
                                            {session?.user?.name?.charAt(0) || '?'}
                                        </div>
                                    )}
                                    <div>
                                        <p className="text-lg font-medium text-slate-900">{session?.user?.name || '未登入'}</p>
                                        <p className="text-slate-500">{session?.user?.email || '-'}</p>
                                        <span className="inline-flex items-center gap-1 mt-1 px-2 py-0.5 text-xs bg-indigo-100 text-indigo-600 rounded-full">
                                            <Shield size={12} />
                                            管理員
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Stats Grid — real data from API */}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                                <div className="bg-white rounded-xl border border-slate-200 p-5">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center text-indigo-600">
                                            <FileText size={20} />
                                        </div>
                                        <div>
                                            <p className="text-2xl font-bold text-slate-900">{meetings.length}</p>
                                            <p className="text-sm text-slate-500">會議記錄</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="bg-white rounded-xl border border-slate-200 p-5">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center text-emerald-600">
                                            <CheckCircle2 size={20} />
                                        </div>
                                        <div>
                                            <p className="text-2xl font-bold text-slate-900">{meetings.filter(m => m.status === 'completed').length}</p>
                                            <p className="text-sm text-slate-500">已完成摘要</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="bg-white rounded-xl border border-slate-200 p-5">
                                    <div className="flex items-center gap-3">
                                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${isConnected ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-600'}`}>
                                            {isConnected ? <Wifi size={20} /> : <WifiOff size={20} />}
                                        </div>
                                        <div>
                                            <p className="text-2xl font-bold text-slate-900">{isConnected ? 'Online' : 'Offline'}</p>
                                            <p className="text-sm text-slate-500">後端狀態</p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Coming Soon Features */}
                            <div className="bg-white rounded-xl border border-slate-200 p-6">
                                <h2 className="text-lg font-semibold text-slate-900 mb-4">功能規劃</h2>
                                <div className="space-y-3">
                                    <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                                        <div className="w-8 h-8 bg-amber-100 rounded-lg flex items-center justify-center text-amber-600">
                                            <Shield size={16} />
                                        </div>
                                        <div className="flex-1">
                                            <p className="font-medium text-slate-700">Entra ID 整合</p>
                                            <p className="text-xs text-slate-500">企業 SSO 認證</p>
                                        </div>
                                        <span className="px-2 py-1 text-xs bg-amber-100 text-amber-600 rounded">規劃中</span>
                                    </div>
                                    <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                                        <div className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center text-purple-600">
                                            <Settings size={16} />
                                        </div>
                                        <div className="flex-1">
                                            <p className="font-medium text-slate-700">用戶管理</p>
                                            <p className="text-xs text-slate-500">角色權限設定</p>
                                        </div>
                                        <span className="px-2 py-1 text-xs bg-purple-100 text-purple-600 rounded">規劃中</span>
                                    </div>
                                    <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                                        <div className="w-8 h-8 bg-indigo-100 rounded-lg flex items-center justify-center text-indigo-600">
                                            <Calendar size={16} />
                                        </div>
                                        <div className="flex-1">
                                            <p className="font-medium text-slate-700">會議分析</p>
                                            <p className="text-xs text-slate-500">統計報表、趨勢分析</p>
                                        </div>
                                        <span className="px-2 py-1 text-xs bg-indigo-100 text-indigo-600 rounded">規劃中</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
