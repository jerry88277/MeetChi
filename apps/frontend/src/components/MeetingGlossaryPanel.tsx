"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, BookOpen, Loader2, RefreshCw } from 'lucide-react';
import { api, GlossaryEntry } from '@/lib/api';

interface MeetingGlossaryPanelProps {
    meetingId: string;
    userUpn: string;
}

export const MeetingGlossaryPanel: React.FC<MeetingGlossaryPanelProps> = ({ meetingId, userUpn }) => {
    const [entries, setEntries] = useState<GlossaryEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [wrongText, setWrongText] = useState('');
    const [correctText, setCorrectText] = useState('');
    const [adding, setAdding] = useState(false);
    const [applying, setApplying] = useState(false);
    const [applyResult, setApplyResult] = useState<string | null>(null);
    const [error, setError] = useState('');

    const loadEntries = useCallback(async () => {
        try {
            setLoading(true);
            const data = await api.listMeetingGlossary(meetingId);
            setEntries(data);
        } catch (e) {
            console.error('Failed to load meeting glossary:', e);
        } finally {
            setLoading(false);
        }
    }, [meetingId]);

    useEffect(() => { loadEntries(); }, [loadEntries]);

    const handleAdd = async () => {
        if (!wrongText.trim() || !correctText.trim()) {
            setError('請填寫錯誤轉錄和正確名稱');
            return;
        }
        setAdding(true);
        setError('');
        try {
            await api.createMeetingEntry(meetingId, wrongText.trim(), correctText.trim());
            setWrongText('');
            setCorrectText('');
            await loadEntries();
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : '新增失敗';
            setError(msg.includes('409') ? '此詞彙已存在' : msg);
        } finally {
            setAdding(false);
        }
    };

    const handleDelete = async (entryId: string) => {
        try {
            await api.deleteMeetingEntry(meetingId, entryId);
            setEntries(prev => prev.filter(e => e.id !== entryId));
        } catch (e) {
            console.error('Delete failed:', e);
        }
    };

    const handleApply = async () => {
        setApplying(true);
        setApplyResult(null);
        try {
            const result = await api.applyGlossaryCorrection(meetingId, userUpn);
            setApplyResult(`已修正 ${result.segments_corrected} 個段落`);
            setTimeout(() => setApplyResult(null), 5000);
        } catch (e) {
            console.error('Apply failed:', e);
            setApplyResult('修正失敗');
        } finally {
            setApplying(false);
        }
    };

    return (
        <div className="bg-card rounded-xl border border-border p-4">
            <div className="flex items-center gap-2 mb-3">
                <BookOpen size={16} className="text-primary" />
                <h4 className="font-semibold text-sm text-foreground">本會議專有名詞</h4>
                <span className="text-xs text-muted-foreground ml-auto">{entries.length} 筆</span>
            </div>
            <p className="text-xs text-muted-foreground mb-3">
                新增本會議特有的名詞修正，與全域對照表聯集後套用（Local 優先）。
            </p>

            {/* Add row */}
            <div className="flex gap-2 mb-3">
                <input
                    type="text"
                    value={wrongText}
                    onChange={(e) => setWrongText(e.target.value)}
                    placeholder="錯誤轉錄"
                    className="flex-1 min-w-[80px] px-2 py-1.5 text-xs border border-border rounded-lg bg-background text-foreground"
                    onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                />
                <span className="self-center text-muted-foreground text-xs">→</span>
                <input
                    type="text"
                    value={correctText}
                    onChange={(e) => setCorrectText(e.target.value)}
                    placeholder="正確名稱"
                    className="flex-1 min-w-[80px] px-2 py-1.5 text-xs border border-border rounded-lg bg-background text-foreground"
                    onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                />
                <button
                    onClick={handleAdd}
                    disabled={adding || !wrongText.trim() || !correctText.trim()}
                    className="px-2 py-1.5 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50"
                >
                    {adding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                </button>
            </div>
            {error && <p className="text-xs text-destructive mb-2">{error}</p>}

            {/* Entry list */}
            {loading ? (
                <div className="flex justify-center py-2">
                    <Loader2 className="animate-spin text-muted-foreground" size={14} />
                </div>
            ) : entries.length > 0 && (
                <div className="space-y-0.5 mb-3">
                    {entries.map(entry => (
                        <div key={entry.id} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-muted/50 group text-xs">
                            <span className="text-foreground">{entry.wrong_text}</span>
                            <span className="text-muted-foreground">→</span>
                            <span className="font-medium text-foreground">{entry.correct_text}</span>
                            <button
                                onClick={() => handleDelete(entry.id)}
                                className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:text-destructive"
                            >
                                <Trash2 size={12} />
                            </button>
                        </div>
                    ))}
                </div>
            )}

            {/* Apply button */}
            <button
                onClick={handleApply}
                disabled={applying}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs bg-muted hover:bg-muted/80 text-foreground rounded-lg transition-colors disabled:opacity-50"
            >
                {applying ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                套用修正到逐字稿
            </button>
            {applyResult && (
                <p className="text-xs text-center mt-1.5 text-status-success">{applyResult}</p>
            )}
        </div>
    );
};
