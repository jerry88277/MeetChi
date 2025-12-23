'use client';

import { useState, useEffect } from 'react';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { invoke } from '@tauri-apps/api/core';
import { emit } from '@tauri-apps/api/event';
import { Save, Mic, Type, Monitor, Globe, SlidersHorizontal, X } from 'lucide-react';

export default function SettingsPage() {
    // State
    const [audioSource, setAudioSource] = useState('default');
    const [devices, setDevices] = useState<{id: string, name: string}[]>([
        { id: 'default', name: 'Default Microphone' },
        { id: 'system', name: 'System Audio (Loopback)' }
    ]);
    const [transMode, setTransMode] = useState('zh_to_en');
    const [fontSize, setFontSize] = useState(24);
    const [opacity, setOpacity] = useState(0.6);
    const [maxLines, setMaxLines] = useState(3);
    const [initialPrompt, setInitialPrompt] = useState('');
    const [vadThreshold, setVadThreshold] = useState(0.005);

    // Load settings on mount
    useEffect(() => {
        if (typeof window !== 'undefined') {
            setInitialPrompt(localStorage.getItem('initialPrompt') || "");
            setFontSize(parseInt(localStorage.getItem('fontSize') || "24"));
            setOpacity(parseFloat(localStorage.getItem('opacity') || "0.6"));
            setMaxLines(parseInt(localStorage.getItem('maxLines') || "3"));
            setAudioSource(localStorage.getItem('audioSource') || "default");
            setTransMode(localStorage.getItem('transMode') || "zh_to_en");
            setVadThreshold(parseFloat(localStorage.getItem('vadThreshold') || "0.005"));

            invoke<{id: string, name: string}[]>('get_audio_devices')
                .then(devs => {
                    const allDevs = [
                         { id: 'default', name: 'Default Microphone' },
                         ...devs
                    ];
                    if (!devs.find(d => d.name.toLowerCase().includes('loopback') || d.name.toLowerCase().includes('stereo mix'))) {
                        allDevs.push({ id: 'system', name: 'System Audio (Loopback)' });
                    }
                    setDevices(allDevs);
                })
                .catch(err => console.error("Failed to load audio devices:", err));
        }
    }, []);

    // Save & Emit helpers
    const saveSetting = async (key: string, value: string) => {
        localStorage.setItem(key, value);
        await emit('setting-changed', { key, value });
    };

    const closeSettings = async () => {
        await getCurrentWindow().hide();
    };

    return (
        <div className="w-screen h-screen bg-transparent flex flex-col overflow-hidden p-2">
            <div className="flex-1 flex flex-col bg-neutral-900/95 backdrop-blur-2xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl text-white select-none">
                
                {/* Custom Title Bar - Split Layout with Absolute Positioning to fix click interception */}
                <div className="relative h-12 bg-white/5 border-b border-white/10 select-none">
                    
                    {/* Layer 1: Drag Region (Full Fill, Z-0) */}
                    <div 
                        data-tauri-drag-region 
                        className="absolute inset-0 cursor-grab active:cursor-grabbing z-0"
                    />

                    {/* Layer 2: Title (Pointer events none, Z-10) */}
                    <div className="absolute inset-0 flex items-center px-4 pointer-events-none z-10">
                        <SettingsIcon className="w-5 h-5 text-blue-400 mr-2" />
                        <span className="font-semibold text-gray-200">Settings</span>
                    </div>

                    {/* Layer 3: Buttons (Right Aligned, High Z-Index, Pointer Events Auto) */}
                    <div className="absolute right-4 top-0 bottom-0 flex items-center z-20">
                        <button 
                            onMouseDown={(e) => e.stopPropagation()} 
                            onClick={closeSettings} 
                            className="p-1.5 hover:bg-white/10 text-gray-400 hover:text-white rounded-full transition-colors cursor-pointer pointer-events-auto"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">
                    {/* Audio Section */}
                    <section className="space-y-4">
                        <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider flex items-center gap-2">
                            <Mic className="w-4 h-4" /> Audio Source
                        </h2>
                        <div className="space-y-3">
                            <div>
                                <label className="block text-sm text-gray-400 mb-1">Input Device</label>
                                <div className="relative">
                                    <select 
                                        value={audioSource}
                                        onChange={(e) => {
                                            setAudioSource(e.target.value);
                                            saveSetting('audioSource', e.target.value);
                                        }}
                                        className="w-full bg-black/40 border border-white/10 rounded-lg p-2.5 text-sm focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 outline-none appearance-none"
                                    >
                                        {devices.map(d => (
                                            <option key={d.id} value={d.id}>{d.name}</option>
                                        ))}
                                    </select>
                                    <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-gray-500">▼</div>
                                </div>
                            </div>
                            
                            <div>
                                <div className="flex justify-between mb-1">
                                    <label className="text-sm text-gray-400">VAD Sensitivity</label>
                                    <span className="text-xs text-gray-500">{vadThreshold}</span>
                                </div>
                                <input 
                                    type="range" min="0.001" max="0.1" step="0.001"
                                    value={vadThreshold}
                                    onChange={(e) => {
                                        const val = parseFloat(e.target.value);
                                        setVadThreshold(val);
                                        saveSetting('vadThreshold', val.toString());
                                    }}
                                    className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                />
                            </div>
                        </div>
                    </section>

                    {/* Translation Section */}
                    <section className="space-y-4">
                        <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider flex items-center gap-2">
                            <Globe className="w-4 h-4" /> Translation Mode
                        </h2>
                        <div className="flex gap-3 bg-black/20 p-1 rounded-xl">
                            <button 
                                onClick={() => { setTransMode('zh_to_en'); saveSetting('transMode', 'zh_to_en'); }}
                                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${transMode === 'zh_to_en' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'}`}
                            >
                                ZH → EN
                            </button>
                            <button 
                                onClick={() => { setTransMode('en_to_zh'); saveSetting('transMode', 'en_to_zh'); }}
                                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${transMode === 'en_to_zh' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'}`}
                            >
                                EN → ZH
                            </button>
                        </div>
                    </section>

                    {/* Appearance Section */}
                    <section className="space-y-4">
                        <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider flex items-center gap-2">
                            <Monitor className="w-4 h-4" /> Appearance
                        </h2>
                        
                        <div className="space-y-4">
                            <div>
                                <div className="flex justify-between mb-1">
                                    <label className="text-sm text-gray-400">Font Size</label>
                                    <span className="text-xs text-gray-500">{fontSize}px</span>
                                </div>
                                <input 
                                    type="range" min="16" max="48" step="2"
                                    value={fontSize}
                                    onChange={(e) => {
                                        const val = parseInt(e.target.value);
                                        setFontSize(val);
                                        saveSetting('fontSize', val.toString());
                                    }}
                                    className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                />
                            </div>

                            <div>
                                <div className="flex justify-between mb-1">
                                    <label className="text-sm text-gray-400">Background Opacity</label>
                                    <span className="text-xs text-gray-500">{Math.round(opacity * 100)}%</span>
                                </div>
                                <input 
                                    type="range" min="0" max="1" step="0.1"
                                    value={opacity}
                                    onChange={(e) => {
                                        const val = parseFloat(e.target.value);
                                        setOpacity(val);
                                        saveSetting('opacity', val.toString());
                                    }}
                                    className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                />
                            </div>

                            <div>
                                <label className="block text-sm text-gray-400 mb-1">Max Lines</label>
                                <input 
                                    type="number" min="1" max="10"
                                    value={maxLines}
                                    onChange={(e) => {
                                        const val = parseInt(e.target.value);
                                        setMaxLines(val);
                                        saveSetting('maxLines', val.toString());
                                    }}
                                    className="w-full bg-black/40 border border-white/10 rounded-lg p-2 text-sm focus:border-blue-500/50 outline-none"
                                />
                            </div>
                        </div>
                    </section>

                    {/* AI Context Section */}
                    <section className="space-y-4">
                        <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider flex items-center gap-2">
                            <Type className="w-4 h-4" /> Context
                        </h2>
                        <div>
                            <label className="block text-sm text-gray-400 mb-1">Initial Prompt</label>
                            <textarea 
                                value={initialPrompt}
                                onChange={(e) => {
                                    setInitialPrompt(e.target.value);
                                    saveSetting('initialPrompt', e.target.value);
                                }}
                                placeholder="Keywords, jargon, or context..."
                                className="w-full h-24 bg-black/40 border border-white/10 rounded-lg p-3 text-sm focus:border-blue-500/50 outline-none resize-none"
                            />
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}

function SettingsIcon({className}: {className?: string}) {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.47a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.35a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
    )
}