"use client";

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, Trash2, Book, Loader2, Pencil, Check, X } from 'lucide-react';
import { api, GlossaryEntry } from '@/lib/api';

interface GlossaryManagerProps {
    userUpn: string;
}

const CATEGORIES = [
    { value: 'company', label: '公司' },
    { value: 'person', label: '人名' },
    { value: 'product', label: '產品' },
    { value: 'other', label: '其他' },
];

export const GlossaryManager: React.FC<GlossaryManagerProps> = ({ userUpn }) => {
    const [entries, setEntries] = useState<GlossaryEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [wrongText, setWrongText] = useState('');
    const [correctText, setCorrectText] = useState('');
    const [category, setCategory] = useState('company');
    const [adding, setAdding] = useState(false);
    const [error, setError] = useState('');
    // Edit state
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editWrong, setEditWrong] = useState('');
    const [editCorrect, setEditCorrect] = useState('');
    const [editCategory, setEditCategory] = useState('company');
    const [saving, setSaving] = useState(false);

    const loadEntries = useCallback(async () => {
        if (!userUpn) return;
        try {
            setLoading(true);
            const data = await api.listGlobalGlossary(userUpn);
            setEntries(data);
        } catch (e) {
            console.error('Failed to load glossary:', e);
        } finally {
            setLoading(false);
        }
    }, [userUpn]);

    useEffect(() => { loadEntries(); }, [loadEntries]);

    const handleAdd = async () => {
        if (!wrongText.trim() || !correctText.trim()) {
            setError('請填寫錯誤轉錄和正確名稱');
            return;
        }
        setAdding(true);
        setError('');
        try {
            await api.createGlobalEntry(userUpn, wrongText.trim(), correctText.trim(), category);
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
            await api.deleteGlobalEntry(userUpn, entryId);
            setEntries(prev => prev.filter(e => e.id !== entryId));
        } catch (e) {
            console.error('Delete failed:', e);
        }
    };

    const startEdit = (entry: GlossaryEntry) => {
        setEditingId(entry.id);
        setEditWrong(entry.wrong_text);
        setEditCorrect(entry.correct_text);
        setEditCategory(entry.category || 'company');
    };

    const cancelEdit = () => {
        setEditingId(null);
        setEditWrong('');
        setEditCorrect('');
    };

    const saveEdit = async () => {
        if (!editingId || !editWrong.trim() || !editCorrect.trim()) return;
        setSaving(true);
        try {
            await api.updateGlobalEntry(userUpn, editingId, editWrong.trim(), editCorrect.trim(), editCategory);
            setEditingId(null);
            await loadEntries();
        } catch (e) {
            console.error('Update failed:', e);
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="bg-card rounded-xl border border-border p-6">
            <div className="flex items-center gap-2 mb-4">
                <Book size={20} className="text-primary" />
                <h3 className="font-bold text-foreground">全域專有名詞對照表</h3>
                <span className="text-xs text-muted-foreground ml-auto">{entries.length} 筆</span>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
                設定常見的 ASR 轉錄錯誤修正，所有新會議轉錄時會自動套用。
            </p>

            {/* Add form */}
            <div className="flex flex-wrap gap-2 mb-4">
                <input
                    type="text"
                    value={wrongText}
                    onChange={(e) => setWrongText(e.target.value)}
                    placeholder="錯誤轉錄（如：晴威）"
                    className="flex-1 min-w-[120px] px-3 py-2 text-sm border border-border rounded-lg bg-background text-foreground"
                    onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                />
                <span className="self-center text-muted-foreground">→</span>
                <input
                    type="text"
                    value={correctText}
                    onChange={(e) => setCorrectText(e.target.value)}
                    placeholder="正確名稱（如：勤崴國際）"
                    className="flex-1 min-w-[120px] px-3 py-2 text-sm border border-border rounded-lg bg-background text-foreground"
                    onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                />
                <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="px-3 py-2 text-sm border border-border rounded-lg bg-background text-foreground"
                >
                    {CATEGORIES.map(c => (
                        <option key={c.value} value={c.value}>{c.label}</option>
                    ))}
                </select>
                <button
                    onClick={handleAdd}
                    disabled={adding || !wrongText.trim() || !correctText.trim()}
                    className="px-3 py-2 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 flex items-center gap-1"
                >
                    {adding ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                    新增
                </button>
            </div>
            {error && <p className="text-sm text-destructive mb-3">{error}</p>}

            {/* Entry list */}
            {loading ? (
                <div className="flex justify-center py-4">
                    <Loader2 className="animate-spin text-muted-foreground" size={20} />
                </div>
            ) : entries.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                    尚未新增對照表，新增後可提高 ASR 轉錄準確率
                </p>
            ) : (
                <div className="space-y-1 max-h-[300px] overflow-y-auto">
                    {entries.map(entry => (
                        <div key={entry.id} className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted/50 group">
                            {editingId === entry.id ? (
                                /* Edit mode */
                                <>
                                    <select
                                        value={editCategory}
                                        onChange={(e) => setEditCategory(e.target.value)}
                                        className="text-xs px-1.5 py-0.5 border border-border rounded bg-background"
                                    >
                                        {CATEGORIES.map(c => (
                                            <option key={c.value} value={c.value}>{c.label}</option>
                                        ))}
                                    </select>
                                    <input
                                        type="text"
                                        value={editWrong}
                                        onChange={(e) => setEditWrong(e.target.value)}
                                        className="flex-1 min-w-[80px] px-2 py-1 text-sm border border-border rounded bg-background text-foreground"
                                        onKeyDown={(e) => e.key === 'Enter' && saveEdit()}
                                    />
                                    <span className="text-muted-foreground text-xs">→</span>
                                    <input
                                        type="text"
                                        value={editCorrect}
                                        onChange={(e) => setEditCorrect(e.target.value)}
                                        className="flex-1 min-w-[80px] px-2 py-1 text-sm border border-border rounded bg-background text-foreground"
                                        onKeyDown={(e) => e.key === 'Enter' && saveEdit()}
                                    />
                                    <button
                                        onClick={saveEdit}
                                        disabled={saving}
                                        className="p-1 text-green-600 hover:text-green-700"
                                        title="儲存"
                                    >
                                        {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                                    </button>
                                    <button
                                        onClick={cancelEdit}
                                        className="p-1 text-muted-foreground hover:text-foreground"
                                        title="取消"
                                    >
                                        <X size={14} />
                                    </button>
                                </>
                            ) : (
                                /* Display mode */
                                <>
                                    <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                                        {CATEGORIES.find(c => c.value === entry.category)?.label || '其他'}
                                    </span>
                                    <span className="text-sm text-foreground">{entry.wrong_text}</span>
                                    <span className="text-muted-foreground text-xs">→</span>
                                    <span className="text-sm font-medium text-foreground">{entry.correct_text}</span>
                                    {entry.usage_count ? (
                                        <span className="text-xs text-muted-foreground ml-auto mr-2">使用 {entry.usage_count} 次</span>
                                    ) : null}
                                    <button
                                        onClick={() => startEdit(entry)}
                                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:text-brand-cta"
                                        title="修改"
                                    >
                                        <Pencil size={14} />
                                    </button>
                                    <button
                                        onClick={() => handleDelete(entry.id)}
                                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:text-destructive"
                                        title="刪除"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};
