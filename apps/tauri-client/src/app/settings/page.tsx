'use client';

import { useState, useEffect, useRef } from 'react';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { LogicalSize } from '@tauri-apps/api/dpi';
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
    const [devices, setDevices] = useState<{ id: string, name: string }[]>([
        { id: 'default', name: 'Default Microphone' },
        { id: 'system', name: 'System Audio (Loopback)' }
    ]);
    const [isMounted, setIsMounted] = useState(false);
    const [transMode, setTransMode] = useState('zh_to_en');
    const [fontSize, setFontSize] = useState(24);
    const [fontWeight, setFontWeight] = useState(400);
    const [opacity, setOpacity] = useState(0.6);
    const [maxLines, setMaxLines] = useState(3);
    const [displayMode, setDisplayMode] = useState<'original' | 'translated' | 'bilingual'>('bilingual');
    const [initialPrompt, setInitialPrompt] = useState('這是一場奇美實業的活動錄影。出席者包括董事長許春華、總經理趙令瑜、執行副總陳連振、營運總處副總王耀慶、行政副總陳世賢、特化副總盛培華、研發總處副總郭銘洲、工務副總徐全成、以及生產總處協理黃建賓。我們討論了石化業的挑戰、2050淨零碳排、永續材料、減碳與環境價值。我們的口號是Step Up，追求共存、共榮、共享、共好，以及幸福企業的目標。');
    const [vadThreshold, setVadThreshold] = useState(0.005);
    const [overlapDuration, setOverlapDuration] = useState(0.0);

    // Operation Mode State
    const [operationMode, setOperationMode] = useState<'transcription' | 'alignment' | 'manual'>('transcription');
    const [combinedScript, setCombinedScript] = useState('');
    const [chineseScript, setChineseScript] = useState('');
    const [englishScript, setEnglishScript] = useState('');
    const [scriptPairCount, setScriptPairCount] = useState(0);

    // Multi-Speaker State
    const [speakerAName, setSpeakerAName] = useState('講者 A');
    const [speakerAChineseScript, setSpeakerAChineseScript] = useState('');
    const [speakerAEnglishScript, setSpeakerAEnglishScript] = useState('');
    const [speakerBName, setSpeakerBName] = useState('講者 B');
    const [speakerBChineseScript, setSpeakerBChineseScript] = useState('');
    const [speakerBEnglishScript, setSpeakerBEnglishScript] = useState('');
    const [multiSpeakerMode, setMultiSpeakerMode] = useState(false);

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

    // Resize State
    const isResizingRef = useRef(false);
    const startResizeState = useRef<{ w: number, h: number, x: number, y: number, factor: number } | null>(null);

    // Load settings on mount
    useEffect(() => {
        if (typeof window !== 'undefined') {
            setInitialPrompt(localStorage.getItem('initialPrompt') || "");
            setFontSize(parseInt(localStorage.getItem('fontSize') || "24"));
            setFontWeight(parseInt(localStorage.getItem('fontWeight') || "400"));
            setOpacity(parseFloat(localStorage.getItem('opacity') || "0.6"));
            setMaxLines(parseInt(localStorage.getItem('maxLines') || "3"));
            setDisplayMode((localStorage.getItem('displayMode') as 'original' | 'translated' | 'bilingual') || 'bilingual');
            setAudioSource(localStorage.getItem('audioSource') || "default");
            setTransMode(localStorage.getItem('transMode') || "zh_to_en");
            setVadThreshold(parseFloat(localStorage.getItem('vadThreshold') || "0.005"));
            setOverlapDuration(parseFloat(localStorage.getItem('overlapDuration') || "0.0"));

            // Operation Mode
            setOperationMode((localStorage.getItem('operationMode') as 'transcription' | 'alignment' | 'manual') || 'transcription');

            // Multi-Speaker Mode
            const savedMultiSpeakerMode = localStorage.getItem('multiSpeakerMode') === 'true';
            setMultiSpeakerMode(savedMultiSpeakerMode);

            // Load Speaker A/B Settings
            setSpeakerAName(localStorage.getItem('speakerAName') || '講者 A');
            setSpeakerAChineseScript(localStorage.getItem('speakerAChineseScript') || '');
            setSpeakerAEnglishScript(localStorage.getItem('speakerAEnglishScript') || '');
            setSpeakerBName(localStorage.getItem('speakerBName') || '講者 B');
            setSpeakerBChineseScript(localStorage.getItem('speakerBChineseScript') || '');
            setSpeakerBEnglishScript(localStorage.getItem('speakerBEnglishScript') || '');

            // Load separate scripts (single-speaker fallback)
            const savedChinese = localStorage.getItem('chineseScript') || '';
            const savedEnglish = localStorage.getItem('englishScript') || '';
            setChineseScript(savedChinese);
            setEnglishScript(savedEnglish);
            // Count and combine
            const chLines = savedChinese.split('\n').filter(l => l.trim());
            const enLines = savedEnglish.split('\n').filter(l => l.trim());
            setScriptPairCount(Math.min(chLines.length, enLines.length));

            // Generate combined script based on mode
            if (savedMultiSpeakerMode) {
                // Multi-speaker format with ===SPEAKER:xxx=== markers
                const speakerACh = (localStorage.getItem('speakerAChineseScript') || '').split('\n').filter(l => l.trim());
                const speakerAEn = (localStorage.getItem('speakerAEnglishScript') || '').split('\n').filter(l => l.trim());
                const speakerBCh = (localStorage.getItem('speakerBChineseScript') || '').split('\n').filter(l => l.trim());
                const speakerBEn = (localStorage.getItem('speakerBEnglishScript') || '').split('\n').filter(l => l.trim());

                let multiCombined = `===SPEAKER:${localStorage.getItem('speakerAName') || '講者 A'}===\n`;
                multiCombined += speakerACh.map((ch, i) => `${ch.trim()} ||| ${speakerAEn[i]?.trim() || ''}`).join('\n');
                multiCombined += `\n===SPEAKER:${localStorage.getItem('speakerBName') || '講者 B'}===\n`;
                multiCombined += speakerBCh.map((ch, i) => `${ch.trim()} ||| ${speakerBEn[i]?.trim() || ''}`).join('\n');

                setCombinedScript(multiCombined);
                saveSetting('combinedScript', multiCombined);
            } else {
                // Single-speaker format
                const combined = chLines.map((ch, i) => `[${i + 1}] ${ch.trim()} ||| ${enLines[i]?.trim() || ''}`).join('\n');
                setCombinedScript(combined);
                saveSetting('combinedScript', combined);
            }

            // Advanced
            setMaxDuration(parseFloat(localStorage.getItem('maxDuration') || "15.0"));
            setMinSilence(parseFloat(localStorage.getItem('minSilence') || "0.6"));
            setBeamSize(parseInt(localStorage.getItem('beamSize') || "5"));
            setTemperature(parseFloat(localStorage.getItem('temperature') || "0.0"));
            setNoSpeechProb(parseFloat(localStorage.getItem('noSpeechProb') || "0.85"));

            // Load corrections from API
            api.getCorrections().then(setCorrections).catch(console.error);

            if (isTauri()) {
                invoke<{ id: string, name: string }[]>('get_audio_devices')
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

            // Mark as mounted to enable client-only features
            setIsMounted(true);
        }
    }, []);

    // Save & Emit helpers
    const saveSetting = async (key: string, value: string) => {
        localStorage.setItem(key, value);
        if (isTauri()) {
            await emit('setting-changed', { key, value });
        }
    };

    // Helper: Regenerate multi-speaker combined script
    const regenerateMultiSpeakerScript = () => {
        const speakerACh = speakerAChineseScript.split('\n').filter(l => l.trim());
        const speakerAEn = speakerAEnglishScript.split('\n').filter(l => l.trim());
        const speakerBCh = speakerBChineseScript.split('\n').filter(l => l.trim());
        const speakerBEn = speakerBEnglishScript.split('\n').filter(l => l.trim());

        let multiCombined = `===SPEAKER:${speakerAName}===\n`;
        multiCombined += speakerACh.map((ch, i) => `${ch.trim()} ||| ${speakerAEn[i]?.trim() || ''}`).join('\n');
        multiCombined += `\n===SPEAKER:${speakerBName}===\n`;
        multiCombined += speakerBCh.map((ch, i) => `${ch.trim()} ||| ${speakerBEn[i]?.trim() || ''}`).join('\n');

        setCombinedScript(multiCombined);
        saveSetting('combinedScript', multiCombined);
    };

    // Helper: Regenerate single-speaker combined script
    const regenerateSingleSpeakerScript = () => {
        const chLines = chineseScript.split('\n').filter(l => l.trim());
        const enLines = englishScript.split('\n').filter(l => l.trim());
        setScriptPairCount(Math.min(chLines.length, enLines.length));
        const combined = chLines.map((ch, i) => `[${i + 1}] ${ch.trim()} ||| ${enLines[i]?.trim() || ''}`).join('\n');
        setCombinedScript(combined);
        saveSetting('combinedScript', combined);
    };

    const closeSettings = async () => {
        if (isTauri()) {
            await getCurrentWindow().hide();
        } else {
            window.close(); // For popups
        }
    };

    // --- Resize Logic ---
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
            if (newWidth > 400 && newHeight > 300) {
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

                    {/* Display Mode Section */}
                    <section className="space-y-4">
                        <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider flex items-center gap-2">
                            <Monitor className="w-4 h-4" /> Display Mode
                        </h2>
                        <div className="flex gap-2 bg-black/20 p-1 rounded-xl">
                            <button
                                onClick={() => { setDisplayMode('original'); saveSetting('displayMode', 'original'); }}
                                className={`flex-1 px-3 py-2 text-sm rounded-lg transition-all ${displayMode === 'original' ? 'bg-blue-500/20 text-blue-400 ring-1 ring-blue-500/50' : 'text-gray-400 hover:text-white hover:bg-white/5'}`}
                            >
                                原文
                            </button>
                            <button
                                onClick={() => { setDisplayMode('translated'); saveSetting('displayMode', 'translated'); }}
                                className={`flex-1 px-3 py-2 text-sm rounded-lg transition-all ${displayMode === 'translated' ? 'bg-blue-500/20 text-blue-400 ring-1 ring-blue-500/50' : 'text-gray-400 hover:text-white hover:bg-white/5'}`}
                            >
                                譯文
                            </button>
                            <button
                                onClick={() => { setDisplayMode('bilingual'); saveSetting('displayMode', 'bilingual'); }}
                                className={`flex-1 px-3 py-2 text-sm rounded-lg transition-all ${displayMode === 'bilingual' ? 'bg-blue-500/20 text-blue-400 ring-1 ring-blue-500/50' : 'text-gray-400 hover:text-white hover:bg-white/5'}`}
                            >
                                原文+譯文
                            </button>
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

                    {/* Operation Mode Section */}
                    <section className="space-y-4">
                        <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider flex items-center gap-2">
                            <SlidersHorizontal className="w-4 h-4" /> Operation Mode
                        </h2>
                        <div className="flex gap-2 bg-black/20 p-1 rounded-xl">
                            <button
                                onClick={() => { setOperationMode('transcription'); saveSetting('operationMode', 'transcription'); }}
                                className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all ${operationMode === 'transcription' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'}`}
                            >
                                轉錄模式
                            </button>
                            <button
                                onClick={() => { setOperationMode('alignment'); saveSetting('operationMode', 'alignment'); }}
                                className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all ${operationMode === 'alignment' ? 'bg-green-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'}`}
                            >
                                對齊模式
                            </button>
                            <button
                                onClick={() => { setOperationMode('manual'); saveSetting('operationMode', 'manual'); }}
                                className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all ${operationMode === 'manual' ? 'bg-purple-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'}`}
                            >
                                手動輸入
                            </button>
                        </div>
                        <p className="text-[10px] text-gray-500">
                            {operationMode === 'transcription' && '即時語音辨識與翻譯'}
                            {operationMode === 'alignment' && '使用預先輸入的腳本進行對齊比對，顯示對應翻譯'}
                            {operationMode === 'manual' && '手動輸入文字並翻譯'}
                        </p>
                    </section>

                    {/* Script Editor Section (only for alignment mode) */}
                    {operationMode === 'alignment' && (
                        <section className="space-y-4">
                            <h2 className="text-sm font-bold text-green-400 uppercase tracking-wider flex items-center gap-2">
                                📝 Script Editor
                            </h2>

                            {/* Multi-Speaker Toggle */}
                            <div className="flex items-center justify-between bg-black/30 rounded-lg p-3">
                                <div>
                                    <span className="text-sm text-white">多講者模式</span>
                                    <p className="text-[10px] text-gray-500">兩位講者接連致詞，各自使用獨立講稿</p>
                                </div>
                                <button
                                    onClick={() => {
                                        const newMode = !multiSpeakerMode;
                                        setMultiSpeakerMode(newMode);
                                        saveSetting('multiSpeakerMode', newMode.toString());
                                        // Regenerate combined script on mode change
                                        if (newMode) {
                                            regenerateMultiSpeakerScript();
                                        } else {
                                            regenerateSingleSpeakerScript();
                                        }
                                    }}
                                    className={`relative w-12 h-6 rounded-full transition-colors ${multiSpeakerMode ? 'bg-green-600' : 'bg-gray-600'}`}
                                >
                                    <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${multiSpeakerMode ? 'translate-x-6' : 'translate-x-0.5'}`} />
                                </button>
                            </div>

                            {multiSpeakerMode ? (
                                /* Multi-Speaker Mode UI */
                                <div className="space-y-4">
                                    {/* Speaker A Section */}
                                    <details className="group" open>
                                        <summary className="list-none flex items-center justify-between cursor-pointer bg-black/30 rounded-lg p-3">
                                            <div className="flex items-center gap-2">
                                                <span className="text-orange-400">👤</span>
                                                <input
                                                    type="text"
                                                    value={speakerAName}
                                                    onChange={(e) => {
                                                        setSpeakerAName(e.target.value);
                                                        saveSetting('speakerAName', e.target.value);
                                                        regenerateMultiSpeakerScript();
                                                    }}
                                                    onClick={(e) => e.stopPropagation()}
                                                    className="bg-transparent text-white text-sm font-medium focus:outline-none border-b border-transparent focus:border-orange-400 w-24"
                                                />
                                                <span className="text-[10px] text-gray-500">
                                                    ({speakerAChineseScript.split('\n').filter(l => l.trim()).length} 行)
                                                </span>
                                            </div>
                                            <span className="text-gray-500 group-open:rotate-180 transition-transform">▼</span>
                                        </summary>
                                        <div className="mt-2 grid grid-cols-2 gap-2">
                                            <div className="bg-black/40 rounded-lg border border-white/10 overflow-hidden">
                                                <div className="p-2 border-b border-white/10 bg-black/20">
                                                    <span className="text-[10px] text-blue-400 font-bold">🇹🇼 中文稿</span>
                                                </div>
                                                <textarea
                                                    value={speakerAChineseScript}
                                                    onChange={(e) => {
                                                        setSpeakerAChineseScript(e.target.value);
                                                        saveSetting('speakerAChineseScript', e.target.value);
                                                        regenerateMultiSpeakerScript();
                                                    }}
                                                    placeholder="各位貴賓大家好&#10;歡迎蒞臨..."
                                                    className="w-full h-36 bg-transparent text-white text-xs p-2 resize-none focus:outline-none font-mono leading-relaxed"
                                                    spellCheck={false}
                                                />
                                            </div>
                                            <div className="bg-black/40 rounded-lg border border-white/10 overflow-hidden">
                                                <div className="p-2 border-b border-white/10 bg-black/20">
                                                    <span className="text-[10px] text-green-400 font-bold">🇺🇸 English</span>
                                                </div>
                                                <textarea
                                                    value={speakerAEnglishScript}
                                                    onChange={(e) => {
                                                        setSpeakerAEnglishScript(e.target.value);
                                                        saveSetting('speakerAEnglishScript', e.target.value);
                                                        regenerateMultiSpeakerScript();
                                                    }}
                                                    placeholder="Good evening, distinguished guests&#10;Welcome..."
                                                    className="w-full h-36 bg-transparent text-white text-xs p-2 resize-none focus:outline-none font-mono leading-relaxed"
                                                    spellCheck={false}
                                                />
                                            </div>
                                        </div>
                                    </details>

                                    {/* Speaker B Section */}
                                    <details className="group" open>
                                        <summary className="list-none flex items-center justify-between cursor-pointer bg-black/30 rounded-lg p-3">
                                            <div className="flex items-center gap-2">
                                                <span className="text-purple-400">👤</span>
                                                <input
                                                    type="text"
                                                    value={speakerBName}
                                                    onChange={(e) => {
                                                        setSpeakerBName(e.target.value);
                                                        saveSetting('speakerBName', e.target.value);
                                                        regenerateMultiSpeakerScript();
                                                    }}
                                                    onClick={(e) => e.stopPropagation()}
                                                    className="bg-transparent text-white text-sm font-medium focus:outline-none border-b border-transparent focus:border-purple-400 w-24"
                                                />
                                                <span className="text-[10px] text-gray-500">
                                                    ({speakerBChineseScript.split('\n').filter(l => l.trim()).length} 行)
                                                </span>
                                            </div>
                                            <span className="text-gray-500 group-open:rotate-180 transition-transform">▼</span>
                                        </summary>
                                        <div className="mt-2 grid grid-cols-2 gap-2">
                                            <div className="bg-black/40 rounded-lg border border-white/10 overflow-hidden">
                                                <div className="p-2 border-b border-white/10 bg-black/20">
                                                    <span className="text-[10px] text-blue-400 font-bold">🇹🇼 中文稿</span>
                                                </div>
                                                <textarea
                                                    value={speakerBChineseScript}
                                                    onChange={(e) => {
                                                        setSpeakerBChineseScript(e.target.value);
                                                        saveSetting('speakerBChineseScript', e.target.value);
                                                        regenerateMultiSpeakerScript();
                                                    }}
                                                    placeholder="感謝董事長&#10;今天很高興..."
                                                    className="w-full h-36 bg-transparent text-white text-xs p-2 resize-none focus:outline-none font-mono leading-relaxed"
                                                    spellCheck={false}
                                                />
                                            </div>
                                            <div className="bg-black/40 rounded-lg border border-white/10 overflow-hidden">
                                                <div className="p-2 border-b border-white/10 bg-black/20">
                                                    <span className="text-[10px] text-green-400 font-bold">🇺🇸 English</span>
                                                </div>
                                                <textarea
                                                    value={speakerBEnglishScript}
                                                    onChange={(e) => {
                                                        setSpeakerBEnglishScript(e.target.value);
                                                        saveSetting('speakerBEnglishScript', e.target.value);
                                                        regenerateMultiSpeakerScript();
                                                    }}
                                                    placeholder="Thank you, Chairman&#10;I am delighted..."
                                                    className="w-full h-36 bg-transparent text-white text-xs p-2 resize-none focus:outline-none font-mono leading-relaxed"
                                                    spellCheck={false}
                                                />
                                            </div>
                                        </div>
                                    </details>

                                    {/* Status */}
                                    <div className="p-2 bg-black/20 rounded-lg">
                                        <span className="text-[10px] text-gray-400">
                                            <span className="text-green-400">✅ 多講者模式</span>
                                            {' '}{speakerAName}: {speakerAChineseScript.split('\n').filter(l => l.trim()).length} 句
                                            {' → '}{speakerBName}: {speakerBChineseScript.split('\n').filter(l => l.trim()).length} 句
                                        </span>
                                    </div>
                                </div>
                            ) : (
                                /* Single-Speaker Mode UI (Original) */
                                <div className="space-y-4">
                                    <p className="text-[10px] text-gray-400">
                                        左側輸入中文稿，右側輸入英文稿，系統按行號自動配對
                                    </p>
                                    <div className="grid grid-cols-2 gap-2">
                                        {/* Chinese Script */}
                                        <div className="bg-black/40 rounded-lg border border-white/10 overflow-hidden">
                                            <div className="p-2 border-b border-white/10 bg-black/20">
                                                <span className="text-[10px] text-blue-400 font-bold">🇹🇼 中文稿</span>
                                            </div>
                                            <textarea
                                                value={chineseScript}
                                                onChange={(e) => {
                                                    const val = e.target.value;
                                                    setChineseScript(val);
                                                    saveSetting('chineseScript', val);
                                                    regenerateSingleSpeakerScript();
                                                }}
                                                placeholder={`各位奇美的合作夥伴，大家晚安！\n隔了一年，又能與各位貴賓一起舉杯。\n我們衷心感謝各位對奇美的支持。`}
                                                className="w-full h-48 bg-transparent text-white text-xs p-2 resize-none focus:outline-none font-mono leading-relaxed"
                                                spellCheck={false}
                                            />
                                        </div>
                                        {/* English Script */}
                                        <div className="bg-black/40 rounded-lg border border-white/10 overflow-hidden">
                                            <div className="p-2 border-b border-white/10 bg-black/20">
                                                <span className="text-[10px] text-green-400 font-bold">🇺🇸 English</span>
                                            </div>
                                            <textarea
                                                value={englishScript}
                                                onChange={(e) => {
                                                    const val = e.target.value;
                                                    setEnglishScript(val);
                                                    saveSetting('englishScript', val);
                                                    regenerateSingleSpeakerScript();
                                                }}
                                                placeholder={`Good evening, our valued partners!\nIt's a pleasure to gather and share this moment.\nWe sincerely appreciate your support.`}
                                                className="w-full h-48 bg-transparent text-white text-xs p-2 resize-none focus:outline-none font-mono leading-relaxed"
                                                spellCheck={false}
                                            />
                                        </div>
                                    </div>
                                    <div className="p-2 bg-black/20 rounded-lg flex justify-between items-center">
                                        <span className="text-[10px] text-gray-400">
                                            {scriptPairCount > 0
                                                ? <span className="text-green-400">✅ 已配對 {scriptPairCount} 句 (中文 {chineseScript.split('\n').filter(l => l.trim()).length} 行 / 英文 {englishScript.split('\n').filter(l => l.trim()).length} 行)</span>
                                                : <span className="text-yellow-400">⚠️ 請輸入腳本</span>
                                            }
                                        </span>
                                    </div>
                                </div>
                            )}
                        </section>
                    )}

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
                                    type="range" min="16" max="72" step="2"
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
                                    <label className="text-sm text-gray-400">Font Weight</label>
                                    <span className="text-xs text-gray-500">{fontWeight}</span>
                                </div>
                                <input
                                    type="range" min="100" max="900" step="100"
                                    value={fontWeight}
                                    onChange={(e) => {
                                        const val = parseInt(e.target.value);
                                        setFontWeight(val);
                                        saveSetting('fontWeight', val.toString());
                                    }}
                                    className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                />
                                <div className="flex justify-between text-[10px] text-gray-600 mt-1">
                                    <span>Thin</span>
                                    <span>Normal</span>
                                    <span>Bold</span>
                                </div>
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
                                    type="number" min="1" max="50"
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

                {/* Resize Handle - only render after mount to prevent hydration mismatch */}
                {isMounted && isTauri() && (
                    <div
                        className="absolute bottom-0 right-0 w-6 h-6 cursor-nwse-resize z-50 flex items-end justify-end p-1"
                        onMouseDown={onResizeStart}
                    >
                        <div className="w-3 h-3 border-r-2 border-b-2 border-white/30 rounded-br-sm hover:border-white/60 transition-colors" />
                    </div>
                )}
            </div>
        </div>
    );
}

function SettingsIcon({ className }: { className?: string }) {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.47a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.35a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" /><circle cx="12" cy="12" r="3" /></svg>
    )
}