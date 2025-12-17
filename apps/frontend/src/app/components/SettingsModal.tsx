import React from 'react';
import { Mic, Monitor, Type, Layers, ArrowLeftRight, X } from 'lucide-react';

interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    isRecording: boolean;
    
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
    isOpen, onClose, isRecording,
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
            <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-zinc-900 border border-gray-200 dark:border-zinc-700 m-4" onClick={e => e.stopPropagation()}>
                
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">設定 (Settings)</h2>
                    <button onClick={onClose} className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors">
                        <X className="h-5 w-5 text-gray-500" />
                    </button>
                </div>

                <div className="space-y-6 max-h-[70vh] overflow-y-auto pr-2 custom-scrollbar">
                    
                    {/* 1. Audio Source */}
                    <div className="space-y-2">
                        <label className="text-sm font-semibold text-gray-500 uppercase tracking-wider">音訊來源</label>
                        <div className="flex items-center gap-2 rounded-lg bg-gray-100 p-1 dark:bg-zinc-800">
                            <button onClick={() => setAudioSource('microphone')} disabled={isRecording}
                                className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-all ${audioSource === 'microphone' ? 'bg-white shadow-sm dark:bg-zinc-700' : 'opacity-50'}`}>
                                <Mic className="h-4 w-4" /> Microphone
                            </button>
                            <button onClick={() => setAudioSource('system')} disabled={isRecording}
                                className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-all ${audioSource === 'system' ? 'bg-white shadow-sm dark:bg-zinc-700' : 'opacity-50'}`}>
                                <Monitor className="h-4 w-4" /> System Audio
                            </button>
                        </div>
                        {isRecording && <p className="text-xs text-amber-600">* 錄音中無法切換音源</p>}
                    </div>

                    {/* 2. Language & Display Mode */}
                    <div className="space-y-2">
                        <label className="text-sm font-semibold text-gray-500 uppercase tracking-wider">語言與顯示</label>
                        <div className="grid grid-cols-2 gap-4">
                            {/* Mode Toggle */}
                            <div className="flex items-center gap-2 rounded-lg bg-gray-100 p-1 dark:bg-zinc-800">
                                <button onClick={() => setDisplayMode('single')} 
                                    className={`flex-1 flex items-center justify-center gap-2 px-2 py-2 rounded-md text-xs font-medium transition-all ${displayMode === 'single' ? 'bg-white shadow-sm dark:bg-zinc-700' : 'opacity-50'}`}>
                                    <Type className="h-3 w-3" /> Single
                                </button>
                                <button onClick={() => setDisplayMode('dual')} 
                                    className={`flex-1 flex items-center justify-center gap-2 px-2 py-2 rounded-md text-xs font-medium transition-all ${displayMode === 'dual' ? 'bg-white shadow-sm dark:bg-zinc-700' : 'opacity-50'}`}>
                                    <Layers className="h-3 w-3" /> Dual
                                </button>
                            </div>
                            {/* Language Swap */}
                            <button onClick={() => setTransMode(transMode === 'zh_to_en' ? 'en_to_zh' : 'zh_to_en')}
                                className="flex items-center justify-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                                <ArrowLeftRight className="h-3 w-3" /> 
                                {transMode === 'zh_to_en' ? '中文 ➝ English' : 'English ➝ 中文'}
                            </button>
                        </div>
                    </div>

                    {/* 3. Appearance (Electron Only mostly, but fontSize applies to web too) */}
                    <div className="space-y-4 border-t border-gray-100 dark:border-zinc-800 pt-4">
                        <label className="text-sm font-semibold text-gray-500 uppercase tracking-wider">外觀樣式</label>
                        
                        {/* Font Size */}
                        <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">字體大小 ({fontSize}px)</span>
                            <input type="range" min="12" max="48" step="1"
                                value={fontSize} onChange={(e) => setFontSize(parseInt(e.target.value))}
                                className="w-1/2 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-zinc-700 accent-blue-600" />
                        </div>

                        {/* Max Lines */}
                        <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">顯示行數 ({maxLines})</span>
                            <input type="range" min="1" max="10" step="1"
                                value={maxLines} onChange={(e) => setMaxLines(parseInt(e.target.value))}
                                className="w-1/2 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-zinc-700 accent-blue-600" />
                        </div>

                        {/* Opacity (Electron Only) */}
                        {isElectron && (
                            <div className="flex items-center justify-between">
                                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">視窗透明度 ({(opacity * 100).toFixed(0)}%)</span>
                                <input type="range" min="0.1" max="1.0" step="0.05"
                                    value={opacity} onChange={(e) => setOpacity(parseFloat(e.target.value))}
                                    className="w-1/2 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-zinc-700 accent-blue-600" />
                            </div>
                        )}
                    </div>

                    {/* 4. Advanced: Initial Prompt */}
                    <div className="space-y-2 border-t border-gray-100 dark:border-zinc-800 pt-4">
                        <label className="text-sm font-semibold text-gray-500 uppercase tracking-wider">AI 上下文引導 (Initial Prompt)</label>
                        <textarea
                            className="w-full min-h-[100px] p-3 text-sm border border-gray-300 rounded-lg bg-gray-50 focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-zinc-800 dark:border-zinc-700 dark:text-gray-100 resize-y"
                            placeholder="輸入會議主題、專有名詞等，引導 ASR 和 LLM 提高準確性..."
                            value={initialPrompt}
                            onChange={(e) => setInitialPrompt(e.target.value)}
                            disabled={isRecording}
                        ></textarea>
                        <p className="text-xs text-gray-400">
                            * 設定將自動儲存，並在下次錄音開始時生效。
                        </p>
                    </div>

                </div>
                
                {/* Footer */}
                <div className="mt-6 flex justify-end">
                    <button onClick={onClose} className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
                        完成 (Done)
                    </button>
                </div>
            </div>
        </div>
    );
}
