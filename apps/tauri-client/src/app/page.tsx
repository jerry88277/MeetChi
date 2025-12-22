'use client';

import { useState, useRef, useEffect } from "react";
import { Mic, Square, Settings, Lock } from "lucide-react";
import { invoke } from '@tauri-apps/api/core';
import { getCurrentWindow, getAllWindows } from '@tauri-apps/api/window';
import { listen } from '@tauri-apps/api/event';

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
  const [segments, setSegments] = useState<Segment[]>([
      { id: '1', content: '這是測試字幕', translated: 'This is a test subtitle', isPolished: true, isPartial: false },
      { id: '2', content: '正在測試 Tauri 透明視窗', translated: 'Testing Tauri transparent window', isPolished: false, isPartial: true }
  ]);
  
  // --- Settings State ---
  const [displayMode, setDisplayMode] = useState<DisplayMode>('dual');
  const [fontSize, setFontSize] = useState(24); 
  const [opacity, setOpacity] = useState(0.6); 

  // --- UI State ---
  const [isHovered, setIsHovered] = useState(false);
  const [isClickThrough, setIsClickThrough] = useState(false);

  // --- Refs ---
  const scrollRefOriginal = useRef<HTMLDivElement>(null); 
  const scrollRefTranslated = useRef<HTMLDivElement>(null); 

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

  // Auto Scroll
  useEffect(() => {
    if (scrollRefOriginal.current) {
        scrollRefOriginal.current.scrollTop = scrollRefOriginal.current.scrollHeight;
    }
    if (scrollRefTranslated.current) {
        scrollRefTranslated.current.scrollTop = scrollRefTranslated.current.scrollHeight;
    }
  }, [segments, displayMode]);

  // Event Listeners
  useEffect(() => {
      const unlistenPromise = listen<boolean>('lock-state-changed', (event) => {
          setIsClickThrough(event.payload);
      });
      return () => { unlistenPromise.then(unlisten => unlisten()); };
  }, []);


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
                className={`flex-1 flex flex-col overflow-hidden rounded-3xl relative transition-all duration-500 ease-out border shadow-2xl backdrop-blur-2xl m-2 ${isClickThrough ? 'border-transparent bg-transparent shadow-none backdrop-blur-none' : 'border-white/20'}`}
                style={{ backgroundColor: isClickThrough ? 'transparent' : `rgba(0, 0, 0, ${opacity})` }} 
            >
            
            {/* Title Bar Container */}
            {!isClickThrough && (
                <div 
                    className={`absolute top-4 left-4 right-4 h-12 z-50 transition-all duration-300 ${isHovered ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4 pointer-events-none'}`}
                >
                    {/* 1. Drag Layer (Z-0) - The actual draggable area */}
                    <div 
                        data-tauri-drag-region
                        className="absolute inset-0 rounded-full cursor-grab active:cursor-grabbing z-0"
                    >
                        {/* Visual Background */}
                        <div className="absolute inset-0 bg-white/10 backdrop-blur-md border border-white/20 rounded-full pointer-events-none" />
                    </div>

                    {/* 2. Buttons Layer (Z-10) - Interactivity */}
                    <div className="absolute inset-0 flex items-center justify-between px-4 pointer-events-none z-10">
                        
                        {/* Left Controls */}
                        <div className="flex items-center gap-3 pointer-events-auto">
                            <button 
                                onClick={(e) => { e.stopPropagation(); setIsRecording(!isRecording); }}
                                className={`w-8 h-8 rounded-full flex items-center justify-center transition-all duration-300 shadow-lg ${isRecording ? 'bg-red-500/80 hover:bg-red-500' : 'bg-white/20 hover:bg-white/30'}`}
                            >
                                {isRecording ? <Square className="h-3 w-3 text-white fill-current" /> : <Mic className="h-4 w-4 text-white" />}
                            </button>
                        </div>

                        {/* Right Controls */}
                        <div className="flex items-center gap-2 pointer-events-auto">
                            {/* Click Through Toggle */}
                            <button 
                                onClick={(e) => { e.stopPropagation(); toggleClickThrough(); }} 
                                className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full transition-colors" 
                                title="Lock / Click-Through"
                            >
                                <Lock className="h-4 w-4" />
                            </button>

                            {/* Settings */}
                            <button 
                                onClick={(e) => { e.stopPropagation(); openSettings(); }}
                                className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full transition-colors"
                            >
                                <Settings className="h-4 w-4" />
                            </button>
                            
                            <div className="flex gap-2 ml-3 pl-3 border-l border-white/10">
                                <button 
                                    onClick={(e) => { e.stopPropagation(); minimizeWindow(); }} 
                                    className="w-3 h-3 rounded-full bg-yellow-500/80 hover:bg-yellow-500 shadow-inner" 
                                    title="Minimize"
                                />
                                <button 
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
                {/* Original Text Area */}
                <div 
                    ref={scrollRefOriginal}
                    className="flex-1 overflow-y-auto [&::-webkit-scrollbar]:hidden"
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

                {/* Translated Text Area */}
                {displayMode === 'dual' && (
                    <div 
                        ref={scrollRefTranslated}
                        className="flex-1 overflow-y-auto [&::-webkit-scrollbar]:hidden border-t border-white/10 pt-4"
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
            </div>
        </div>
    </>
  );
}
