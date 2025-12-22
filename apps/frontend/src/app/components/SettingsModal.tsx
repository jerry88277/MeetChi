import React from 'react';
import { Mic, Monitor, Type, Layers, ArrowLeftRight, X, AlertTriangle } from 'lucide-react';

interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    isRecording: boolean;
    errorMessage?: string; // New prop for error messages
    
    // Audio Settings
    audioSource: 'microphone' | 'system';
    setAudioSource: (source: 'microphone' | 'system') => void;
    
    // Language Settings
    displayMode: 'single' | 'dual';
    setDisplayMode: (mode: 'single' | 'dual') => void;
    transMode: 'zh_to_en' | 'en_to_zh';
    setTransMode: (mode: 'zh_to_en' | 'en_to_zh') => void;
    
    // Appearance Settings
    fontSize: number;
    setFontSize: (size: number) => void;
    opacity: number;
    setOpacity: (opacity: number) => void;
    maxLines: number;
    setMaxLines: (lines: number) => void;
    
    // AI Settings
    initialPrompt: string;
    setInitialPrompt: (prompt: string) => void;
    
    isElectron: boolean;
}

export default function SettingsModal({
    isOpen, onClose, isRecording, errorMessage,
    audioSource, setAudioSource,
    displayMode, setDisplayMode,
    transMode, setTransMode,
    fontSize, setFontSize,
    opacity, setOpacity,
    maxLines, setMaxLines,
    initialPrompt, setInitialPrompt,
    isElectron
}: SettingsModalProps) {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-md transition-all duration-300" onClick={onClose}>
            {/* Liquid Glass Modal Container */}
            <div 
                className="w-full max-w-lg rounded-3xl bg-white/80 backdrop-blur-xl p-8 shadow-2xl border border-white/40 m-4 relative overflow-hidden" 
                onClick={e => e.stopPropagation()}
                style={{
                    boxShadow: '0 20px 50px rgba(0,0,0,0.15), 0 0 0 1px rgba(255,255,255,0.2) inset'
                }}
            >
                
                {/* Header */}
                <div className="flex items-center justify-between mb-8">
                    <h2 className="text-2xl font-bold text-gray-800 tracking-tight">設定</h2>
                    <button 
                        onClick={onClose} 
                        className="p-2 rounded-full hover:bg-black/5 transition-colors active:scale-95"
                    >
                        <X className="h-6 w-6 text-gray-500" />
                    </button>
                </div>

                {/* Error Message Display Area */}
                {errorMessage && (
                    <div className="mb-6 p-4 rounded-2xl bg-red-50 border border-red-100 flex items-start gap-3">
                        <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
                        <div>
                            <h3 className="text-sm font-semibold text-red-800">發生錯誤</h3>
                            <p className="text-sm text-red-600 mt-1">{errorMessage}</p>
                        </div>
                    </div>
                )}

                <div className="space-y-8 max-h-[65vh] overflow-y-auto pr-2 custom-scrollbar">
                    
                    {/* 1. Audio Source */}
                    <div className="space-y-3">
                        <label className="text-xs font-bold text-gray-400 uppercase tracking-widest pl-1">音訊來源</label>
                        <div className="flex items-center gap-3 p-1 bg-gray-100/50 rounded-2xl border border-white/50">
                            <button onClick={() => setAudioSource('microphone')} disabled={isRecording}
                                className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${audioSource === 'microphone' ? 'bg-white shadow-md text-gray-800' : 'text-gray-500 hover:bg-white/50'}`}>
                                <Mic className="h-4 w-4" /> Microphone
                            </button>
                            <button onClick={() => setAudioSource('system')} disabled={isRecording}
                                className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${audioSource === 'system' ? 'bg-white shadow-md text-gray-800' : 'text-gray-500 hover:bg-white/50'}`}>
                                <Monitor className="h-4 w-4" /> System Audio
                            </button>
                        </div>
                        {isRecording && <p className="text-xs text-amber-600 pl-2 font-medium">* 錄音中無法切換音源</p>}
                    </div>

                    {/* 2. Language & Display Mode */}
                    <div className="space-y-3">
                        <label className="text-xs font-bold text-gray-400 uppercase tracking-widest pl-1">語言與顯示</label>
                        <div className="grid grid-cols-2 gap-4">
                            {/* Mode Toggle */}
                            <div className="flex items-center gap-1 p-1 bg-gray-100/50 rounded-2xl border border-white/50">
                                <button onClick={() => setDisplayMode('single')} 
                                    className={`flex-1 flex items-center justify-center gap-2 px-2 py-2.5 rounded-xl text-xs font-semibold transition-all duration-200 ${displayMode === 'single' ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 hover:bg-white/50'}`}>
                                    <Type className="h-3 w-3" /> 單語
                                </button>
                                <button onClick={() => setDisplayMode('dual')} 
                                    className={`flex-1 flex items-center justify-center gap-2 px-2 py-2.5 rounded-xl text-xs font-semibold transition-all duration-200 ${displayMode === 'dual' ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 hover:bg-white/50'}`}>
                                    <Layers className="h-3 w-3" /> 雙語
                                </button>
                            </div>
                            {/* Language Swap */}
                            <button onClick={() => setTransMode(transMode === 'zh_to_en' ? 'en_to_zh' : 'zh_to_en')}
                                className="flex items-center justify-center gap-2 rounded-2xl bg-blue-50/50 px-4 py-2.5 text-xs font-semibold text-blue-600 hover:bg-blue-100/80 transition-all border border-blue-100 shadow-sm active:scale-95">
                                <ArrowLeftRight className="h-3 w-3" /> 
                                {transMode === 'zh_to_en' ? '中 ➝ 英' : '英 ➝ 中'}
                            </button>
                        </div>
                    </div>

                    {/* 3. Appearance */}
                    <div className="space-y-5 pt-2">
                        <label className="text-xs font-bold text-gray-400 uppercase tracking-widest pl-1">外觀樣式</label>
                        
                        {/* Font Size */}
                        <div className="space-y-2">
                            <div className="flex justify-between text-sm font-medium text-gray-600 px-1">
                                <span>字體大小</span>
                                <span>{fontSize}px</span>
                            </div>
                            <input type="range" min="16" max="48" step="2"
                                value={fontSize} onChange={(e) => setFontSize(parseInt(e.target.value))}
                                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-gray-800" />
                        </div>

                        {/* Max Lines */}
                        <div className="space-y-2">
                            <div className="flex justify-between text-sm font-medium text-gray-600 px-1">
                                <span>顯示行數</span>
                                <span>{maxLines} 行</span>
                            </div>
                            <input type="range" min="1" max="8" step="1"
                                value={maxLines} onChange={(e) => setMaxLines(parseInt(e.target.value))}
                                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-gray-800" />
                        </div>

                        {/* Opacity */}
                        <div className="space-y-2">
                            <div className="flex justify-between text-sm font-medium text-gray-600 px-1">
                                <span>背景透明度</span>
                                <span>{(opacity * 100).toFixed(0)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.1"
                                value={opacity} onChange={(e) => setOpacity(parseFloat(e.target.value))}
                                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-gray-800" />
                        </div>
                    </div>

                    {/* 4. Advanced: Initial Prompt */}
                    <div className="space-y-3 pt-2">
                        <label className="text-xs font-bold text-gray-400 uppercase tracking-widest pl-1">AI 上下文引導 (Initial Prompt)</label>
                        <textarea
                            className="w-full min-h-[100px] p-4 text-sm border border-gray-200 rounded-2xl bg-gray-50/50 focus:ring-2 focus:ring-gray-200 focus:border-transparent resize-y shadow-inner outline-none transition-all placeholder:text-gray-400"
                            placeholder="輸入會議主題、專有名詞等，引導 ASR 和 LLM 提高準確性..."
                            value={initialPrompt}
                            onChange={(e) => setInitialPrompt(e.target.value)}
                            disabled={isRecording}
                        ></textarea>
                    </div>

                </div>
                
                {/* Footer */}
                <div className="mt-8 flex justify-end">
                    <button 
                        onClick={onClose} 
                        className="px-8 py-3 bg-gray-900 hover:bg-black text-white rounded-2xl font-semibold shadow-lg shadow-gray-300/50 transition-all active:scale-95"
                    >
                        完成
                    </button>
                </div>
            </div>
        </div>
    );
}
