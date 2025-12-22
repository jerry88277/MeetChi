"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Mic, Square, Settings, X, Minus, Maximize2, RefreshCw } from "lucide-react"; // RefreshCw for language swap
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
  const [fontSize, setFontSize] = useState<number>(24); 
  const [opacity, setOpacity] = useState<number>(0.6); 
  const [maxLines, setMaxLines] = useState<number>(3); 

  // --- UI State ---
  const [isElectron, setIsElectron] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  // --- Refs ---
  const socketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioWorkletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioQueueRef = useRef<ArrayBuffer[]>([]);
  const isRecordingRef = useRef(false);
  
  const scrollRefOriginal = useRef<HTMLDivElement>(null); 
  const scrollRefTranslated = useRef<HTMLDivElement>(null); 

  // --- Initialization & Persistence ---
  useEffect(() => {
      if (typeof window !== 'undefined' && window.electronAPI) {
          setIsElectron(true);
      }
      
      if (typeof window !== 'undefined') {
          setInitialPrompt(localStorage.getItem('initialPrompt') || "");
          setFontSize(parseInt(localStorage.getItem('fontSize') || "24"));
          setOpacity(parseFloat(localStorage.getItem('opacity') || "0.6"));
          setMaxLines(parseInt(localStorage.getItem('maxLines') || "3"));
      }
  }, []);

  useEffect(() => { if (typeof window !== 'undefined') localStorage.setItem('initialPrompt', initialPrompt); }, [initialPrompt]);
  useEffect(() => { if (typeof window !== 'undefined') localStorage.setItem('fontSize', fontSize.toString()); }, [fontSize]);
  useEffect(() => { if (typeof window !== 'undefined') localStorage.setItem('maxLines', maxLines.toString()); }, [maxLines]);
  useEffect(() => { if (typeof window !== 'undefined') localStorage.setItem('opacity', opacity.toString()); }, [opacity]);

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

  // Auto Scroll
  useEffect(() => {
    if (scrollRefOriginal.current) {
        scrollRefOriginal.current.scrollTop = scrollRefOriginal.current.scrollHeight;
    }
    if (scrollRefTranslated.current) {
        scrollRefTranslated.current.scrollTop = scrollRefTranslated.current.scrollHeight;
    }
  }, [segments, displayMode]);

  // --- Audio Logic ---
  const initAudio = async () => {
      let stream: MediaStream;
      if (isElectron && audioSource === 'system') {
          try {
              const sources = await window.electronAPI!.getDesktopSources();
              // Try to find screen 1 or default
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
      
      try {
        await audioContext.audioWorklet.addModule('/audio-worklet-processor.js');
        const audioWorkletNode = new AudioWorkletNode(audioContext, 'audio-pass-through-processor');
        audioWorkletNodeRef.current = audioWorkletNode;

        // Initialize Worklet
        audioWorkletNode.port.postMessage({ type: 'init', wasmFilePath: '/rnnoise-wasm/rnnoise.wasm', sampleRate: SAMPLE_RATE, frameSize: 480 });

        audioWorkletNode.port.onmessage = (event) => {
            if (event.data.type === 'initialized') { console.log('AudioWorklet Initialized'); return; }
            if (event.data.type === 'error') { console.error(event.data.error); return; }
            if (!isRecordingRef.current) return;

            const socket = socketRef.current;
            if (socket && socket.readyState === WebSocket.OPEN) {
                if (audioQueueRef.current.length > 0) {
                    audioQueueRef.current.forEach(chunk => socket.send(chunk));
                    audioQueueRef.current = [];
                }
                socket.send(event.data);
            } else {
                audioQueueRef.current.push(event.data);
            }
        };

        source.connect(audioWorkletNode);
        audioWorkletNode.connect(audioContext.destination);
      } catch (e) {
          console.error("AudioWorklet setup failed:", e);
          throw e;
      }

      if (audioContext.state === 'suspended') await audioContext.resume();
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
        setStatus("recording");
        setIsRecording(true);
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === "error") return;
        setSegments(prev => {
            const idx = prev.findIndex(s => s.id === message.id);
            const newSeg = { id: message.id, content: message.content, translated: message.translated, isPolished: message.type === "polished", isPartial: message.type === "partial" };
            if (idx !== -1) { const copy = [...prev]; copy[idx] = newSeg; return copy; }
            return [...prev, newSeg];
        });
      };
      socket.onerror = (e) => { 
          console.error("WebSocket Error:", e); 
          setStatus("error"); 
          setErrorMessage("WebSocket Connection Failed. Check Backend."); 
          stopRecording(); 
      };
      socket.onclose = () => { if (isRecordingRef.current) stopRecording(); };
    } catch (err: any) {
      console.error(err);
      setErrorMessage(err.message || "Failed to start recording");
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
    if (audioWorkletNodeRef.current) { audioWorkletNodeRef.current.disconnect(); audioWorkletNodeRef.current = null; }
    if (audioContextRef.current) { audioContextRef.current.close(); audioContextRef.current = null; }
    if (socketRef.current) { if (socketRef.current.readyState === WebSocket.OPEN) socketRef.current.close(); socketRef.current = null; }
  };

  const toggleRecording = () => {
      if (isRecording) stopRecording();
      else startRecording();
  };

  // --- Handlers ---
  const swapLanguages = () => {
      setTransMode(prev => prev === 'zh_to_en' ? 'en_to_zh' : 'zh_to_en');
  };

  return (
    <>
        {/* iOS 26 Liquid Glass Container */}
        {/* Outermost container must be FULL SCREEN and TRANSPARENT with NO padding to avoid border artifacts at window edges */}
        <div 
            className="w-screen h-screen flex flex-col overflow-hidden relative group bg-transparent"
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            {/* The Glass Lens - Floating with Margin */}
            <div 
                className="flex-1 flex flex-col overflow-hidden rounded-3xl relative transition-all duration-500 ease-out border border-white/20 shadow-2xl backdrop-blur-2xl m-2"
                style={{ backgroundColor: `rgba(255, 255, 255, ${opacity * 0.1})` }} 
            >
            
            {/* Title Bar - Floating Liquid Bar */}
            <div 
                className={`absolute top-4 left-4 right-4 h-12 bg-white/10 backdrop-blur-md border border-white/20 rounded-full flex items-center justify-between px-4 select-none z-50 transition-all duration-300 title-drag ${isHovered || showSettings ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4 pointer-events-none'}`}
            >
                <div className="flex items-center gap-3">
                    {/* Record Button */}
                    <button 
                        onClick={(e) => { e.stopPropagation(); toggleRecording(); }}
                        className={`w-8 h-8 rounded-full flex items-center justify-center transition-all duration-300 shadow-lg no-drag ${isRecording ? 'bg-red-500/80 hover:bg-red-500' : 'bg-white/20 hover:bg-white/30'}`}
                        title={isRecording ? "Stop Recording" : "Start Recording"}
                    >
                        {isRecording ? <Square className="h-3 w-3 text-white fill-current" /> : <Mic className="h-4 w-4 text-white" />}
                    </button>
                </div>

                <div className="flex items-center gap-2 no-drag">
                    {/* Swap Language */}
                    <button onClick={swapLanguages} className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full transition-colors" title="Swap Languages">
                        <RefreshCw className="h-4 w-4" />
                    </button>

                    {/* Settings */}
                    <button 
                        onClick={() => setShowSettings(true)}
                        className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full transition-colors"
                    >
                        <Settings className="h-4 w-4" />
                    </button>
                    
                    {/* Status Indicators */}
                    {status === 'connecting' && <div className="w-2 h-2 bg-yellow-400 rounded-full animate-pulse shadow-[0_0_10px_rgba(250,204,21,0.5)]"></div>}
                    {status === 'error' && <div className="w-2 h-2 bg-red-500 rounded-full shadow-[0_0_10px_rgba(239,68,68,0.5)]"></div>}

                    {/* Window Controls (Mac-style traffic lights) */}
                    {isElectron && (
                        <div className="flex gap-2 ml-3 pl-3 border-l border-white/10">
                            <button onClick={() => window.electronAPI?.minimize()} className="w-3 h-3 rounded-full bg-yellow-500/80 hover:bg-yellow-500 shadow-inner" />
                            <button onClick={() => window.electronAPI?.maximize()} className="w-3 h-3 rounded-full bg-green-500/80 hover:bg-green-500 shadow-inner" />
                            <button onClick={() => window.electronAPI?.close()} className="w-3 h-3 rounded-full bg-red-500/80 hover:bg-red-500 shadow-inner" />
                        </div>
                    )}
                </div>
            </div>

            {/* Content Area - Split View */}
            <div 
                className="flex-1 flex flex-col p-6 gap-4 select-none mt-14" // Push content down for title bar
                style={{ 
                    fontSize: `${fontSize}px`,
                    lineHeight: '1.6',
                    textShadow: '0 2px 10px rgba(0,0,0,0.3)' // Deep shadow for glass readability
                }}
            >
                {/* Original Text Area */}
                <div 
                    ref={scrollRefOriginal}
                    className="flex-1 overflow-y-auto [&::-webkit-scrollbar]:hidden mask-image-gradient-b" // Hide scrollbar
                >
                    <div className="flex flex-wrap content-end min-h-full pb-2">
                        {segments.map((seg) => (
                            <span 
                                key={seg.id} 
                                className={`mr-2 transition-colors duration-500 ${seg.isPartial ? 'text-white/40 italic' : (seg.isPolished ? 'text-blue-300' : 'text-white')}`}
                            >
                                {seg.content}
                            </span>
                        ))}
                    </div>
                </div>

                {/* Translated Text Area (Only in Dual Mode) */}
                {displayMode === 'dual' && (
                    <div 
                        ref={scrollRefTranslated}
                        className="flex-1 overflow-y-auto [&::-webkit-scrollbar]:hidden border-t border-white/10 pt-4"
                    >
                        <div className="flex flex-wrap content-start min-h-full">
                            {segments.map((seg) => (
                                <span 
                                    key={seg.id} 
                                    className={`mr-2 transition-colors duration-500 text-[0.9em] ${seg.isPartial ? 'text-white/30 italic' : 'text-white/80'}`}
                                >
                                    {seg.translated || (seg.isPolished ? "" : "...")}
                                </span>
                            ))}
                        </div>
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
            errorMessage={errorMessage} // Pass error message
            isElectron={isElectron}
        />
    </>
  );
}

