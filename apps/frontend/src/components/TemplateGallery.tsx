"use client";

import React, { useState, useEffect, useCallback } from 'react';
import {
    FileText, DollarSign, Users, Code, Target, Lightbulb,
    Clock, RotateCcw, ClipboardList, GraduationCap,
    Eye, Copy, Pencil, Trash2, X, Plus, ChevronDown, ChevronUp, ChevronRight,
    Loader2, Search,
} from 'lucide-react';
import { api, TemplateDTO, TemplateSectionDTO, CreateTemplateDTO, UpdateTemplateDTO } from '@/lib/api';
import { ErrorState } from './ui/error-state';

// Icon mapping from string to component
const ICON_MAP: Record<string, React.ElementType> = {
    FileText, DollarSign, Users, Code, Target, Lightbulb,
    Clock, RotateCcw, ClipboardList, GraduationCap,
};

// Category labels
const CATEGORIES: Record<string, string> = {
    all: '全部',
    general: '通用',
    sales: '業務',
    hr: '人資',
    engineering: '工程',
    custom: '自訂',
};

interface TemplateGalleryProps {
    onBack?: () => void;
}

export const TemplateGallery = ({ onBack }: TemplateGalleryProps) => {
    const [templates, setTemplates] = useState<TemplateDTO[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [activeCategory, setActiveCategory] = useState('all');
    const [searchQuery, setSearchQuery] = useState('');
    const [previewTemplate, setPreviewTemplate] = useState<TemplateDTO | null>(null);
    const [editingTemplate, setEditingTemplate] = useState<TemplateDTO | null>(null);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null);

    const fetchTemplates = useCallback(async () => {
        setIsLoading(true);
        try {
            const data = await api.getTemplates();
            setTemplates(data);
            setError(null);
        } catch (e) {
            setError(e instanceof Error ? e.message : '載入模板失敗');
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

    const filteredTemplates = templates.filter(t => {
        const matchCategory = activeCategory === 'all' || t.category === activeCategory;
        const matchSearch = !searchQuery ||
            t.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            t.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
            t.tags.some(tag => tag.includes(searchQuery));
        return matchCategory && matchSearch;
    });

    const handleFork = async (template: TemplateDTO) => {
        try {
            const forked = await api.createTemplate({
                name: `${template.name}_custom_${Date.now()}`,
                display_name: `${template.display_name} (自訂)`,
                description: template.description,
                category: 'custom',
                icon: template.icon,
                color: template.color,
                tags: [...template.tags],
                fork_from: template.name,
            });
            setTemplates(prev => [...prev, forked]);
            setEditingTemplate(forked);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Fork 失敗');
        }
    };

    const handleDelete = async (id: string) => {
        try {
            await api.deleteTemplate(id);
            setTemplates(prev => prev.filter(t => t.id !== id));
            setShowDeleteConfirm(null);
        } catch (e) {
            setError(e instanceof Error ? e.message : '刪除失敗');
        }
    };

    const handleSaveEdit = async (id: string, data: UpdateTemplateDTO) => {
        try {
            const updated = await api.updateTemplate(id, data);
            setTemplates(prev => prev.map(t => t.id === id ? updated : t));
            setEditingTemplate(null);
        } catch (e) {
            setError(e instanceof Error ? e.message : '儲存失敗');
        }
    };

    // Editor sub-view
    if (editingTemplate) {
        return (
            <TemplateEditor
                template={editingTemplate}
                onSave={(data) => handleSaveEdit(editingTemplate.id, data)}
                onCancel={() => setEditingTemplate(null)}
                onDelete={() => {
                    setShowDeleteConfirm(editingTemplate.id);
                    setEditingTemplate(null);
                }}
            />
        );
    }

    return (
        <div className="p-6 md:p-8 max-w-5xl mx-auto overflow-auto">
            {/* Header — P1 補 back 按鈕（audit 反映主視圖無返回入口） */}
            <div className="mb-8">
                <div className="flex items-center gap-3 mb-2">
                    {onBack && (
                        <button
                            onClick={onBack}
                            aria-label="返回 Dashboard"
                            title="返回"
                            className="p-2 hover:bg-muted rounded-full text-muted-foreground transition-colors"
                        >
                            <ChevronRight size={20} className="rotate-180" />
                        </button>
                    )}
                    <h1 className="text-2xl font-bold text-foreground">模板管理</h1>
                </div>
                <p className="text-muted-foreground">選擇適合會議類型的摘要模板，或 Fork 建立客製版本</p>
            </div>

            {/* Search */}
            <div className="relative mb-6">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" size={18} />
                <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="搜尋模板名稱或標籤..."
                    className="w-full pl-11 pr-4 py-2.5 bg-card border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-cta focus:border-transparent text-sm transition-all"
                />
            </div>

            {/* Category Tabs */}
            <div className="flex gap-2 mb-6 flex-wrap">
                {Object.entries(CATEGORIES).map(([key, label]) => (
                    <button
                        key={key}
                        onClick={() => setActiveCategory(key)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                            activeCategory === key
                                ? 'bg-brand-cta text-white shadow-md'
                                : 'bg-card border border-border text-muted-foreground hover:bg-muted'
                        }`}
                    >
                        {label}
                    </button>
                ))}
            </div>

            {/* Error — 統一 <ErrorState> */}
            {error && (
                <div className="mb-6">
                    <ErrorState title="模板載入失敗" message={error} onRetry={fetchTemplates} />
                </div>
            )}

            {/* Loading */}
            {isLoading && (
                <div className="text-center py-16">
                    <Loader2 size={48} className="mx-auto text-brand-cta animate-spin mb-4" />
                    <p className="text-muted-foreground">載入模板中...</p>
                </div>
            )}

            {/* Template Grid — P2: items-stretch 讓同列卡片高度一致；
                  內部 flex column 把 actions 推到底部對齊 */}
            {!isLoading && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-stretch">
                    {filteredTemplates.map(tpl => {
                        const IconComp = ICON_MAP[tpl.icon] || FileText;
                        return (
                            <div key={tpl.id} className="bg-card rounded-xl border border-border p-5 hover:shadow-lg transition-all group flex w-full">
                                <div className="flex items-start gap-4 w-full">
                                    <div className={`w-11 h-11 bg-${tpl.color}/15 rounded-xl flex items-center justify-center text-${tpl.color} flex-shrink-0`}>
                                        <IconComp size={22} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1">
                                            <h3 className="font-semibold text-foreground truncate">{tpl.display_name}</h3>
                                            {tpl.is_system && (
                                                <span className="px-2 py-0.5 text-xs bg-brand-cta/15 text-brand-cta rounded-full flex-shrink-0">系統</span>
                                            )}
                                        </div>
                                        <p className="text-sm text-muted-foreground mb-3 line-clamp-2">{tpl.description}</p>
                                        <div className="flex flex-wrap gap-1.5 mb-3">
                                            {tpl.tags.map(tag => (
                                                <span key={tag} className="px-2 py-0.5 text-xs bg-muted text-muted-foreground rounded">{tag}</span>
                                            ))}
                                        </div>
                                        {/* Actions — opacity-0 群組改 group-hover/group-focus-within 才能鍵盤可達 */}
                                        <div className="flex gap-2 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
                                            <button
                                                onClick={() => setPreviewTemplate(tpl)}
                                                aria-label={`預覽模板：${tpl.display_name}`}
                                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground transition-colors"
                                            >
                                                <Eye size={14} /> 預覽
                                            </button>
                                            <button
                                                onClick={() => handleFork(tpl)}
                                                aria-label={`Fork 模板：${tpl.display_name}`}
                                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-brand-cta/10 rounded-lg hover:bg-brand-cta/20 text-brand-cta transition-colors"
                                            >
                                                <Copy size={14} /> Fork
                                            </button>
                                            {!tpl.is_system && (
                                                <>
                                                    <button
                                                        onClick={() => setEditingTemplate(tpl)}
                                                        aria-label={`編輯模板：${tpl.display_name}`}
                                                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground transition-colors"
                                                    >
                                                        <Pencil size={14} /> 編輯
                                                    </button>
                                                    <button
                                                        onClick={() => setShowDeleteConfirm(tpl.id)}
                                                        aria-label={`刪除模板：${tpl.display_name}`}
                                                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-status-error/10 rounded-lg hover:bg-status-error/20 text-status-error transition-colors"
                                                    >
                                                        <Trash2 size={14} />
                                                    </button>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {!isLoading && filteredTemplates.length === 0 && (
                <div className="text-center py-16">
                    <FileText size={48} className="mx-auto text-muted-foreground/30 mb-4" />
                    <p className="text-muted-foreground">沒有符合的模板</p>
                </div>
            )}

            {/* Preview Modal */}
            {previewTemplate && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setPreviewTemplate(null)}>
                    <div className="bg-card rounded-2xl border border-border max-w-lg w-full max-h-[80vh] overflow-auto p-6" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-bold text-foreground">{previewTemplate.display_name}</h2>
                            <button onClick={() => setPreviewTemplate(null)} aria-label="關閉預覽" className="p-2 hover:bg-muted rounded-lg text-muted-foreground">
                                <X size={20} />
                            </button>
                        </div>
                        <p className="text-sm text-muted-foreground mb-4">{previewTemplate.description}</p>
                        <h3 className="text-sm font-semibold text-foreground mb-3">輸出段落結構</h3>
                        <div className="space-y-3">
                            {previewTemplate.sections.map((s, i) => (
                                <div key={i} className="bg-muted/50 rounded-lg p-3">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="text-sm font-medium text-foreground">{s.title}</span>
                                        <span className="px-1.5 py-0.5 text-xs bg-card border border-border rounded text-muted-foreground font-mono">{s.output_key}</span>
                                        <span className="px-1.5 py-0.5 text-xs bg-brand-violet/10 text-brand-violet rounded">{s.output_type}</span>
                                    </div>
                                    <p className="text-xs text-muted-foreground">{s.instruction}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* Delete Confirm Dialog */}
            {showDeleteConfirm && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowDeleteConfirm(null)}>
                    <div className="bg-card rounded-2xl border border-border max-w-sm w-full p-6" onClick={e => e.stopPropagation()}>
                        <h2 className="text-lg font-bold text-foreground mb-2">確認刪除</h2>
                        <p className="text-sm text-muted-foreground mb-4">此操作無法復原。確定要刪除此模板？</p>
                        <div className="flex justify-end gap-3">
                            <button onClick={() => setShowDeleteConfirm(null)} className="px-4 py-2 text-sm bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground">取消</button>
                            <button onClick={() => handleDelete(showDeleteConfirm)} className="px-4 py-2 text-sm bg-status-error text-white rounded-lg hover:bg-status-error/90">刪除</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};


// --- Template Editor Sub-Component ---

interface TemplateEditorProps {
    template: TemplateDTO;
    onSave: (data: UpdateTemplateDTO) => void;
    onCancel: () => void;
    onDelete: () => void;
}

const TemplateEditor = ({ template, onSave, onCancel, onDelete }: TemplateEditorProps) => {
    const [displayName, setDisplayName] = useState(template.display_name);
    const [description, setDescription] = useState(template.description);
    const [category, setCategory] = useState(template.category);
    const [tags, setTags] = useState(template.tags.join(', '));
    const [sections, setSections] = useState<TemplateSectionDTO[]>(template.sections);

    const addSection = () => {
        setSections(prev => [...prev, { title: '', instruction: '', output_key: '', output_type: 'list' }]);
    };

    const updateSection = (index: number, field: keyof TemplateSectionDTO, value: string) => {
        setSections(prev => prev.map((s, i) => i === index ? { ...s, [field]: value } : s));
    };

    const removeSection = (index: number) => {
        setSections(prev => prev.filter((_, i) => i !== index));
    };

    const moveSection = (index: number, direction: -1 | 1) => {
        const newIndex = index + direction;
        if (newIndex < 0 || newIndex >= sections.length) return;
        setSections(prev => {
            const arr = [...prev];
            [arr[index], arr[newIndex]] = [arr[newIndex], arr[index]];
            return arr;
        });
    };

    const handleSubmit = () => {
        onSave({
            display_name: displayName,
            description,
            category,
            tags: tags.split(',').map(t => t.trim()).filter(Boolean),
            sections,
        });
    };

    return (
        <div className="p-6 md:p-8 max-w-3xl mx-auto overflow-auto">
            <div className="flex items-center justify-between mb-8">
                <h1 className="text-2xl font-bold text-foreground">編輯模板</h1>
                <div className="flex gap-2">
                    <button onClick={onDelete} className="px-3 py-2 text-sm text-status-error hover:bg-status-error/10 rounded-lg transition-colors">
                        <Trash2 size={16} />
                    </button>
                    <button onClick={onCancel} className="px-4 py-2 text-sm bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground">取消</button>
                    <button onClick={handleSubmit} className="px-4 py-2 text-sm bg-brand-cta text-white rounded-lg hover:bg-brand-cta/90">儲存</button>
                </div>
            </div>

            {/* Basic info */}
            <div className="space-y-4 mb-8">
                <div>
                    <label className="block text-sm font-medium text-foreground mb-1">模板名稱</label>
                    <input value={displayName} onChange={e => setDisplayName(e.target.value)}
                        className="w-full px-3 py-2 bg-card border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-cta text-sm" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-foreground mb-1">描述</label>
                    <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2}
                        className="w-full px-3 py-2 bg-card border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-cta text-sm resize-none" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-foreground mb-1">分類</label>
                        <select value={category} onChange={e => setCategory(e.target.value)}
                            className="w-full px-3 py-2 bg-card border border-border rounded-lg text-sm">
                            <option value="general">通用</option>
                            <option value="sales">業務</option>
                            <option value="hr">人資</option>
                            <option value="engineering">工程</option>
                            <option value="custom">自訂</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-foreground mb-1">標籤（逗號分隔）</label>
                        <input value={tags} onChange={e => setTags(e.target.value)}
                            className="w-full px-3 py-2 bg-card border border-border rounded-lg text-sm" placeholder="摘要, 待辦" />
                    </div>
                </div>
            </div>

            {/* Sections */}
            <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-foreground">輸出段落</h2>
                <button onClick={addSection} className="flex items-center gap-1 px-3 py-1.5 text-xs bg-brand-cta/10 text-brand-cta rounded-lg hover:bg-brand-cta/20 transition-colors">
                    <Plus size={14} /> 新增段落
                </button>
            </div>

            <div className="space-y-4">
                {sections.map((s, i) => (
                    <div key={i} className="bg-card border border-border rounded-xl p-4">
                        <div className="flex items-center gap-2 mb-3">
                            <span className="text-xs text-muted-foreground">#{i + 1}</span>
                            <div className="flex gap-1 ml-auto">
                                <button onClick={() => moveSection(i, -1)} disabled={i === 0} aria-label="上移此段" title="上移" className="p-1 hover:bg-muted rounded disabled:opacity-30">
                                    <ChevronUp size={14} />
                                </button>
                                <button onClick={() => moveSection(i, 1)} disabled={i === sections.length - 1} aria-label="下移此段" title="下移" className="p-1 hover:bg-muted rounded disabled:opacity-30">
                                    <ChevronDown size={14} />
                                </button>
                                <button onClick={() => removeSection(i)} aria-label="刪除此段" title="刪除" className="p-1 hover:bg-status-error/10 text-status-error rounded">
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-3 mb-3">
                            <input value={s.title} onChange={e => updateSection(i, 'title', e.target.value)}
                                placeholder="段落標題" className="px-3 py-2 bg-muted border border-border rounded-lg text-sm" />
                            <div className="flex gap-2">
                                <input value={s.output_key} onChange={e => updateSection(i, 'output_key', e.target.value)}
                                    placeholder="output_key" className="flex-1 px-3 py-2 bg-muted border border-border rounded-lg text-sm font-mono" />
                                <select value={s.output_type} onChange={e => updateSection(i, 'output_type', e.target.value)}
                                    className="px-2 py-2 bg-muted border border-border rounded-lg text-sm">
                                    <option value="string">string</option>
                                    <option value="list">list</option>
                                    <option value="object">object</option>
                                </select>
                            </div>
                        </div>
                        <textarea value={s.instruction} onChange={e => updateSection(i, 'instruction', e.target.value)}
                            placeholder="LLM 指令，例如：列出所有待辦事項" rows={2}
                            className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-sm resize-none" />
                    </div>
                ))}
            </div>
        </div>
    );
};
