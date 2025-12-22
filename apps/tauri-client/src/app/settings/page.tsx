'use client';

import { useState, useEffect } from 'react';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { invoke } from '@tauri-apps/api/core';
import { Save, Mic, Type, Monitor, Globe } from 'lucide-react';

export default function SettingsPage() {
    // State
    const [audioSource, setAudioSource] = useState('default');
    const [devices, setDevices] = useState<{id: string, name: string}[]>([
        { id: 'default', name: 'Default Microphone' },
        { id: 'system', name: 'System Audio (Loopback)' }
    ]); // Initial mock data
    const [transMode, setTransMode] = useState('zh_to_en');
    const [fontSize, setFontSize] = useState(24);
    const [opacity, setOpacity] = useState(0.6);
    const [maxLines, setMaxLines] = useState(3);
    const [initialPrompt, setInitialPrompt] = useState('');

    // Load settings on mount
    useEffect(() => {
        if (typeof window !== 'undefined') {
            setInitialPrompt(localStorage.getItem('initialPrompt') || "");
            setFontSize(parseInt(localStorage.getItem('fontSize') || "24"));
            setOpacity(parseFloat(localStorage.getItem('opacity') || "0.6"));
            setMaxLines(parseInt(localStorage.getItem('maxLines') || "3"));
            setAudioSource(localStorage.getItem('audioSource') || "default");
            setTransMode(localStorage.getItem('transMode') || "zh_to_en");

            // Fetch devices from Rust
            invoke<{id: string, name: string}[]>('get_audio_devices')
                .then(devs => {
                    // Prepend System Audio option
                    const allDevs = [
                         { id: 'default', name: 'Default Microphone' }, // Keep default option
                         ...devs
                    ];
                    // Add loopback mock if not detected (cpal loopback is tricky to list as input sometimes)
                    if (!devs.find(d => d.name.toLowerCase().includes('loopback') || d.name.toLowerCase().includes('stereo mix'))) {
                        allDevs.push({ id: 'system', name: 'System Audio (Loopback)' });
                    }
                    setDevices(allDevs);
                })
                .catch(err => console.error("Failed to load audio devices:", err));
        }
    }, []);

    // Save helpers
    const saveSetting = (key: string, value: string) => {
        localStorage.setItem(key, value);
        // Dispatch storage event manually for same-window updates if needed, 
        // though Main window is separate, so it will pick up changes via Storage Event listener or manual reload.
        // Actually, separate windows share localStorage, but 'storage' event only fires on OTHER windows.
        // This is perfect for syncing Main window.
    };

    return (
        <div className="min-h-screen bg-neutral-900 text-white p-6 select-none">
            <h1 className="text-2xl font-bold mb-6 flex items-center gap-2">
                <SettingsIcon className="w-6 h-6 text-blue-400" />
                Settings
            </h1>

            <div className="space-y-8">
                {/* Audio Section */}
                <section className="space-y-4">
                    <h2 className="text-lg font-semibold text-gray-400 border-b border-gray-700 pb-2 flex items-center gap-2">
                        <Mic className="w-4 h-4" /> Audio Source
                    </h2>
                    <div className="space-y-2">
                        <label className="block text-sm text-gray-400">Input Device</label>
                        <select 
                            value={audioSource}
                            onChange={(e) => {
                                setAudioSource(e.target.value);
                                saveSetting('audioSource', e.target.value);
                            }}
                            className="w-full bg-neutral-800 border border-neutral-700 rounded p-2 focus:ring-2 focus:ring-blue-500 outline-none"
                        >
                            {devices.map(d => (
                                <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                        </select>
                        <p className="text-xs text-gray-500">
                            Select 'System Audio' to capture computer sound (e.g. Teams, YouTube).
                        </p>
                    </div>
                </section>

                {/* Translation Section */}
                <section className="space-y-4">
                    <h2 className="text-lg font-semibold text-gray-400 border-b border-gray-700 pb-2 flex items-center gap-2">
                        <Globe className="w-4 h-4" /> Translation
                    </h2>
                    <div className="flex gap-4">
                        <button 
                            onClick={() => { setTransMode('zh_to_en'); saveSetting('transMode', 'zh_to_en'); }}
                            className={`flex-1 py-3 rounded border transition-all ${transMode === 'zh_to_en' ? 'bg-blue-600 border-blue-500 text-white shadow-lg' : 'bg-neutral-800 border-neutral-700 text-gray-400 hover:bg-neutral-700'}`}
                        >
                            ZH → EN
                        </button>
                        <button 
                            onClick={() => { setTransMode('en_to_zh'); saveSetting('transMode', 'en_to_zh'); }}
                            className={`flex-1 py-3 rounded border transition-all ${transMode === 'en_to_zh' ? 'bg-blue-600 border-blue-500 text-white shadow-lg' : 'bg-neutral-800 border-neutral-700 text-gray-400 hover:bg-neutral-700'}`}
                        >
                            EN → ZH
                        </button>
                    </div>
                </section>

                {/* Appearance Section */}
                <section className="space-y-4">
                    <h2 className="text-lg font-semibold text-gray-400 border-b border-gray-700 pb-2 flex items-center gap-2">
                        <Monitor className="w-4 h-4" /> Appearance
                    </h2>
                    
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <label className="block text-sm text-gray-400">Font Size ({fontSize}px)</label>
                            <input 
                                type="range" min="16" max="48" step="2"
                                value={fontSize}
                                onChange={(e) => {
                                    const val = parseInt(e.target.value);
                                    setFontSize(val);
                                    saveSetting('fontSize', val.toString());
                                }}
                                className="w-full h-2 bg-neutral-700 rounded-lg appearance-none cursor-pointer"
                            />
                        </div>

                        <div className="space-y-2">
                            <label className="block text-sm text-gray-400">Bg Opacity ({Math.round(opacity * 100)}%)</label>
                            <input 
                                type="range" min="0" max="1" step="0.1"
                                value={opacity}
                                onChange={(e) => {
                                    const val = parseFloat(e.target.value);
                                    setOpacity(val);
                                    saveSetting('opacity', val.toString());
                                }}
                                className="w-full h-2 bg-neutral-700 rounded-lg appearance-none cursor-pointer"
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <label className="block text-sm text-gray-400">Max Lines ({maxLines})</label>
                        <input 
                            type="number" min="1" max="10"
                            value={maxLines}
                            onChange={(e) => {
                                const val = parseInt(e.target.value);
                                setMaxLines(val);
                                saveSetting('maxLines', val.toString());
                            }}
                            className="w-full bg-neutral-800 border border-neutral-700 rounded p-2"
                        />
                    </div>
                </section>

                {/* AI Context Section */}
                <section className="space-y-4">
                    <h2 className="text-lg font-semibold text-gray-400 border-b border-gray-700 pb-2 flex items-center gap-2">
                        <Type className="w-4 h-4" /> AI Context
                    </h2>
                    <div className="space-y-2">
                        <label className="block text-sm text-gray-400">Initial Prompt (Context/Keywords)</label>
                        <textarea 
                            value={initialPrompt}
                            onChange={(e) => {
                                setInitialPrompt(e.target.value);
                                saveSetting('initialPrompt', e.target.value);
                            }}
                            placeholder="e.g. This is a meeting about AI architecture..."
                            className="w-full h-24 bg-neutral-800 border border-neutral-700 rounded p-2 focus:ring-2 focus:ring-blue-500 outline-none resize-none"
                        />
                    </div>
                </section>
            </div>
        </div>
    );
}

function SettingsIcon({className}: {className?: string}) {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.47a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.35a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
    )
}
