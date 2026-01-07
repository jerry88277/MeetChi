'use client';

import { useState, useEffect } from 'react';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { invoke } from '@tauri-apps/api/core';
import { emit } from '@tauri-apps/api/event';
import { Save, Mic, Type, Monitor, Globe, SlidersHorizontal, X, Plus, Trash2, Cpu } from 'lucide-react';
import { api } from '@/lib/api';

// --- Helper for Web Mode ---
const isTauri = () => {
    return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
};

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
    const [initialPrompt, setInitialPrompt] = useState('這是一場奇美實業的活動錄影。出席者包括董事長許春華、總經理趙令瑜、執行副總陳連振、營運總處副總王耀慶、行政副總陳世賢、特化副總盛培華、研發總處副總郭銘洲、工務副總徐全成、以及生產總處協理黃建賓。我們討論了石化業的挑戰、2050淨零碳排、永續材料、減碳與環境價值。我們的口號是Step Up，追求共存、共榮、共享、共好，以及幸福企業的目標。');
    const [vadThreshold, setVadThreshold] = useState(0.005);
    const [overlapDuration, setOverlapDuration] = useState(0.0);
    
    // Advanced Settings State
    const [maxDuration, setMaxDuration] = useState(15.0);
    const [minSilence, setMinSilence] = useState(0.6);
    const [beamSize, setBeamSize] = useState(5);
    const [temperature, setTemperature] = useState(0.0);
    const [noSpeechProb, setNoSpeechProb] = useState(0.85);

    // Corrections State
    const [corrections, setCorrections] = useState<Record<string, string>>({});
    const [newWrong, setNewWrong] = useState('');
    const [newCorrect, setNewCorrect] = useState('');

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
            setOverlapDuration(parseFloat(localStorage.getItem('overlapDuration') || "0.0"));
            
            // Advanced
            setMaxDuration(parseFloat(localStorage.getItem('maxDuration') || "15.0"));
            setMinSilence(parseFloat(localStorage.getItem('minSilence') || "0.6"));
            setBeamSize(parseInt(localStorage.getItem('beamSize') || "5"));
            setTemperature(parseFloat(localStorage.getItem('temperature') || "0.0"));
            setNoSpeechProb(parseFloat(localStorage.getItem('noSpeechProb') || "0.85"));

            // Load corrections from API
            api.getCorrections().then(setCorrections).catch(console.error);

            if (isTauri()) {
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
            } else {
                console.log("[Web Mode] Loaded mock audio devices");
            }
        }
    }, []);

    // Save & Emit helpers
    const saveSetting = async (key: string, value: string) => {
        localStorage.setItem(key, value);
        if (isTauri()) {
            await emit('setting-changed', { key, value });
        }
    };

    const closeSettings = async () => {
        if (isTauri()) {
            await getCurrentWindow().hide();
        } else {
            window.close(); // For popups
        }
    };

    const handleAddCorrection = async () => {
        if (!newWrong || !newCorrect) return;
        const previousCorrections = { ...corrections };
        const newCorrections = { ...corrections, [newWrong]: newCorrect };
        
        setCorrections(newCorrections);
        setNewWrong('');
        setNewCorrect('');
        
        try {
            await api.updateCorrections(newCorrections);
        } catch (e) {
            console.error("Failed to save correction:", e);
            alert("Failed to save correction. Please check connection.");
            setCorrections(previousCorrections);
        }
    };

    const handleDeleteCorrection = async (key: string) => {
        const previousCorrections = { ...corrections };
        const newCorrections = { ...corrections };
        delete newCorrections[key];
        
        setCorrections(newCorrections);
        
        try {
            await api.updateCorrections(newCorrections);
        } catch (e) {
            console.error("Failed to delete correction:", e);
            alert("Failed to delete correction.");
            setCorrections(previousCorrections);
        }
    };

    return (
        <div className="w-screen h-screen bg-transparent flex flex-col overflow-hidden p-2">
            <div className="flex-1 flex flex-col bg-neutral-900/95 backdrop-blur-2xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl text-white select-none">
                
                {/* Title Bar */}
                <div className="relative h-12 bg-white/5 border-b border-white/10 select-none">
                    <div data-tauri-drag-region className="absolute inset-0 cursor-grab active:cursor-grabbing z-0" />
                    <div className="absolute inset-0 flex items-center px-4 pointer-events-none z-10">
                        <SettingsIcon className="w-5 h-5 text-blue-400 mr-2" />
                        <span className="font-semibold text-gray-200">Settings</span>
                    </div>
                    <div className="absolute right-4 top-0 bottom-0 flex items-center z-20">
                        <button onMouseDown={(e) => e.stopPropagation()} onClick={closeSettings} className="p-1.5 hover:bg-white/10 text-gray-400 hover:text-white rounded-full transition-colors cursor-pointer pointer-events-auto">
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
                                    <label className="text-sm text-gray-400">VAD Sensitivity (Input Level)</label>
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

                            <div>
                                <div className="flex justify-between mb-1">
                                    <label className="text-sm text-gray-400">Audio Overlap (s)</label>
                                    <span className="text-xs text-gray-500">{overlapDuration}s</span>
                                </div>
                                <input 
                                    type="range" min="0.0" max="1.0" step="0.1"
                                    value={overlapDuration}
                                    onChange={(e) => {
                                        const val = parseFloat(e.target.value);
                                        setOverlapDuration(val);
                                        saveSetting('overlapDuration', val.toString());
                                    }}
                                    className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                />
                            </div>
                        </div>
                    </section>

                    {/* Advanced ASR Settings */}
                    <section className="space-y-4">
                        <details className="group">
                            <summary className="list-none flex items-center justify-between cursor-pointer">
                                <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider flex items-center gap-2">
                                    <Cpu className="w-4 h-4" /> Advanced ASR Settings
                                </h2>
                                <span className="text-gray-500 group-open:rotate-180 transition-transform">▼</span>
                            </summary>
                            <div className="pt-4 space-y-4 pl-2 border-l border-white/5 mt-2">
                                
                                <div>
                                    <div className="flex justify-between mb-1">
                                        <label className="text-sm text-gray-400">Max Fragment Duration</label>
                                        <span className="text-xs text-gray-500">{maxDuration}s</span>
                                    </div>
                                    <input type="range" min="3" max="30" step="1" value={maxDuration}
                                        onChange={(e) => { const val = parseFloat(e.target.value); setMaxDuration(val); saveSetting('maxDuration', val.toString()); }}
                                        className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500" />
                                    <p className="text-[10px] text-gray-600 mt-1">Longer = More context/accurate, Shorter = Faster updates.</p>
                                </div>

                                <div>
                                    <div className="flex justify-between mb-1">
                                        <label className="text-sm text-gray-400">Min Silence Duration</label>
                                        <span className="text-xs text-gray-500">{minSilence}s</span>
                                    </div>
                                    <input type="range" min="0.2" max="2.0" step="0.1" value={minSilence}
                                        onChange={(e) => { const val = parseFloat(e.target.value); setMinSilence(val); saveSetting('minSilence', val.toString()); }}
                                        className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500" />
                                </div>

                                <div>
                                    <div className="flex justify-between mb-1">
                                        <label className="text-sm text-gray-400">Beam Size (Accuracy vs Speed)</label>
                                        <span className="text-xs text-gray-500">{beamSize}</span>
                                    </div>
                                    <input type="range" min="1" max="10" step="1" value={beamSize}
                                        onChange={(e) => { const val = parseInt(e.target.value); setBeamSize(val); saveSetting('beamSize', val.toString()); }}
                                        className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500" />
                                </div>

                                <div>
                                    <div className="flex justify-between mb-1">
                                        <label className="text-sm text-gray-400">Temperature (Creativity)</label>
                                        <span className="text-xs text-gray-500">{temperature}</span>
                                    </div>
                                    <input type="range" min="0.0" max="1.0" step="0.1" value={temperature}
                                        onChange={(e) => { const val = parseFloat(e.target.value); setTemperature(val); saveSetting('temperature', val.toString()); }}
                                        className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500" />
                                </div>

                                <div>
                                    <div className="flex justify-between mb-1">
                                        <label className="text-sm text-gray-400">No Speech Threshold</label>
                                        <span className="text-xs text-gray-500">{noSpeechProb}</span>
                                    </div>
                                    <input type="range" min="0.1" max="0.95" step="0.05" value={noSpeechProb}
                                        onChange={(e) => { const val = parseFloat(e.target.value); setNoSpeechProb(val); saveSetting('noSpeechProb', val.toString()); }}
                                        className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500" />
                                    <p className="text-[10px] text-gray-600 mt-1">Higher = Show more (even noise), Lower = Stricter filtering.</p>
                                </div>
                            </div>
                        </details>
                    </section>

                    {/* Keyword Corrections Section */}
                    <section className="space-y-4">
                        <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider flex items-center gap-2">
                            <SlidersHorizontal className="w-4 h-4" /> Keyword Corrections
                        </h2>
                        <div className="bg-black/40 rounded-lg border border-white/10 overflow-hidden">
                            {/* List */}
                            <div className="max-h-40 overflow-y-auto p-2 space-y-2">
                                {Object.entries(corrections).sort(([a], [b]) => a.localeCompare(b, 'zh-TW')).map(([wrong, correct]) => (
                                    <div key={wrong} className="flex items-center justify-between bg-white/5 p-2 rounded text-sm">
                                        <div className="flex items-center gap-2">
                                            <span className="text-red-400 line-through opacity-70">{wrong}</span>
                                            <span className="text-white/40">→</span>
                                            <span className="text-green-400">{correct}</span>
                                        </div>
                                        <button onClick={() => handleDeleteCorrection(wrong)} className="p-1 text-white/40 hover:text-red-400 rounded-full">
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                ))}
                                {Object.keys(corrections).length === 0 && <div className="text-center text-white/30 text-xs py-2">No corrections yet.</div>}
                            </div>
                        </div>
                            {/* Add Form */}
                            <div className="p-2 border-t border-white/10 flex gap-2 rounded-lg bg-black/40 mt-4">
                                <input 
                                    type="text" placeholder="錯誤詞 (e.g. 剩副總)" 
                                    value={newWrong} onChange={e => setNewWrong(e.target.value)}
                                    className="flex-1 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs focus:border-blue-500/50 outline-none text-white"
                                />
                                <input 
                                    type="text" placeholder="正確詞 (e.g. 盛副總)" 
                                    value={newCorrect} onChange={e => setNewCorrect(e.target.value)}
                                    className="flex-1 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs focus:border-blue-500/50 outline-none text-white"
                                />
                                <button onClick={handleAddCorrection} className="bg-blue-600 hover:bg-blue-500 text-white rounded px-3 py-1 text-sm font-medium">
                                    <Plus className="w-4 h-4" /> Add
                                </button>
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