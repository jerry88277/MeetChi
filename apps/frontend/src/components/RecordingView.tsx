"use client";

import React, { useState, useEffect, useRef } from 'react';
import {
    Mic,
    ChevronRight,
    Loader2,
    AlertCircle,
    Square,
    Volume2,
    UploadCloud,
    Shield
} from 'lucide-react';
import { api } from '@/lib/api';
import { set, get, del, keys } from 'idb-keyval';

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

export const RecordingView = ({ meetingId, meetingTitle, onBack, onFinish }: RecordingViewProps) => {
    const [isRecording, setIsRecording] = useState(false);
    const [isPreparing, setIsPreparing] = useState(false);
    const [recordingTime, setRecordingTime] = useState(0);
    const [transcriptEntries, setTranscriptEntries] = useState<TranscriptEntry[]>([]);
    const [volumeLevel, setVolumeLevel] = useState(0);
    const [wsStatus, setWsStatus] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
    const [errorMsg, setErrorMsg] = useState<string | null>(null);
    const [backendReady, setBackendReady] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [customContext, setCustomContext] = useState('');

    const wsRef = useRef<WebSocket | null>(null);
    const audioContextRef = useRef<AudioContext | null>(null);
    const processorRef = useRef<ScriptProcessorNode | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const transcriptEndRef = useRef<HTMLDivElement>(null);
    const recognitionRef = useRef<any>(null);
    const isRecordingRef = useRef(false);

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
            // Audio constraints — Stage 1 of recording pipeline uplift:
            //   - sampleRate ideal=48000: 讓 OS 給原始品質 (iOS/macOS VPIO 內建處理)，
            //     後續 AudioContext 16k pipeline 由 browser 重採樣，保留 dynamic range
            //   - autoGainControl=true: **Windows 主戰場**——iOS/macOS 有 OS 級 VPIO，
            //     Windows 沒等價 voice-processing pipeline，必須補軟體 AGC
            //   - echoCancellation/noiseSuppression: Chrome WebRTC 軟體 NS（master switch）
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: { ideal: 48000 },
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
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

            // 3.5 Setup MediaRecorder for local full-quality backup
            audioChunksRef.current = [];
            let options = { mimeType: 'audio/webm;codecs=opus' };
            if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                options = { mimeType: 'audio/webm' };
            }
            const mediaRecorder = new MediaRecorder(stream, options);
            mediaRecorderRef.current = mediaRecorder;
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunksRef.current.push(e.data);
            };
            mediaRecorder.start(1000); // accumulate chunks every 1s

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
                            // Remove partial (both backend partial and Web Speech partial), add raw
                            const filtered = newEntries.filter(e =>
                                !((e.id === msg.id && e.type === 'partial') || e.id === 'web-speech-partial')
                            );
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
                    initial_prompt: customContext,
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

            // 7. Web Speech API — free, low-latency partial transcription
            const SpeechRecognition = (window as any).webkitSpeechRecognition
                || (window as any).SpeechRecognition;
            if (SpeechRecognition) {
                const recognition = new SpeechRecognition();
                recognition.lang = 'zh-TW';
                recognition.continuous = true;
                recognition.interimResults = true;
                recognition.maxAlternatives = 1;

                recognition.onresult = (event: any) => {
                    const last = event.results[event.resultIndex];
                    const text = last[0].transcript;
                    if (!last.isFinal) {
                        // Show interim result as partial transcript
                        setTranscriptEntries(prev => {
                            const idx = prev.findIndex(e => e.id === 'web-speech-partial' && e.type === 'partial');
                            if (idx >= 0) {
                                const updated = [...prev];
                                updated[idx] = { ...updated[idx], content: text };
                                return updated;
                            }
                            return [...prev, { id: 'web-speech-partial', type: 'partial' as const, content: text }];
                        });
                    }
                    // Note: We don't use isFinal from Web Speech API as final.
                    // The authoritative final transcript comes from Gemini API via backend.
                };

                recognition.onerror = (event: any) => {
                    if (event.error !== 'no-speech' && event.error !== 'aborted') {
                        console.warn('[MeetChi] Web Speech API error:', event.error);
                    }
                };

                recognition.onend = () => {
                    // Auto-restart if still recording
                    if (isRecordingRef.current) {
                        try { recognition.start(); } catch { /* ignore */ }
                    }
                };

                try {
                    recognition.start();
                    recognitionRef.current = recognition;
                    console.log('[MeetChi] Web Speech API started for partial transcription');
                } catch (e) {
                    console.warn('[MeetChi] Web Speech API failed to start:', e);
                }
            } else {
                console.warn('[MeetChi] Web Speech API not supported in this browser');
            }

            isRecordingRef.current = true;

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

        // Stop Web Speech API
        if (recognitionRef.current) {
            try { recognitionRef.current.stop(); } catch { /* ignore */ }
            recognitionRef.current = null;
        }
        isRecordingRef.current = false;

        // Close WebSocket (stateless backend will clean up)
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }

        setIsRecording(false);
        setVolumeLevel(0);

        // Handle MediaRecorder completion, Upload and UI transition
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
            setIsUploading(true);
            mediaRecorderRef.current.onstop = async () => {
                const blob = new Blob(audioChunksRef.current, { type: mediaRecorderRef.current?.mimeType || 'audio/webm' });
                
                if (streamRef.current) {
                    streamRef.current.getTracks().forEach(t => t.stop());
                    streamRef.current = null;
                }
                
                if (meetingId) {
                    try {
                        // Phase 1: Backup locally
                        await set(`meeting_audio_${meetingId}`, blob);
                        console.log(`[MeetChi] Audio saved locally to IDB (meeting_audio_${meetingId})`);
                        
                        // Phase 2: Upload to GCS
                        const file = new File([blob], 'audio.webm', { type: blob.type });
                        const { uploadUrl } = await api.getUploadUrl(meetingId, 'audio.webm', blob.type);
                        await api.uploadToGcs(uploadUrl, file);
                        console.log(`[MeetChi] Audio uploaded safely to GCS`);
                        
                        // Phase 3: Trigger Background Summary Task
                        await api.regenerateSummary(meetingId, 'general', customContext);
                        console.log(`[MeetChi] Background summary task triggered`);
                        
                        // Cleanup
                        await del(`meeting_audio_${meetingId}`);
                        console.log(`[MeetChi] Local audio backup cleared`);
                        
                    } catch (e) {
                        console.error('[MeetChi] Upload failed:', e);
                        // We intentionally don't clear the `meeting_audio_${meetingId}` in IDB so Crash Recovery can find it.
                        setErrorMsg('上傳過程中發生錯誤，將為您保留本地備份，稍後可於 Dashboard 重試。');
                    } finally {
                        setIsUploading(false);
                        onFinish(meetingId);
                    }
                } else {
                    setIsUploading(false);
                    if (meetingId) onFinish(meetingId);
                }
            };
            mediaRecorderRef.current.stop();
        } else {
            if (streamRef.current) {
                streamRef.current.getTracks().forEach(t => t.stop());
                streamRef.current = null;
            }
            if (meetingId) {
                onFinish(meetingId);
            }
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
            if (recognitionRef.current) { try { recognitionRef.current.stop(); } catch { } }
            isRecordingRef.current = false;
        };
    }, []);

    // Finalized entries only (raw or polished)
    const finalizedEntries = transcriptEntries.filter(e => e.type !== 'partial');
    const currentPartial = transcriptEntries.find(e => e.type === 'partial');

    return (
        <div className="h-full flex flex-col bg-white relative">
            {/* Overlay during upload */}
            {isUploading && (
                <div className="absolute inset-0 bg-white/80 backdrop-blur-sm z-50 flex flex-col items-center justify-center">
                    <Loader2 className="w-12 h-12 text-indigo-600 animate-spin mb-4" />
                    <h3 className="text-xl font-bold text-slate-800">音檔安穩上傳中...</h3>
                    <p className="text-slate-500 mt-2">保障您的會議紀錄不遺失，請勿關閉視窗</p>
                </div>
            )}

            {/* Header */}
            <div className="border-b border-slate-200 px-6 py-4 flex items-center gap-4 bg-white sticky top-0 z-10">
                <button onClick={() => { if (isRecording) { stopRecording(); } else { onBack(); } }}
                    className="p-2 hover:bg-slate-100 rounded-full text-slate-500 transition-colors">
                    <ChevronRight size={24} className="rotate-180" />
                </button>
                <div className="flex-1">
                    <div className="flex items-center gap-3">
                        <h2 className="text-xl font-bold text-slate-900">{meetingTitle}</h2>
                        <div className="flex items-center gap-1.5 px-2 py-0.5 bg-green-50 text-green-700 rounded-full text-[10px] font-semibold border border-green-200">
                            <Shield className="w-3 h-3" />
                            <span>地端機密錄音</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-3 text-sm text-slate-500 mt-1">
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
                        <p className="text-slate-500 max-w-sm mb-6">點擊下方按鈕開始錄音，系統將即時轉錄你的語音。</p>
                        
                        {/* Custom Context Input */}
                        <div className="w-full max-w-sm text-left">
                            <label className="text-sm font-medium text-slate-700 mb-2 block">
                                專有名詞 / 背景資料 (可選)
                            </label>
                            <input 
                                type="text"
                                value={customContext}
                                onChange={(e) => setCustomContext(e.target.value)}
                                placeholder="例如: MeetChi, AI專案, Scrum..."
                                className="w-full px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all placeholder:text-slate-400 shadow-sm"
                            />
                            <p className="text-xs text-slate-500 mt-2">提供關鍵字能幫助 AI 更好辨識生僻名詞</p>
                        </div>
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
