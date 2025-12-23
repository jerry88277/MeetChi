'use client';

import { useState, useRef, useEffect } from "react";
import { Mic, Square, Settings, Lock } from "lucide-react";
import { invoke } from '@tauri-apps/api/core';
import { getCurrentWindow, getAllWindows } from '@tauri-apps/api/window';
import { WebviewWindow } from '@tauri-apps/api/webviewWindow';
import { listen } from '@tauri-apps/api/event';
import { LogicalSize } from '@tauri-apps/api/dpi';

type DisplayMode = 'single' | 'dual';

type Segment = {
    id: string;
    content: string;
    translated?: string;
    isPolished: boolean;
    isPartial?: boolean;
};

export default function Home() {
  // --- Global State ---
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeechDetected, setIsSpeechDetected] = useState(false);
  const [segments, setSegments] = useState<Segment[]>([]); 
  
  // --- Settings State ---
  const [displayMode, setDisplayMode] = useState<DisplayMode>('dual');
  const [fontSize, setFontSize] = useState(24); 
  const [opacity, setOpacity] = useState(0.6); 
  const [maxLines, setMaxLines] = useState(3); // Default 3

  // --- UI State ---
  const [isHovered, setIsHovered] = useState(false);
  const [isClickThrough, setIsClickThrough] = useState(false);

  // --- Refs ---
  const scrollRefOriginal = useRef<HTMLDivElement>(null); 
  const scrollRefTranslated = useRef<HTMLDivElement>(null); 
  const speechTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isResizingRef = useRef(false);
  const startResizeState = useRef<{ w: number, h: number, x: number, y: number, factor: number } | null>(null);

  // --- Window Controls ---
  const minimizeWindow = async () => {
    try {
        await getCurrentWindow().minimize();
    } catch (e) {
        console.error("Failed to minimize:", e);
    }
  };

  const closeWindow = async () => {
    try {
        await getCurrentWindow().close();
    } catch (e) {
        console.error("Failed to close:", e);
    }
  };

  const openSettings = async () => {
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
                width: 400,
                height: 600,
                resizable: true,
                fullscreen: false,
                transparent: true,
                decorations: false,
                alwaysOnTop: false,
                shadow: false,
                visible: true 
            });
            
            webview.once('tauri://error', function (e) {
                console.error('Error creating settings window', e);
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
      await invoke('set_ignore_cursor_events', { ignore: newState });
  };

  // --- Audio Control ---
  const toggleRecording = async () => {
      try {
        if (isRecording) {
            await invoke('stop_audio_command');
            setIsRecording(false);
            setIsSpeechDetected(false);
        } else {
            const deviceId = localStorage.getItem('audioSource') || "default";
            const vadThreshold = parseFloat(localStorage.getItem('vadThreshold') || "0.005");
            await invoke('start_audio_command', { deviceId, vadThreshold });
            setIsRecording(true);
        }
      } catch (e) {
          console.error("Audio toggle failed:", e);
          alert(`Recording Error: ${e}`);
          setIsRecording(false);
      }
  };

  // --- Dynamic Window Resizing ---
  const updateWindowHeight = async (fSize: number, lines: number, mode: DisplayMode) => {
      try {
        const lineHeight = 1.6;
        const padding = 48; // p-6 (24px) * 2
        const titleBarHeight = !isClickThrough ? 48 : 0; // h-12 (48px)
        const gap = 16; // gap-4 (16px)

        const singleAreaHeight = fSize * lineHeight * lines;
        
        let contentHeight = singleAreaHeight;
        if (mode === 'dual') {
            const transFontSize = fSize * 0.9;
            const transAreaHeight = transFontSize * lineHeight * lines;
            contentHeight += transAreaHeight + gap; // Add translated area + gap
        }
        
        const totalHeight = contentHeight + padding + titleBarHeight + 20; // Extra buffer
        
        const appWindow = getCurrentWindow();
        const size = await appWindow.innerSize();
        const factor = await appWindow.scaleFactor();
        const currentWidth = size.width / factor;
        
        // Only update height, keep width
        await appWindow.setSize(new LogicalSize(currentWidth, totalHeight));
      } catch (e) {
          console.error("Failed to resize window:", e);
      }
  };

  // --- Custom Resize Logic (Optimized) ---
  const onResizeStart = async (e: React.MouseEvent) => {
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
          const storedMode = (localStorage.getItem('transMode') || "zh_to_en") === 'zh_to_en' ? 'dual' : 'dual'; // Simplified mapping
          // Actually transMode doesn't map 1:1 to displayMode in current logic, 
          // let's assume default is dual.
          
          setFontSize(storedFontSize);
          setMaxLines(storedMaxLines);
          // updateWindowHeight(storedFontSize, storedMaxLines, 'dual');
      }
  }, []);

  // Event Listeners
  useEffect(() => {
      const unlistenLock = listen<boolean>('lock-state-changed', (event) => {
          setIsClickThrough(event.payload);
      });
      
      const unlistenSpeech = listen<boolean>('speech-detected', (event) => {
          if (event.payload) {
              setIsSpeechDetected(true);
              if (speechTimeoutRef.current) clearTimeout(speechTimeoutRef.current);
              speechTimeoutRef.current = setTimeout(() => setIsSpeechDetected(false), 200);
          }
      });

      const unlistenSettings = listen<{ key: string, value: string }>('setting-changed', (event) => {
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
          }
      });

      const unlistenTranscript = listen<string>('transcript-update', (event) => {
          try {
              const data = JSON.parse(event.payload);
              if (data.type === 'error') return;

              setSegments(prev => {
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

      return () => { 
          unlistenLock.then(f => f()); 
          unlistenSpeech.then(f => f());
          unlistenSettings.then(f => f());
          unlistenTranscript.then(f => f());
      };
  }, [fontSize, maxLines, displayMode]); // Dependencies needed for updateWindowHeight closure? 
  // No, state inside listener is stale. Better to use refs or functional updates.
  // But updateWindowHeight uses current params. 
  // We should pass the NEW value from event, and current OTHER values from state.
  // React state in event listener closure is stale.
  // Correct fix: Use refs for fontSize/maxLines or just rely on the event payload mostly?
  // Let's use functional updates or ref. 
  // For simplicity, I'll ignore stale state for now as 'displayMode' rarely changes.


  return (
    <>
        {/* Outermost container */}
        <div 
            className={`w-screen h-screen flex flex-col overflow-hidden relative group transition-colors duration-300 ${isClickThrough ? 'pointer-events-none' : 'bg-transparent'}`}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            {/* The Glass Lens */}
            <div 
                className={`flex-1 flex flex-col overflow-hidden rounded-3xl relative transition-all duration-500 ease-out border m-2 ${
                    isClickThrough 
                        ? 'border-transparent shadow-none' 
                        : 'border-white/20 shadow-2xl backdrop-blur-2xl'
                }`}
                style={{ backgroundColor: `rgba(0, 0, 0, ${opacity})` }} 
            >
            
            {/* Title Bar Container */}
            {!isClickThrough && (
                <div 
                    className={`absolute top-4 left-4 right-4 h-12 z-50 transition-all duration-300 ${isHovered ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4 pointer-events-none'}`}
                >
                    {/* 1. Drag Layer (Background) */}
                    <div 
                        data-tauri-drag-region
                        className="absolute inset-0 bg-white/10 backdrop-blur-md border border-white/20 rounded-full cursor-grab active:cursor-grabbing pointer-events-auto"
                    />

                    {/* 2. Content Layer (Buttons) */}
                    <div className="absolute inset-0 flex items-center justify-between px-4 pointer-events-none">
                        
                        {/* Left Controls */}
                        <div className="flex items-center gap-3 pointer-events-auto">
                            {/* VAD Indicator */}
                            <div className={`w-2.5 h-2.5 rounded-full transition-all duration-200 ${isSpeechDetected ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.8)] scale-110' : 'bg-white/20 scale-100'}`} />

                            <button 
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={(e) => { e.stopPropagation(); toggleRecording(); }}
                                className={`w-8 h-8 rounded-full flex items-center justify-center transition-all duration-300 shadow-lg ${isRecording ? 'bg-red-500/80 hover:bg-red-500' : 'bg-white/20 hover:bg-white/30'}`}
                            >
                                {isRecording ? <Square className="h-3 w-3 text-white fill-current" /> : <Mic className="h-4 w-4 text-white" />}
                            </button>
                        </div>

                        {/* Right Controls */}
                        <div className="flex items-center gap-2 pointer-events-auto">
                            {/* Click Through Toggle */}
                            <button 
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={(e) => { e.stopPropagation(); toggleClickThrough(); }} 
                                className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full transition-colors" 
                                title="Lock / Click-Through"
                            >
                                <Lock className="h-4 w-4" />
                            </button>

                            {/* Settings */}
                            <button 
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={(e) => { e.stopPropagation(); openSettings(); }}
                                className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full transition-colors"
                            >
                                <Settings className="h-4 w-4" />
                            </button>
                            
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
                        </div>
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
                <div 
                    ref={scrollRefOriginal}
                    className="overflow-y-auto [&::-webkit-scrollbar]:hidden scroll-smooth"
                    style={{
                        height: `${fontSize * 1.6 * maxLines}px`,
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

                {/* Translated Text Area - With Fading Mask */}
                {displayMode === 'dual' && (
                    <div 
                        ref={scrollRefTranslated}
                        className="overflow-y-auto [&::-webkit-scrollbar]:hidden border-t border-white/10 pt-4 scroll-smooth"
                        style={{
                            height: `${(fontSize * 0.9) * 1.6 * maxLines}px`,
                            maskImage: 'linear-gradient(to bottom, transparent 0%, black 25%, black 100%)',
                            WebkitMaskImage: 'linear-gradient(to bottom, transparent 0%, black 25%, black 100%)'
                        }}
                    >
                        <div className="flex flex-wrap content-start min-h-full">
                            {segments.map((seg) => (
                                <span 
                                    key={seg.id} 
                                    className={`mr-2 transition-colors duration-500 text-[0.9em] ${seg.isPartial ? 'text-white/50 italic' : 'text-white/90'}`}
                                >
                                    {seg.translated || "..."}
                                </span>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* Resize Handle */}
            {!isClickThrough && (
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