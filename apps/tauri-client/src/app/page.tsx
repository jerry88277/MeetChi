'use client';

import { useState, useRef, useEffect } from "react";
import { Mic, Square, Settings, Lock, Clock, FileText, RefreshCw, X, Minus } from "lucide-react";
import { getCurrentWindow, getAllWindows } from '@tauri-apps/api/window';
import { WebviewWindow } from '@tauri-apps/api/webviewWindow';
import { listen, UnlistenFn } from '@tauri-apps/api/event';
import { LogicalSize } from '@tauri-apps/api/dpi';
import { api, TranscriptSegment } from "@/lib/api";
import { invoke } from '@tauri-apps/api/core';

type DisplayMode = 'original' | 'translated' | 'bilingual';

type Segment = {
    id: string;
    content: string;
    translated?: string;
    isPolished: boolean;
    isPartial?: boolean;
};

// --- Helper for Web Mode ---
const isTauri = () => {
    return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
};

const safeInvoke = async (cmd: string, args?: any) => {
    if (isTauri()) {
        try {
            return await invoke(cmd, args);
        } catch (e) {
            console.warn(`Tauri invoke failed: ${cmd}`, e);
        }
    } else {
        console.log(`[Web Mode] Skipped invoke: ${cmd}`, args);
    }
};

const safeListen = async <T,>(event: string, handler: (event: any) => void): Promise<UnlistenFn> => {
    if (isTauri()) {
        try {
            return await listen<T>(event, handler);
        } catch (e) {
            console.warn(`Tauri listen failed: ${event}`, e);
        }
    }
    return () => { }; // Dummy unlisten
};

export default function Home() {
    // --- Global State ---
    const [isRecording, setIsRecording] = useState(false);
    const [isSpeechDetected, setIsSpeechDetected] = useState(false);
    const [segments, setSegments] = useState<Segment[]>([]);
    const [templateName, setTemplateName] = useState('general');
    const currentMeetingIdRef = useRef<string | null>(null);

    // --- Settings State ---
    const [displayMode, setDisplayMode] = useState<DisplayMode>('bilingual');
    const [fontSize, setFontSize] = useState(24);
    const [opacity, setOpacity] = useState(0.6);
    const [maxLines, setMaxLines] = useState(3); // Default 3

    // --- UI State ---
    const [isHovered, setIsHovered] = useState(false);
    const [isClickThrough, setIsClickThrough] = useState(false);
    const [isDesktop, setIsDesktop] = useState(false);

    useEffect(() => {
        setIsDesktop(isTauri());
    }, []);

    // --- Refs ---
    const scrollRefOriginal = useRef<HTMLDivElement>(null);
    const scrollRefTranslated = useRef<HTMLDivElement>(null);
    const speechTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const isResizingRef = useRef(false);
    const startResizeState = useRef<{ w: number, h: number, x: number, y: number, factor: number } | null>(null);

    // --- Window Controls ---
    const minimizeWindow = async () => {
        if (!isTauri()) return;
        try {
            await getCurrentWindow().minimize();
        } catch (e) {
            console.error("Failed to minimize:", e);
        }
    };

    const closeWindow = async () => {
        if (!isTauri()) return;
        try {
            await getCurrentWindow().close();
        } catch (e) {
            console.error("Failed to close:", e);
        }
    };

    const openSettings = async () => {
        if (!isTauri()) {
            window.open('/settings', '_blank', 'width=600,height=600');
            return;
        }
        try {
            const windows = await getAllWindows();
            const settingsWin = windows.find(w => w.label === 'settings');
            if (settingsWin) {
                await settingsWin.show();
                await settingsWin.setFocus();
            } else {
                const webview = new WebviewWindow('settings', {
                    url: '/settings',
                    title: 'TranscriptHub Settings',
                    width: 600,
                    height: 600,
                    resizable: true,
                    fullscreen: false,
                    transparent: true,
                    decorations: false,
                    alwaysOnTop: false,
                    shadow: false,
                    visible: true
                });
            }
        } catch (e) {
            console.error("Failed to get windows:", e);
        }
    };

    const openHistory = async () => {
        if (!isTauri()) {
            window.location.href = '/history';
            return;
        }
        try {
            const windows = await getAllWindows();
            const historyWin = windows.find(w => w.label === 'history');
            if (historyWin) {
                await historyWin.show();
                await historyWin.setFocus();
            } else {
                const webview = new WebviewWindow('history', {
                    url: '/history',
                    title: 'Meeting History',
                    width: 900,
                    height: 700,
                    resizable: true,
                    fullscreen: false,
                    transparent: false,
                    decorations: true,
                    visible: true
                });
            }
        } catch (e) {
            console.error("Failed to get windows:", e);
        }
    };

    // --- Click-through Logic ---
    const toggleClickThrough = async () => {
        const newState = !isClickThrough;
        setIsClickThrough(newState);

        if (!isTauri()) {
            if (newState) {
                setTimeout(() => alert("Web Mode: UI Locked. Press 'ESC' to unlock."), 100);
            }
            return;
        }

        await safeInvoke('set_ignore_cursor_events', { ignore: newState });
    };

    // --- Audio Control ---
    const toggleRecording = async () => {
        try {
            if (isRecording) {
                await safeInvoke('stop_audio_command');
                setIsRecording(false);
                setIsSpeechDetected(false);

                // Save segments to backend
                if (currentMeetingIdRef.current && segments.length > 0) {
                    const apiSegments: TranscriptSegment[] = segments.map((seg, index) => ({
                        order: index,
                        start_time: 0, // Placeholder
                        end_time: 0,   // Placeholder
                        content_raw: seg.content,
                        content_polished: seg.isPolished ? seg.content : undefined,
                        content_translated: seg.translated,
                        is_final: !seg.isPartial
                    }));

                    try {
                        await api.addSegments(currentMeetingIdRef.current, apiSegments);
                        console.log(`Saved ${apiSegments.length} segments for meeting ${currentMeetingIdRef.current}`);
                    } catch (saveError) {
                        console.error("Failed to save meeting segments:", saveError);
                        alert("Failed to save meeting data. Please check connection.");
                    }
                }
                currentMeetingIdRef.current = null;

            } else {
                // Create Meeting in Backend
                try {
                    const newMeeting = await api.createMeeting(`Meeting ${new Date().toLocaleString()}`, 'zh', templateName);
                    currentMeetingIdRef.current = newMeeting.id;
                    console.log("Created meeting:", newMeeting.id);
                } catch (createError) {
                    console.error("Failed to create meeting:", createError);
                    alert("Failed to create meeting session. Recording will not be saved.");
                    return;
                }

                const deviceId = localStorage.getItem('audioSource') || "default";
                const vadThreshold = parseFloat(localStorage.getItem('vadThreshold') || "0.005");
                const overlapDuration = parseFloat(localStorage.getItem('overlapDuration') || "0.0");
                const mode = localStorage.getItem('operationMode') || "transcription";
                let initialPrompt = localStorage.getItem('initialPrompt') || "";

                console.log("[DEBUG] Starting recording - Mode:", mode);
                console.log("[DEBUG] initialPrompt before alignment check:", initialPrompt);

                if (mode === 'alignment') {
                    const script = localStorage.getItem('combinedScript');
                    console.log("[DEBUG] Alignment mode detected, combinedScript:", script);
                    if (script) {
                        initialPrompt = script;
                        console.log("[DEBUG] Using combinedScript as initialPrompt. Length:", initialPrompt.length);
                    } else {
                        console.warn("[DEBUG] Alignment mode but no combinedScript found!");
                    }
                }

                console.log("[DEBUG] Final parameters for start_audio_command:");
                console.log("  - mode:", mode);
                console.log("  - initialPrompt length:", initialPrompt.length);
                console.log("  - initialPrompt preview:", initialPrompt.substring(0, 100));

                // Only for Tauri
                if (isTauri()) {
                    await safeInvoke('start_audio_command', { deviceId, vadThreshold, meetingId: currentMeetingIdRef.current, overlapDuration, mode, initialPrompt });
                }

                // In Web Mode, simulate
                if (!isTauri()) {
                    console.log("[Web Mode] Simulating recording...");
                    setSegments([]); // Clear segments
                    setTimeout(() => {
                        setSegments([{
                            id: 'mock-1', content: '這是一個測試會議。', isPolished: false, isPartial: false
                        }, {
                            id: 'mock-2', content: '我們正在測試摘要生成功能。', isPolished: false, isPartial: false
                        }]);
                    }, 1000);
                } else {
                    setSegments([]);
                }

                setIsRecording(true);
            }
        } catch (e) {
            console.error("Audio toggle failed:", e);
            alert(`Recording Error: ${e}`);
            setIsRecording(false);
            currentMeetingIdRef.current = null;
        }
    };

    // --- Dynamic Window Resizing ---
    const updateWindowHeight = async (fSize: number, lines: number, mode: DisplayMode) => {
        if (!isTauri()) return;
        try {
            const lineHeight = 1.6;
            const padding = 48;
            const titleBarHeight = !isClickThrough ? 48 : 0;
            const gap = 16;

            // Split total lines
            const linesPerArea = mode === 'bilingual' ? lines / 2 : lines;

            const originalHeight = fSize * lineHeight * linesPerArea;

            let contentHeight = originalHeight;
            if (mode === 'bilingual') {
                const transFontSize = fSize * 0.9;
                const transHeight = transFontSize * lineHeight * linesPerArea;
                contentHeight += transHeight + gap;
            }

            const totalHeight = contentHeight + padding + titleBarHeight + 20;

            const appWindow = getCurrentWindow();
            const size = await appWindow.innerSize();
            const factor = await appWindow.scaleFactor();
            const currentWidth = size.width / factor;

            await appWindow.setSize(new LogicalSize(currentWidth, totalHeight));
        } catch (e) {
            console.error("Failed to resize window:", e);
        }
    };

    // --- Custom Resize Logic (Optimized) ---
    const onResizeStart = async (e: React.MouseEvent) => {
        if (!isTauri()) return;
        e.stopPropagation();
        try {
            const appWindow = getCurrentWindow();
            const factor = await appWindow.scaleFactor();
            const size = await appWindow.innerSize();

            startResizeState.current = {
                w: size.width,
                h: size.height,
                x: e.screenX,
                y: e.screenY,
                factor: factor
            };
            isResizingRef.current = true;
        } catch (err) {
            console.error("Failed to init resize:", err);
        }
    };

    useEffect(() => {
        if (!isTauri()) return;
        const handleMouseMove = async (e: MouseEvent) => {
            if (!isResizingRef.current || !startResizeState.current) return;
            const state = startResizeState.current;

            const startLogicalW = state.w / state.factor;
            const startLogicalH = state.h / state.factor;

            const deltaX = e.screenX - state.x;
            const deltaY = e.screenY - state.y;

            const newWidth = startLogicalW + deltaX;
            const newHeight = startLogicalH + deltaY;

            if (newWidth > 300 && newHeight > 100) {
                await getCurrentWindow().setSize(new LogicalSize(newWidth, newHeight));
            }
        };

        const handleMouseUp = () => {
            isResizingRef.current = false;
            startResizeState.current = null;
        };

        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseup', handleMouseUp);

        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, []);


    // Auto Scroll
    useEffect(() => {
        if (scrollRefOriginal.current) {
            scrollRefOriginal.current.scrollTop = scrollRefOriginal.current.scrollHeight;
        }
        if (scrollRefTranslated.current) {
            scrollRefTranslated.current.scrollTop = scrollRefTranslated.current.scrollHeight;
        }
    }, [segments, displayMode]);

    // Initial load
    useEffect(() => {
        if (typeof window !== 'undefined') {
            const storedFontSize = parseInt(localStorage.getItem('fontSize') || "24");
            const storedMaxLines = parseInt(localStorage.getItem('maxLines') || "3");

            setFontSize(storedFontSize);
            setMaxLines(storedMaxLines);

            // Auto-resize on startup
            setTimeout(() => {
                updateWindowHeight(storedFontSize, storedMaxLines, 'bilingual');
            }, 200);
        }
    }, []);

    // Event Listeners
    useEffect(() => {
        let unlistenLock: UnlistenFn | undefined;
        let unlistenSpeech: UnlistenFn | undefined;
        let unlistenSettings: UnlistenFn | undefined;
        let unlistenTranscript: UnlistenFn | undefined;

        const initListeners = async () => {
            unlistenLock = await safeListen<boolean>('lock-state-changed', (event) => {
                setIsClickThrough(event.payload);
            });

            unlistenSpeech = await safeListen<boolean>('speech-detected', (event) => {
                if (event.payload) {
                    setIsSpeechDetected(true);
                    if (speechTimeoutRef.current) clearTimeout(speechTimeoutRef.current);
                    speechTimeoutRef.current = setTimeout(() => setIsSpeechDetected(false), 200);
                }
            });

            unlistenSettings = await safeListen<{ key: string, value: string }>('setting-changed', (event) => {
                const { key, value } = event.payload;
                switch (key) {
                    case 'fontSize':
                        const newSize = parseInt(value);
                        setFontSize(newSize);
                        updateWindowHeight(newSize, maxLines, displayMode);
                        break;
                    case 'opacity': setOpacity(parseFloat(value)); break;
                    case 'maxLines':
                        const newLines = parseInt(value);
                        setMaxLines(newLines);
                        updateWindowHeight(fontSize, newLines, displayMode);
                        break;
                    case 'displayMode':
                        setDisplayMode(value as DisplayMode);
                        break;
                }
            });

            unlistenTranscript = await safeListen<string>('transcript-update', (event) => {
                try {
                    const data = JSON.parse(event.payload);
                    if (data.type === 'error') return;

                    setSegments(prev => {
                        // If raw transcript is empty, it means the segment was silence/noise. Remove it.
                        if (data.type === 'raw' && (!data.content || data.content.trim() === '')) {
                            return prev.filter(s => s.id !== data.id);
                        }

                        const idx = prev.findIndex(s => s.id === data.id);
                        const newSeg: Segment = {
                            id: data.id,
                            content: data.content,
                            translated: data.translated,
                            isPolished: data.type === 'polished',
                            isPartial: data.type === 'partial'
                        };

                        if (idx !== -1) {
                            const copy = [...prev];
                            copy[idx] = newSeg;
                            return copy;
                        } else {
                            return [...prev, newSeg];
                        }
                    });
                } catch (e) {
                    console.error("Failed to parse transcript update:", e);
                }
            });
        };

        initListeners();

        return () => {
            if (unlistenLock) unlistenLock();
            if (unlistenSpeech) unlistenSpeech();
            if (unlistenSettings) unlistenSettings();
            if (unlistenTranscript) unlistenTranscript();
        };
    }, [fontSize, maxLines, displayMode]);

    // Safety: Unlock on ESC
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                setIsClickThrough(false);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, []);

    const linesPerArea = displayMode === 'bilingual' ? maxLines / 2 : maxLines;

    return (
        <>
            {/* Outermost Container: Transparent & Full Screen */}
            <div
                className={`w-screen h-screen flex flex-col overflow-hidden relative group transition-colors duration-300 ${isClickThrough ? 'pointer-events-none' : 'bg-transparent'}`}
                onMouseEnter={() => setIsHovered(true)}
                onMouseLeave={() => setIsHovered(false)}
            >
                {/* The Glass Lens - Floating with Margin */}
                <div
                    className={`flex-1 flex flex-col overflow-hidden rounded-3xl relative transition-all duration-500 ease-out border m-2 ${isClickThrough
                        ? 'border-transparent shadow-none'
                        : 'border-white/20 shadow-2xl backdrop-blur-2xl'
                        }`}
                    style={{ backgroundColor: `rgba(0, 0, 0, ${opacity})` }}
                >

                    {/* Title Bar Container - Floating, Rounded, Auto-Hide */}
                    {!isClickThrough && (
                        <div
                            data-tauri-drag-region
                            className={`absolute top-4 left-4 right-4 h-12 bg-white/10 backdrop-blur-md border border-white/20 rounded-full flex items-center justify-between px-4 select-none z-50 transition-all duration-300 ${isHovered ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4 pointer-events-none'}`}
                        >
                            {/* Left Controls */}
                            <div className="flex items-center gap-3 pointer-events-auto">
                                {/* VAD Indicator */}
                                <div className={`w-2.5 h-2.5 rounded-full transition-all duration-200 ${isSpeechDetected ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.8)] scale-110' : 'bg-white/20 scale-100'}`} />

                                {/* Record Button */}
                                <button
                                    onMouseDown={(e) => e.stopPropagation()}
                                    onClick={(e) => { e.stopPropagation(); toggleRecording(); }}
                                    className={`w-8 h-8 rounded-full flex items-center justify-center transition-all duration-300 shadow-lg ${isRecording ? 'bg-red-500/80 hover:bg-red-500' : 'bg-white/20 hover:bg-white/30'}`}
                                    title={isRecording ? "Stop Recording" : "Start Recording"}
                                >
                                    {isRecording ? <Square className="h-3 w-3 text-white fill-current" /> : <Mic className="h-4 w-4 text-white" />}
                                </button>
                            </div>

                            {/* Right Controls */}
                            <div className="flex items-center gap-2 pointer-events-auto">
                                {/* Template Selector */}
                                <div className="relative group/template pointer-events-auto mr-1" title="Select Meeting Template">
                                    <FileText className="h-3 w-3 text-white/70 absolute left-2 top-1/2 -translate-y-1/2 pointer-events-none" />
                                    <select
                                        value={templateName}
                                        onChange={(e) => setTemplateName(e.target.value)}
                                        className="pl-7 pr-2 py-1 bg-white/10 text-white/90 text-[10px] rounded-full border border-white/10 appearance-none hover:bg-white/20 focus:outline-none focus:ring-1 focus:ring-white/30 cursor-pointer w-24 truncate"
                                        onClick={(e) => e.stopPropagation()}
                                        onMouseDown={(e) => e.stopPropagation()}
                                        disabled={isRecording}
                                    >
                                        <option value="general" className="bg-gray-900 text-white">General</option>
                                        <option value="sales" className="bg-gray-900 text-white">Sales (BANT)</option>
                                        <option value="hr" className="bg-gray-900 text-white">HR (STAR)</option>
                                        <option value="tech" className="bg-gray-900 text-white">Tech (Decision)</option>
                                    </select>
                                </div>

                                {/* Click Through Toggle */}
                                <button
                                    onMouseDown={(e) => e.stopPropagation()}
                                    onClick={(e) => { e.stopPropagation(); toggleClickThrough(); }}
                                    className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full transition-colors"
                                    title="Lock / Click-Through"
                                >
                                    <Lock className="h-4 w-4" />
                                </button>

                                {/* History */}
                                <button
                                    onMouseDown={(e) => e.stopPropagation()}
                                    onClick={(e) => { e.stopPropagation(); openHistory(); }}
                                    className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full transition-colors"
                                    title="History"
                                >
                                    <Clock className="h-4 w-4" />
                                </button>

                                {/* Settings */}
                                <button
                                    onMouseDown={(e) => e.stopPropagation()}
                                    onClick={(e) => { e.stopPropagation(); openSettings(); }}
                                    className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full transition-colors"
                                >
                                    <Settings className="h-4 w-4" />
                                </button>

                                {/* Minimize & Close (Desktop Only) */}
                                {isDesktop && (
                                    <div className="flex gap-2 ml-3 pl-3 border-l border-white/10">
                                        <button
                                            onMouseDown={(e) => e.stopPropagation()}
                                            onClick={(e) => { e.stopPropagation(); minimizeWindow(); }}
                                            className="w-3 h-3 rounded-full bg-yellow-500/80 hover:bg-yellow-500 shadow-inner"
                                            title="Minimize"
                                        />
                                        <button
                                            onMouseDown={(e) => e.stopPropagation()}
                                            onClick={(e) => { e.stopPropagation(); closeWindow(); }}
                                            className="w-3 h-3 rounded-full bg-red-500/80 hover:bg-red-500 shadow-inner"
                                            title="Close"
                                        />
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Content Area */}
                    <div
                        className={`flex-1 flex flex-col p-6 gap-4 select-none ${!isClickThrough ? 'mt-14' : ''}`}
                        style={{
                            fontSize: `${fontSize}px`,
                            lineHeight: '1.6',
                            textShadow: '0 2px 4px rgba(0,0,0,0.8)'
                        }}
                    >
                        {/* Original Text Area - With Fading Mask */}
                        {displayMode !== 'translated' && (
                            <div
                                ref={scrollRefOriginal}
                                className="overflow-y-auto [&::-webkit-scrollbar]:hidden scroll-smooth"
                                style={{
                                    height: `${fontSize * 1.6 * linesPerArea}px`,
                                    maskImage: 'linear-gradient(to bottom, transparent 0%, black 25%, black 100%)',
                                    WebkitMaskImage: 'linear-gradient(to bottom, transparent 0%, black 25%, black 100%)'
                                }}
                            >
                                <div className="flex flex-wrap content-end min-h-full pb-2">
                                    {segments.map((seg) => (
                                        <span
                                            key={seg.id}
                                            className={`mr-2 transition-colors duration-500 ${seg.isPartial ? 'text-white/60 italic' : (seg.isPolished ? 'text-blue-300' : 'text-white')}`}
                                        >
                                            {seg.content}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Translated Text Area - With Fading Mask */}
                        {displayMode !== 'original' && (
                            <div
                                ref={scrollRefTranslated}
                                className="overflow-y-auto [&::-webkit-scrollbar]:hidden border-t border-white/10 pt-4 scroll-smooth"
                                style={{
                                    height: `${(fontSize * 0.9) * 1.6 * linesPerArea}px`,
                                    fontSize: '0.9em',
                                    maskImage: 'linear-gradient(to bottom, transparent 0%, black 25%, black 100%)',
                                    WebkitMaskImage: 'linear-gradient(to bottom, transparent 0%, black 25%, black 100%)'
                                }}
                            >
                                <div className="flex flex-wrap content-start min-h-full">
                                    {segments.map((seg) => (
                                        <span
                                            key={seg.id}
                                            className={`mr-2 transition-colors duration-500 ${seg.isPartial ? 'text-white/50 italic' : 'text-white/90'}`}
                                        >
                                            {seg.translated || "..."}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Resize Handle */}
                    {!isClickThrough && isDesktop && (
                        <div
                            className="absolute bottom-0 right-0 w-6 h-6 cursor-nwse-resize z-50 flex items-end justify-end p-1 pointer-events-auto"
                            onMouseDown={onResizeStart}
                        >
                            <div className="w-3 h-3 border-r-2 border-b-2 border-white/30 rounded-br-sm group-hover:border-white/60 transition-colors" />
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}