"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Mic, Square, Settings, X, Minus, Maximize2, Play, Pause, AlertCircle } from "lucide-react";
import SettingsModal from "./components/SettingsModal";

// --- Configuration ---
const SAMPLE_RATE = 16000;
const WEBSOCKET_URL = "ws://127.0.0.1:8000/ws/transcribe";

type AudioSourceType = 'microphone' | 'system';
type DisplayMode = 'single' | 'dual';
type TransMode = 'zh_to_en' | 'en_to_zh';

type Segment = {
    id: string;
    content: string;
    translated?: string;
    isPolished: boolean;
    isPartial?: boolean;
};

// Add declaration for electronAPI
declare global {
    interface Window {
        electronAPI?: {
            minimize: () => void;
            maximize: () => void;
            close: () => void;
            setAlwaysOnTop: (flag: boolean) => void;
            setIgnoreMouseEvents: (flag: boolean) => void;
            setOpacity: (value: number) => void;
            getDesktopSources: () => Promise<any[]>;
            resizeWindowStart: (direction: string) => void;
            resizeWindowStop: () => void;
            resizeWindowContent: (size: { width?: number, height: number }) => void;
        };
    }
}

export default function Home() {
  // --- Global State ---
  const [isRecording, setIsRecording] = useState(false);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [status, setStatus] = useState<"idle" | "connecting" | "recording" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");
  
  // --- Settings State (Persisted) ---
  const [audioSource, setAudioSource] = useState<AudioSourceType>('microphone');
  const [displayMode, setDisplayMode] = useState<DisplayMode>('dual');
  const [transMode, setTransMode] = useState<TransMode>('zh_to_en');
  const [initialPrompt, setInitialPrompt] = useState<string>("");
  const [fontSize, setFontSize] = useState<number>(24); // Increased default for subtitle view
  const [opacity, setOpacity] = useState<number>(0.6); // Background opacity
  const [maxLines, setMaxLines] = useState<number>(3); // Default 3 lines

  // --- Auto-Resize Logic ---
  useEffect(() => {
      if (typeof window !== 'undefined' && window.electronAPI && window.electronAPI.resizeWindowContent) {
          const lineHeightMultiplier = 1.6; // Empirically determined for line-height 1.5 and some buffer
          const headerHeight = 40; // Title bar height
          const paddingOuter = 6 * 2; // p-1.5 on outer container is 6px per side = 12px total vertical
          const paddingInner = 4 * 2; // p-4 on inner subtitle content area = 16px per side = 32px total vertical
          
          // Calculate desired height for a single line of text
          const singleLineVisualHeight = fontSize * lineHeightMultiplier;
          
          let contentAreaHeight = 0;
          if (displayMode === 'dual') {
              // Dual mode: maxLines for original + maxLines for translated
              contentAreaHeight = (singleLineVisualHeight * maxLines) * 2;
          } else {
              // Single mode: maxLines for original
              contentAreaHeight = singleLineVisualHeight * maxLines;
          }

          const totalHeight = Math.ceil(headerHeight + paddingOuter + paddingInner + contentAreaHeight);
          
          window.electronAPI.resizeWindowContent({ height: totalHeight });
      }
  }, [fontSize, maxLines, displayMode]);

  // --- UI State ---
  const [isElectron, setIsElectron] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  // --- Refs ---
  const socketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioQueueRef = useRef<ArrayBuffer[]>([]);
  const isRecordingRef = useRef(false);
  
  const scrollRef = useRef<HTMLDivElement>(null); // This will now control the whole content area scrolling
  const scrollRefOriginal = useRef<HTMLDivElement>(null); // For dual mode original
  const scrollRefTranslated = useRef<HTMLDivElement>(null); // For dual mode translated

  // --- Initialization & Persistence ---
  useEffect(() => {
      // Check Electron
      if (typeof window !== 'undefined' && window.electronAPI) {
          setIsElectron(true);
      }
      
      // Load Settings
      if (typeof window !== 'undefined') {
          setInitialPrompt(localStorage.getItem('initialPrompt') || "");
          setFontSize(parseInt(localStorage.getItem('fontSize') || "24"));
          setOpacity(parseFloat(localStorage.getItem('opacity') || "0.6"));
          setMaxLines(parseInt(localStorage.getItem('maxLines') || "3"));
          // Audio source & modes reset on reload usually, or can persist them too
      }
  }, []);

  // Save Settings
  useEffect(() => { if (typeof window !== 'undefined') localStorage.setItem('initialPrompt', initialPrompt); }, [initialPrompt]);
  useEffect(() => { if (typeof window !== 'undefined') localStorage.setItem('fontSize', fontSize.toString()); }, [fontSize]);
  useEffect(() => { if (typeof window !== 'undefined') localStorage.setItem('maxLines', maxLines.toString()); }, [maxLines]);
  useEffect(() => { 
      if (typeof window !== 'undefined') localStorage.setItem('opacity', opacity.toString()); 
      // Note: We don't call window.electronAPI.setOpacity here anymore, 
      // because we handle opacity via CSS background-color for "Immersive Mode"
      // If we want the *whole window* to be transparent (including text), we use setOpacity.
      // But usually for subtitles, we want text opaque, background transparent.
      // So we will stick to CSS rgba().
  }, [opacity]);

  // Send config on change
  useEffect(() => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
          const source_lang = transMode === 'zh_to_en' ? 'zh' : 'en';
          const target_lang = transMode === 'zh_to_en' ? 'en' : 'zh';
          socketRef.current.send(JSON.stringify({
              type: "config",
              source_lang,
              target_lang,
              initial_prompt: initialPrompt
          }));
      }
  }, [transMode, initialPrompt]);

  // Auto Scroll - now applies to the actual scrollable content area
  useEffect(() => {
    // Determine which scrollRef to use based on displayMode
    const currentScrollRef = displayMode === 'dual' ? scrollRefOriginal : scrollRef;
    if (currentScrollRef.current) {
        currentScrollRef.current.scrollTop = currentScrollRef.current.scrollHeight;
    }
    // Also for translated part in dual mode
    if (displayMode === 'dual' && scrollRefTranslated.current) {
        scrollRefTranslated.current.scrollTop = scrollRefTranslated.current.scrollHeight;
    }
  }, [segments, displayMode, fontSize, maxLines]);

  // --- Audio Logic (Identical to previous, condensed) ---
  const processAudio = useCallback((audioProcessingEvent: AudioProcessingEvent) => {
    if (!isRecordingRef.current) return;
    const inputData = audioProcessingEvent.inputBuffer.getChannelData(0);
    let maxAmp = 0;
    const pcmData = new Int16Array(inputData.length);
    for (let i = 0; i < inputData.length; i++) {
      const s = Math.max(-1, Math.min(1, inputData[i]));
      if (Math.abs(s) > maxAmp) maxAmp = Math.abs(s); 
      pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    if (maxAmp < 0.001) return; // Silence filter

    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
        if (audioQueueRef.current.length > 0) {
            audioQueueRef.current.forEach(chunk => socket.send(chunk));
            audioQueueRef.current = [];
        }
        socket.send(pcmData.buffer);
    } else {
        audioQueueRef.current.push(pcmData.buffer);
    }
  }, []);

  const initAudio = async () => {
      let stream: MediaStream;
      if (isElectron && audioSource === 'system') {
          try {
              const sources = await window.electronAPI!.getDesktopSources();
              const source = sources.find((s: any) => s.name === 'Entire Screen' || s.name === 'Screen 1') || sources[0];
              stream = await navigator.mediaDevices.getUserMedia({
                  audio: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: source.id } } as any,
                  video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: source.id } } as any
              });
          } catch (err: any) { throw new Error(`System Audio Error: ${err.message}`); }
      } else if (audioSource === 'system') {
          // @ts-ignore
          stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: { sampleRate: SAMPLE_RATE, echoCancellation: false } });
      } else {
          stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: SAMPLE_RATE, echoCancellation: false } });
      }
      streamRef.current = stream;
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: SAMPLE_RATE });
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = processAudio;
      processorRef.current = processor;
      source.connect(processor);
      processor.connect(audioContext.destination);
      if (audioContext.state === 'suspended') await audioContext.resume();
      // Stop video track if system audio
      if (audioSource === 'system') stream.getVideoTracks().forEach(t => t.stop());
  };

  const startRecording = async () => {
    setErrorMessage("");
    setStatus("connecting");
    isRecordingRef.current = true;
    audioQueueRef.current = [];
    try {
      await initAudio();
      const socket = new WebSocket(WEBSOCKET_URL);
      socketRef.current = socket;
      socket.onopen = () => {
        const s_lang = transMode === 'zh_to_en' ? 'zh' : 'en';
        const t_lang = transMode === 'zh_to_en' ? 'en' : 'zh';
        socket.send(JSON.stringify({ type: "config", source_lang: s_lang, target_lang: t_lang, initial_prompt: initialPrompt }));
        if (audioQueueRef.current.length > 0) {
            audioQueueRef.current.forEach(chunk => socket.send(chunk));
            audioQueueRef.current = [];
        }
        setStatus("recording");
        setIsRecording(true);
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        setSegments(prev => {
            const idx = prev.findIndex(s => s.id === message.id);
            const newSeg = { id: message.id, content: message.content, translated: message.translated, isPolished: message.type === "polished", isPartial: message.type === "partial" };
            if (message.type === "error") return prev;
            if (idx !== -1) { const copy = [...prev]; copy[idx] = newSeg; return copy; }
            return [...prev, newSeg];
        });
      };
      socket.onerror = (e) => { console.error(e); setStatus("error"); setErrorMessage("Connection Error"); stopRecording(); };
      socket.onclose = () => { if (isRecordingRef.current) stopRecording(); };
    } catch (err: any) {
      console.error(err);
      setErrorMessage(err.message || "Failed to start");
      setStatus("error");
      stopRecording();
    }
  };

  const stopRecording = () => {
    setIsRecording(false);
    isRecordingRef.current = false;
    setStatus("idle");
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    if (sourceRef.current) { sourceRef.current.disconnect(); sourceRef.current = null; }
    if (processorRef.current) { processorRef.current.disconnect(); processorRef.current = null; }
    if (audioContextRef.current) { audioContextRef.current.close(); audioContextRef.current = null; }
    if (socketRef.current) { if (socketRef.current.readyState === WebSocket.OPEN) socketRef.current.close(); socketRef.current = null; }
  };

  const toggleRecording = () => {
      if (isRecording) stopRecording();
      else startRecording();
  };

  // --- Rendering ---
  const getText = (seg: Segment, type: 'original' | 'translated') => {
      if (type === 'translated') return seg.translated || (seg.isPolished ? "" : (seg.isPartial ? "..." : "")); 
      return seg.content;
  };

  const handleResizeStart = (direction: string) => {
        if (typeof window !== 'undefined' && (window as any).ipcRenderer) {
             (window as any).ipcRenderer.send('resize-window-start', direction);
        }
        // Fallback or for standard web: do nothing or simulate
        const stopResize = () => {
            if (typeof window !== 'undefined' && (window as any).ipcRenderer) {
                (window as any).ipcRenderer.send('resize-window-stop');
            }
            window.removeEventListener('mouseup', stopResize);
        };
        window.addEventListener('mouseup', stopResize);
  };

  return (
    <>
        {/* Main Immersive Window Container with Padding for Resize Handles */}
        <div 
            className="w-screen h-screen flex flex-col overflow-hidden relative group p-1.5" // Added p-1.5 (6px) padding for resize edges
            style={{ backgroundColor: 'rgba(0, 0, 0, 0.01)' }} // Trick: 1% opacity to catch mouse events for resizing (hit-test) instead of falling through to desktop
            onMouseEnter={() => setIsHovered(true)} // Hover anywhere in the window triggers title bar
            onMouseLeave={() => setIsHovered(false)}
        >
            {/* --- Manual Resize Handles (Transparent but Interactive) --- */}
            {/* Top */}
            <div className="absolute top-0 left-2 right-2 h-2 cursor-ns-resize z-[100]" onMouseDown={() => handleResizeStart('top')} style={{ WebkitAppRegion: 'no-drag' } as any} />
            {/* Bottom */}
            <div className="absolute bottom-0 left-2 right-2 h-2 cursor-ns-resize z-[100]" onMouseDown={() => handleResizeStart('bottom')} style={{ WebkitAppRegion: 'no-drag' } as any} />
            {/* Left */}
            <div className="absolute top-2 bottom-2 left-0 w-2 cursor-ew-resize z-[100]" onMouseDown={() => handleResizeStart('left')} style={{ WebkitAppRegion: 'no-drag' } as any} />
            {/* Right */}
            <div className="absolute top-2 bottom-2 right-0 w-2 cursor-ew-resize z-[100]" onMouseDown={() => handleResizeStart('right')} style={{ WebkitAppRegion: 'no-drag' } as any} />
            {/* Corners */}
            <div className="absolute top-0 left-0 w-4 h-4 cursor-nwse-resize z-[101]" onMouseDown={() => handleResizeStart('top-left')} style={{ WebkitAppRegion: 'no-drag' } as any} />
            <div className="absolute top-0 right-0 w-4 h-4 cursor-nesw-resize z-[101]" onMouseDown={() => handleResizeStart('top-right')} style={{ WebkitAppRegion: 'no-drag' } as any} />
            <div className="absolute bottom-0 left-0 w-4 h-4 cursor-nesw-resize z-[101]" onMouseDown={() => handleResizeStart('bottom-left')} style={{ WebkitAppRegion: 'no-drag' } as any} />
            <div className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize z-[101]" onMouseDown={() => handleResizeStart('bottom-right')} style={{ WebkitAppRegion: 'no-drag' } as any} />


            {/* The Actual Visible Content Area (The "Sunglasses" Lens) */}
            <div 
                className="flex-1 flex flex-col overflow-hidden rounded-lg relative transition-colors duration-300"
                style={{ backgroundColor: `rgba(0, 0, 0, ${opacity})` }} // Inner content has the opacity
                onMouseEnter={() => setIsHovered(true)} // Hover on content area shows title bar
                onMouseLeave={() => setIsHovered(false)}
            >
            
            {/* Title Bar (Hover to Show) - Opaque */}
            <div 
                className={`absolute top-0 left-0 right-0 h-10 bg-neutral-900 flex items-center justify-between px-3 select-none z-50 transition-opacity duration-300 ${isHovered || showSettings ? 'opacity-100' : 'opacity-0'}`}
                style={{ WebkitAppRegion: 'drag' } as any}
            >
                <div className="flex items-center gap-2">
                    <span className="text-white font-bold text-sm tracking-wide">TranscriptHub</span>
                    {/* Record/Stop Button in Title Bar */}
                    <button 
                        onClick={(e) => { e.stopPropagation(); toggleRecording(); }}
                        className={`p-1.5 rounded-full transition-colors ${isRecording ? 'bg-red-500 hover:bg-red-600' : 'bg-green-500 hover:bg-green-600'}`}
                        style={{ WebkitAppRegion: 'no-drag' } as any}
                        title={isRecording ? "Stop Recording" : "Start Recording"}
                    >
                        {isRecording ? <Square className="h-3 w-3 text-white fill-current" /> : <Mic className="h-3 w-3 text-white fill-current" />}
                    </button>
                </div>

                <div className="flex items-center gap-2" style={{ WebkitAppRegion: 'no-drag' } as any}>
                    {/* Settings Button */}
                    <button 
                        onClick={() => setShowSettings(true)}
                        className="p-1.5 text-gray-300 hover:text-white hover:bg-white/10 rounded-md transition-colors"
                        title="Settings"
                    >
                        <Settings className="h-4 w-4" />
                    </button>
                    
                    {status === 'connecting' && <span className="text-xs text-yellow-400 animate-pulse">Connecting...</span>}
                    {status === 'error' && <span className="text-xs text-red-400">Error</span>}

                    {/* Window Controls */}
                    {isElectron && (
                        <div className="flex gap-1.5 ml-2 border-l border-white/20 pl-2">
                            <button onClick={() => window.electronAPI?.minimize()} className="p-1 hover:bg-white/10 rounded"><Minus className="h-3 w-3 text-white" /></button>
                            <button onClick={() => window.electronAPI?.maximize()} className="p-1 hover:bg-white/10 rounded"><Maximize2 className="h-3 w-3 text-white" /></button>
                            <button onClick={() => window.electronAPI?.close()} className="p-1 hover:bg-red-500 rounded"><X className="h-3 w-3 text-white" /></button>
                        </div>
                    )}
                </div>
            </div>

            {/* Subtitle Content Area */}
            {/* New structure for dual-language display */}
            <div 
                className="flex-1 flex flex-col p-4 select-none" // select-none added here
                style={{ 
                    fontSize: `${fontSize}px`,
                    lineHeight: '1.5',
                }}
            >
                
                {/* Dual Language Display Area */}
                {displayMode === 'dual' ? (
                    <div className="flex-1 flex flex-col justify-end">
                        {/* Original Language Part (Top) - Flowing Text */}
                        <div 
                            ref={scrollRefOriginal} 
                            className="flex-1 overflow-y-auto pb-2 border-b border-white/10 flex flex-wrap content-end"
                            style={{ maxHeight: `${fontSize * 1.6 * maxLines}px` }} // Max height for original part
                        > 
                            {segments.slice(-maxLines).map((seg) => (
                                <span key={seg.id} className={`mr-2 inline-block text-shadow-md font-medium ${seg.isPartial ? 'text-white/70' : 'text-white'}`}>
                                    {seg.content}
                                </span>
                            ))}
                        </div>
                        {/* Translated Language Part (Bottom) - Flowing Text */}
                        <div 
                            ref={scrollRefTranslated}
                            className="flex-1 overflow-y-auto pt-2 flex flex-wrap content-start"
                            style={{ maxHeight: `${fontSize * 1.6 * maxLines}px` }} // Max height for translated part
                        > 
                            {segments.slice(-maxLines).map((seg) => (
                                <span key={seg.id} className={`mr-2 inline-block text-shadow-md font-medium text-[0.85em] ${seg.isPartial ? 'text-yellow-200/70' : 'text-yellow-300'}`}>
                                    {seg.translated || (seg.isPolished ? "" : "...")}
                                </span>
                            ))}
                        </div>
                    </div>
                ) : (
                    /* Single Language Display Area - Flowing Text */
                    <div 
                        ref={scrollRef} 
                        className="flex-1 overflow-y-auto flex flex-wrap content-end pb-2"
                        style={{ maxHeight: `${fontSize * 1.6 * maxLines}px` }} // Max height for single part
                    >
                        {segments.slice(-maxLines).map((seg) => (
                            <span key={seg.id} className={`mr-2 inline-block text-shadow-md font-medium ${seg.isPartial ? 'text-white/70' : 'text-white'}`}>
                                {seg.content}
                            </span>
                        ))}
                    </div>
                )}
            </div>
            </div>
        </div>

        {/* Settings Modal */}
        <SettingsModal 
            isOpen={showSettings}
            onClose={() => setShowSettings(false)}
            isRecording={isRecording}
            audioSource={audioSource} setAudioSource={setAudioSource}
            displayMode={displayMode} setDisplayMode={setDisplayMode}
            transMode={transMode} setTransMode={setTransMode}
            fontSize={fontSize} setFontSize={setFontSize}
            opacity={opacity} setOpacity={setOpacity}
            maxLines={maxLines} setMaxLines={setMaxLines}
            initialPrompt={initialPrompt} setInitialPrompt={setInitialPrompt}
            isElectron={isElectron}
        />
    </>
  );
}
