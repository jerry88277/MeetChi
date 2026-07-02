"use client";

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
    FileText, DollarSign, Users, Code, Target, Lightbulb,
    Clock, RotateCcw, ClipboardList, GraduationCap,
    Eye, Copy, Pencil, Trash2, X, Plus, ChevronDown, ChevronUp, ChevronRight,
    Loader2, Search,
} from 'lucide-react';
import { toast } from 'sonner';
import { api, TemplateDTO, TemplateSectionDTO, UpdateTemplateDTO } from '@/lib/api';
import { ErrorState } from './ui/error-state';
import { useEscape } from '@/hooks/useEscape';

// Icon mapping from string to component
const ICON_MAP: Record<string, React.ElementType> = {
    FileText, DollarSign, Users, Code, Target, Lightbulb,
    Clock, RotateCcw, ClipboardList, GraduationCap,
};

// T-A3 / T-F4：動態 `bg-${color}` class 在生產 build 會被 Tailwind purge，改用靜態 map。
// 後端目前的顏色值：brand-cta / brand-violet / status-success / status-warning。
const COLOR_MAP: Record<string, { bg: string; text: string; dot: string }> = {
    'brand-cta': { bg: 'bg-brand-cta/15', text: 'text-brand-cta', dot: 'bg-brand-cta' },
    'brand-violet': { bg: 'bg-brand-violet/15', text: 'text-brand-violet', dot: 'bg-brand-violet' },
    'status-success': { bg: 'bg-status-success/15', text: 'text-status-success', dot: 'bg-status-success' },
    'status-warning': { bg: 'bg-status-warning/15', text: 'text-status-warning', dot: 'bg-status-warning' },
};
const DEFAULT_COLOR = { bg: 'bg-brand-cta/15', text: 'text-brand-cta', dot: 'bg-brand-cta' };
// Legacy alias: templates seeded before the DDG rename stored color='brand-accent'
// (which was itself an alias of brand-violet). Normalize so existing DB rows still render violet.
const colorClasses = (color: string) => COLOR_MAP[color === 'brand-accent' ? 'brand-violet' : color] || DEFAULT_COLOR;

// T-A5：編輯器可選圖示 / 顏色（限定為已在 Tailwind safelist 的值）
const ICON_OPTIONS: string[] = Object.keys(ICON_MAP);
const COLOR_OPTIONS: string[] = Object.keys(COLOR_MAP);

// T-B2：使用者「預設模板」偏好（localStorage）。上傳設定視窗初始化時讀取。
const DEFAULT_TEMPLATE_KEY = 'meetchi:default_template';

// T-A2：模板異動後廣播事件，讓其他各自 getTemplates 的畫面（Dashboard/DetailView）重抓。
const TEMPLATES_CHANGED_EVENT = 'meetchi:templates-changed';
const broadcastTemplatesChanged = () => {
    try { window.dispatchEvent(new CustomEvent(TEMPLATES_CHANGED_EVENT)); } catch { /* ignore */ }
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

const OUTPUT_TYPE_LABELS: Record<string, string> = {
    string: '一段文字',
    list: '條列清單',
    object: '結構化欄位',
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
    // T-A4：從零建立（空白）新模板
    const [isCreatingNew, setIsCreatingNew] = useState(false);
    // T-B4/T-E2：刪除確認改單一對話框，直接帶入使用數
    const [deleteConfirm, setDeleteConfirm] = useState<TemplateDTO | null>(null);
    const [isDeleting, setIsDeleting] = useState(false);
    const [forkTarget, setForkTarget] = useState<TemplateDTO | null>(null);
    const [forkName, setForkName] = useState('');
    // T-B2：目前預設模板 name
    const [defaultTemplate, setDefaultTemplate] = useState<string | null>(null);

    useEffect(() => {
        try { setDefaultTemplate(localStorage.getItem(DEFAULT_TEMPLATE_KEY)); } catch { /* ignore */ }
    }, []);

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

    // T-D1：與 DetailView/上傳下游一致——僅顯示啟用中的模板。
    const activeTemplates = useMemo(
        () => templates.filter(t => t.is_active !== false),
        [templates]
    );

    // T-A6：搜尋對名稱/描述/標籤皆不分大小寫。
    const filteredTemplates = useMemo(() => {
        const q = searchQuery.trim().toLowerCase();
        return activeTemplates.filter(t => {
            const matchCategory = activeCategory === 'all' || t.category === activeCategory;
            const matchSearch = !q ||
                t.display_name.toLowerCase().includes(q) ||
                t.description.toLowerCase().includes(q) ||
                t.tags.some(tag => tag.toLowerCase().includes(q));
            return matchCategory && matchSearch;
        });
    }, [activeTemplates, activeCategory, searchQuery]);

    const setAsDefault = (tpl: TemplateDTO) => {
        try {
            localStorage.setItem(DEFAULT_TEMPLATE_KEY, tpl.name);
            setDefaultTemplate(tpl.name);
            broadcastTemplatesChanged();
            toast.success(`已將「${tpl.display_name}」設為預設模板，之後上傳會自動帶入`);
        } catch {
            toast.error('無法儲存預設模板設定');
        }
    };

    const clearDefault = () => {
        try {
            localStorage.removeItem(DEFAULT_TEMPLATE_KEY);
            setDefaultTemplate(null);
            broadcastTemplatesChanged();
            toast.success('已取消預設模板');
        } catch { /* ignore */ }
    };

    const handleFork = (template: TemplateDTO) => {
        // Show naming dialog instead of immediately forking
        setForkTarget(template);
        setForkName(`${template.display_name} (我的版本)`);
    };

    const executeFork = async () => {
        if (!forkTarget || !forkName.trim()) return;
        const base = forkTarget;
        const toastId = toast.loading('複製模板中...');
        try {
            const forked = await api.createTemplate({
                display_name: forkName.trim(),
                description: base.description,
                category: 'custom',
                icon: base.icon,
                color: base.color,
                tags: [...base.tags],
                fork_from: base.name,
            });
            setTemplates(prev => [...prev, forked]);
            setForkTarget(null);
            setForkName('');
            broadcastTemplatesChanged();
            // T-B1：複製後給明確回饋，並引導直接進編輯器調整。
            toast.success('已複製為您的版本', {
                id: toastId,
                description: '可以直接編輯調整內容',
                action: { label: '立即編輯', onClick: () => setEditingTemplate(forked) },
            });
        } catch (e) {
            toast.error(e instanceof Error ? e.message : '複製失敗', { id: toastId });
        }
    };

    const executeDelete = async () => {
        if (!deleteConfirm) return;
        const id = deleteConfirm.id;
        setIsDeleting(true);
        const toastId = toast.loading('刪除模板中...');
        try {
            // 已在對話框顯示使用數並取得使用者確認，直接 force 刪除。
            await api.deleteTemplate(id, true);
            setTemplates(prev => prev.filter(t => t.id !== id));
            setDeleteConfirm(null);
            broadcastTemplatesChanged();
            toast.success('模板已刪除', { id: toastId });
        } catch (e) {
            toast.error(e instanceof Error ? e.message : '刪除失敗', { id: toastId });
        } finally {
            setIsDeleting(false);
        }
    };

    const handleSaveEdit = async (id: string, data: UpdateTemplateDTO) => {
        const toastId = toast.loading('儲存中...');
        try {
            const updated = await api.updateTemplate(id, data);
            setTemplates(prev => prev.map(t => t.id === id ? updated : t));
            setEditingTemplate(null);
            broadcastTemplatesChanged();
            toast.success('模板已儲存', { id: toastId });
        } catch (e) {
            toast.error(e instanceof Error ? e.message : '儲存失敗', { id: toastId });
        }
    };

    const handleCreateNew = async (data: UpdateTemplateDTO) => {
        const toastId = toast.loading('建立中...');
        try {
            const created = await api.createTemplate({
                display_name: data.display_name || '未命名模板',
                description: data.description,
                category: data.category || 'custom',
                icon: data.icon,
                color: data.color,
                tags: data.tags,
                sections: data.sections,
            });
            setTemplates(prev => [...prev, created]);
            setIsCreatingNew(false);
            broadcastTemplatesChanged();
            toast.success('模板已建立', { id: toastId });
        } catch (e) {
            toast.error(e instanceof Error ? e.message : '建立失敗', { id: toastId });
        }
    };

    // Editor sub-view — 編輯既有 / 從零建立共用
    if (editingTemplate || isCreatingNew) {
        const blank: TemplateDTO = {
            id: '', name: '', display_name: '', description: '', category: 'custom',
            icon: 'FileText', color: 'brand-cta', sections: [], tags: [],
            is_system: false, is_active: true,
        };
        const target = editingTemplate ?? blank;
        return (
            <TemplateEditor
                template={target}
                mode={editingTemplate ? 'edit' : 'create'}
                onSave={(data) => editingTemplate ? handleSaveEdit(editingTemplate.id, data) : handleCreateNew(data)}
                onCancel={() => { setEditingTemplate(null); setIsCreatingNew(false); }}
                onDelete={editingTemplate ? () => {
                    setDeleteConfirm(editingTemplate);
                    setEditingTemplate(null);
                } : undefined}
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
                    {/* T-A4：從零建立新模板 */}
                    <button
                        onClick={() => setIsCreatingNew(true)}
                        className="ml-auto flex items-center gap-1.5 px-4 py-2 bg-brand-cta text-white rounded-lg hover:bg-brand-cta/90 text-sm font-medium transition-colors shadow-sm"
                    >
                        <Plus size={16} /> 新增模板
                    </button>
                </div>
                <p className="text-muted-foreground">不同類型的會議，AI 會用不同的框架整理摘要。選擇適合的模板，或複製後自訂調整。</p>
            </div>

            {/* Search */}
            <div className="relative mb-6">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" size={18} />
                <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="搜尋模板名稱、說明或標籤..."
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
                        const c = colorClasses(tpl.color);
                        const isDefault = defaultTemplate === tpl.name;
                        return (
                            <div key={tpl.id} className="bg-card rounded-xl border border-border p-5 hover:shadow-lg transition-all group flex w-full">
                                <div className="flex items-start gap-4 w-full">
                                    <div className={`w-11 h-11 ${c.bg} rounded-xl flex items-center justify-center ${c.text} flex-shrink-0`}>
                                        <IconComp size={22} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                                            <h3 className="font-semibold text-foreground truncate">{tpl.display_name}</h3>
                                            {tpl.is_system ? (
                                                <span className="px-2 py-0.5 text-xs bg-brand-cta/15 text-brand-cta rounded-full flex-shrink-0">系統</span>
                                            ) : (
                                                /* T-D3：自訂模板加「我的」徽章，與系統模板辨識對稱 */
                                                <span className="px-2 py-0.5 text-xs bg-status-success/15 text-status-success rounded-full flex-shrink-0">我的</span>
                                            )}
                                            {isDefault && (
                                                <span className="px-2 py-0.5 text-xs bg-brand-chimei-orange/15 text-brand-chimei-orange rounded-full flex-shrink-0">⭐ 預設</span>
                                            )}
                                        </div>
                                        <p className="text-sm text-muted-foreground mb-3 line-clamp-2">{tpl.description}</p>
                                        <div className="flex flex-wrap gap-1.5 mb-3">
                                            {tpl.tags.map(tag => (
                                                <span key={tag} className="px-2 py-0.5 text-xs bg-muted text-muted-foreground rounded">{tag}</span>
                                            ))}
                                            {/* T-F6：usage_count 正規型別取值 */}
                                            {(tpl.usage_count ?? 0) > 0 && (
                                                <span className="px-2 py-0.5 text-xs bg-brand-cta/10 text-brand-cta rounded">
                                                    已用於 {tpl.usage_count} 場會議
                                                </span>
                                            )}
                                        </div>
                                        {/* Actions — always visible for touch accessibility */}
                                        <div className="flex flex-wrap gap-2 mt-auto pt-2">
                                            <button
                                                onClick={() => setPreviewTemplate(tpl)}
                                                aria-label={`預覽模板：${tpl.display_name}`}
                                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground transition-colors"
                                            >
                                                <Eye size={14} /> 預覽
                                            </button>
                                            <button
                                                onClick={() => handleFork(tpl)}
                                                aria-label={`複製模板：${tpl.display_name}`}
                                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-brand-cta/10 rounded-lg hover:bg-brand-cta/20 text-brand-cta transition-colors"
                                            >
                                                <Copy size={14} /> 複製為我的版本
                                            </button>
                                            {/* T-B2：設為 / 取消預設 */}
                                            {isDefault ? (
                                                <button
                                                    onClick={clearDefault}
                                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground transition-colors"
                                                >
                                                    取消預設
                                                </button>
                                            ) : (
                                                <button
                                                    onClick={() => setAsDefault(tpl)}
                                                    aria-label={`設為預設模板：${tpl.display_name}`}
                                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground transition-colors"
                                                >
                                                    ⭐ 設為預設
                                                </button>
                                            )}
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
                                                        onClick={() => setDeleteConfirm(tpl)}
                                                        aria-label={`刪除模板：${tpl.display_name}`}
                                                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-status-error/10 rounded-lg hover:bg-status-error/20 text-status-error transition-colors"
                                                    >
                                                        {/* T-F2：刪除鈕加文字，避免純圖示視覺弱 */}
                                                        <Trash2 size={14} /> 刪除
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

            {/* T-C5：空狀態分流——搜尋/篩選無結果 vs 完全沒有模板 */}
            {!isLoading && !error && filteredTemplates.length === 0 && (
                <div className="text-center py-16">
                    <FileText size={48} className="mx-auto text-muted-foreground/30 mb-4" />
                    {searchQuery || activeCategory !== 'all' ? (
                        <>
                            <p className="text-muted-foreground mb-4">沒有符合「{searchQuery || CATEGORIES[activeCategory]}」的模板</p>
                            <button
                                onClick={() => { setSearchQuery(''); setActiveCategory('all'); }}
                                className="px-4 py-2 text-sm bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground transition-colors"
                            >
                                清除搜尋與篩選
                            </button>
                        </>
                    ) : (
                        <>
                            <p className="text-muted-foreground mb-4">還沒有任何模板，從零建立一個開始吧</p>
                            <button
                                onClick={() => setIsCreatingNew(true)}
                                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm bg-brand-cta text-white rounded-lg hover:bg-brand-cta/90 transition-colors"
                            >
                                <Plus size={16} /> 新增模板
                            </button>
                        </>
                    )}
                </div>
            )}

            {/* Preview Modal */}
            {previewTemplate && (
                <PreviewModal template={previewTemplate} onClose={() => setPreviewTemplate(null)} />
            )}

            {/* Delete Confirm Dialog — T-B4/T-E2：單一對話框，直接帶入使用數 */}
            {deleteConfirm && (
                <DeleteConfirmModal
                    template={deleteConfirm}
                    isDeleting={isDeleting}
                    onCancel={() => setDeleteConfirm(null)}
                    onConfirm={executeDelete}
                />
            )}

            {/* Fork Naming Dialog */}
            {forkTarget && (
                <ForkModal
                    target={forkTarget}
                    name={forkName}
                    onNameChange={setForkName}
                    onCancel={() => setForkTarget(null)}
                    onConfirm={executeFork}
                />
            )}
        </div>
    );
};


// --- Preview Modal (T-F1 Esc, T-F5 展開, 友善輸出型別) ---

const PreviewModal = ({ template, onClose }: { template: TemplateDTO; onClose: () => void }) => {
    useEscape(onClose, true);
    const [expanded, setExpanded] = useState<Record<number, boolean>>({});
    const c = colorClasses(template.color);
    const IconComp = ICON_MAP[template.icon] || FileText;
    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
            <div className="bg-card rounded-2xl border border-border max-w-lg w-full max-h-[80vh] overflow-auto p-6" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}>
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3 min-w-0">
                        <div className={`w-9 h-9 ${c.bg} rounded-lg flex items-center justify-center ${c.text} flex-shrink-0`}>
                            <IconComp size={18} />
                        </div>
                        <h2 className="text-lg font-bold text-foreground truncate">{template.display_name}</h2>
                    </div>
                    <button onClick={onClose} aria-label="關閉預覽" className="p-2 hover:bg-muted rounded-lg text-muted-foreground">
                        <X size={20} />
                    </button>
                </div>
                <p className="text-sm text-muted-foreground mb-4">{template.description}</p>
                <h3 className="text-sm font-semibold text-foreground mb-3">這個模板會產出這些段落</h3>
                <div className="space-y-3">
                    {template.sections.map((s, i) => {
                        const isLong = s.instruction.length > 100;
                        const isExpanded = expanded[i];
                        return (
                            <div key={i} className="bg-muted/50 rounded-lg p-3">
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="text-brand-cta font-medium">✓</span>
                                    <span className="text-sm font-medium text-foreground">{s.title}</span>
                                    <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-card text-muted-foreground border border-border">
                                        {OUTPUT_TYPE_LABELS[s.output_type] || s.output_type}
                                    </span>
                                </div>
                                <p className="text-xs text-muted-foreground pl-5">
                                    {isLong && !isExpanded ? s.instruction.slice(0, 100) + '...' : s.instruction}
                                </p>
                                {isLong && (
                                    <button
                                        onClick={() => setExpanded(prev => ({ ...prev, [i]: !prev[i] }))}
                                        className="text-xs text-brand-cta hover:underline pl-5 mt-1"
                                    >
                                        {isExpanded ? '收合' : '展開'}
                                    </button>
                                )}
                            </div>
                        );
                    })}
                    {template.sections.length === 0 && (
                        <p className="text-sm text-muted-foreground">此模板尚未設定輸出段落。</p>
                    )}
                </div>
            </div>
        </div>
    );
};


// --- Delete Confirm Modal (T-B4/T-E2/T-E1/T-F1) ---

const DeleteConfirmModal = ({ template, isDeleting, onCancel, onConfirm }: {
    template: TemplateDTO; isDeleting: boolean; onCancel: () => void; onConfirm: () => void;
}) => {
    useEscape(onCancel, true);
    const usage = template.usage_count ?? 0;
    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onCancel}>
            <div className="bg-card rounded-2xl border border-border max-w-sm w-full p-6" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}>
                <h2 className="text-lg font-bold text-foreground mb-2">刪除「{template.display_name}」？</h2>
                {usage > 0 ? (
                    <p className="text-sm text-status-warning mb-2">
                        ⚠️ 此模板已被 <span className="font-semibold">{usage}</span> 場會議使用。刪除不會影響既有會議的摘要，但無法再用它產生新摘要。
                    </p>
                ) : (
                    <p className="text-sm text-muted-foreground mb-2">此模板尚未被任何會議使用。</p>
                )}
                {/* T-E1：語意誠實——soft delete 但無自助還原 */}
                <p className="text-xs text-muted-foreground mb-4">刪除後將封存，30 天內可請 IT 協助還原。</p>
                <div className="flex justify-end gap-3">
                    <button onClick={onCancel} disabled={isDeleting} className="px-4 py-2 text-sm bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground disabled:opacity-50">取消</button>
                    <button onClick={onConfirm} disabled={isDeleting} className="flex items-center gap-1.5 px-4 py-2 text-sm bg-status-error text-white rounded-lg hover:bg-status-error/90 disabled:opacity-50">
                        {isDeleting && <Loader2 size={14} className="animate-spin" />}
                        刪除
                    </button>
                </div>
            </div>
        </div>
    );
};


// --- Fork Modal (T-F1) ---

const ForkModal = ({ target, name, onNameChange, onCancel, onConfirm }: {
    target: TemplateDTO; name: string; onNameChange: (v: string) => void; onCancel: () => void; onConfirm: () => void;
}) => {
    useEscape(onCancel, true);
    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onCancel}>
            <div className="bg-card rounded-2xl border border-border max-w-sm w-full p-6" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}>
                <h2 className="text-lg font-bold text-foreground mb-2">📋 複製模板</h2>
                <p className="text-sm text-muted-foreground mb-4">
                    以「{target.display_name}」為基礎，建立您自己的版本。
                </p>
                <label className="block text-sm font-medium text-foreground mb-1">模板名稱</label>
                <input
                    value={name}
                    onChange={e => onNameChange(e.target.value)}
                    className="w-full px-3 py-2 bg-card border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-cta text-sm mb-4"
                    placeholder="例如：我的業務會議模板"
                    autoFocus
                    onKeyDown={e => { if (e.key === 'Enter') onConfirm(); }}
                />
                <div className="flex justify-end gap-3">
                    <button onClick={onCancel} className="px-4 py-2 text-sm bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground">取消</button>
                    <button onClick={onConfirm} disabled={!name.trim()} className="px-4 py-2 text-sm bg-brand-cta text-white rounded-lg hover:bg-brand-cta/90 disabled:opacity-50">建立</button>
                </div>
            </div>
        </div>
    );
};


// --- Template Editor Sub-Component ---

interface TemplateEditorProps {
    template: TemplateDTO;
    mode: 'edit' | 'create';
    onSave: (data: UpdateTemplateDTO) => void;
    onCancel: () => void;
    onDelete?: () => void;
}

const INSTRUCTION_MAX = 500;

const TemplateEditor = ({ template, mode, onSave, onCancel, onDelete }: TemplateEditorProps) => {
    const [displayName, setDisplayName] = useState(template.display_name);
    const [description, setDescription] = useState(template.description);
    const [category, setCategory] = useState(template.category);
    const [icon, setIcon] = useState(template.icon || 'FileText');
    const [color, setColor] = useState(template.color || 'brand-cta');
    const [tags, setTags] = useState(template.tags.join(', '));
    const [sections, setSections] = useState<TemplateSectionDTO[]>(
        template.sections.length > 0
            ? template.sections
            : [{ title: '', instruction: '', output_key: '', output_type: 'list' }]
    );
    // T-C1：送出後才標紅
    const [showErrors, setShowErrors] = useState(false);
    // T-C3：離開確認
    const [confirmDiscard, setConfirmDiscard] = useState(false);

    // 追蹤是否有變更（dirty check）
    const initialSnapshot = useMemo(() => JSON.stringify({
        displayName: template.display_name, description: template.description,
        category: template.category, icon: template.icon || 'FileText',
        color: template.color || 'brand-cta', tags: template.tags.join(', '),
        sections: template.sections.length > 0 ? template.sections : [{ title: '', instruction: '', output_key: '', output_type: 'list' }],
    }), [template]);
    const isDirty = JSON.stringify({ displayName, description, category, icon, color, tags, sections }) !== initialSnapshot;

    const requestCancel = () => {
        if (isDirty) setConfirmDiscard(true);
        else onCancel();
    };
    useEscape(requestCancel, true);

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

    // T-C1：前端驗證——空名稱、無段落、段落空標題/空指令/空或重複 output_key。
    const validation = useMemo(() => {
        const errors: { name?: string; sections?: string; rows: Record<number, string> } = { rows: {} };
        if (!displayName.trim()) errors.name = '請輸入模板名稱';
        if (sections.length === 0) errors.sections = '至少需要一個輸出段落';
        const seenKeys = new Set<string>();
        sections.forEach((s, i) => {
            const rowErrs: string[] = [];
            if (!s.title.trim()) rowErrs.push('段落標題必填');
            if (!s.instruction.trim()) rowErrs.push('AI 指令必填');
            if (!s.output_key.trim()) rowErrs.push('output_key 必填');
            else {
                const k = s.output_key.trim();
                if (seenKeys.has(k)) rowErrs.push(`output_key「${k}」重複`);
                seenKeys.add(k);
            }
            if (s.instruction.length > INSTRUCTION_MAX) rowErrs.push(`指令超過 ${INSTRUCTION_MAX} 字`);
            if (rowErrs.length) errors.rows[i] = rowErrs.join('；');
        });
        const isValid = !errors.name && !errors.sections && Object.keys(errors.rows).length === 0;
        return { errors, isValid };
    }, [displayName, sections]);

    const handleSubmit = () => {
        if (!validation.isValid) {
            setShowErrors(true);
            toast.error('請修正標紅的欄位後再儲存');
            return;
        }
        onSave({
            display_name: displayName.trim(),
            description,
            category,
            icon,
            color,
            tags: tags.split(',').map(t => t.trim()).filter(Boolean),
            sections,
        });
    };

    const inputErrClass = (hasErr: boolean) =>
        hasErr ? 'border-status-error focus:ring-status-error/40' : 'border-border focus:ring-brand-cta';

    return (
        <div className="p-6 md:p-8 max-w-3xl mx-auto overflow-auto">
            <div className="flex items-center justify-between mb-8">
                <h1 className="text-2xl font-bold text-foreground">{mode === 'create' ? '新增模板' : '編輯模板'}</h1>
                <div className="flex gap-2">
                    {onDelete && (
                        <button onClick={onDelete} aria-label="刪除模板" title="刪除" className="px-3 py-2 text-sm text-status-error hover:bg-status-error/10 rounded-lg transition-colors">
                            <Trash2 size={16} />
                        </button>
                    )}
                    <button onClick={requestCancel} className="px-4 py-2 text-sm bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground">取消</button>
                    <button onClick={handleSubmit} className="px-4 py-2 text-sm bg-brand-cta text-white rounded-lg hover:bg-brand-cta/90">{mode === 'create' ? '建立' : '儲存'}</button>
                </div>
            </div>

            {/* Basic info */}
            <div className="space-y-4 mb-8">
                <div>
                    <label className="block text-sm font-medium text-foreground mb-1">模板名稱</label>
                    <input value={displayName} onChange={e => setDisplayName(e.target.value)}
                        className={`w-full px-3 py-2 bg-card border rounded-lg focus:outline-none focus:ring-2 text-sm ${inputErrClass(showErrors && !!validation.errors.name)}`} />
                    {showErrors && validation.errors.name && (
                        <p className="text-xs text-status-error mt-1">{validation.errors.name}</p>
                    )}
                </div>
                <div>
                    <label className="block text-sm font-medium text-foreground mb-1">描述</label>
                    <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2}
                        className="w-full px-3 py-2 bg-card border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-cta text-sm resize-none" />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
                {/* T-A5：icon / color 選擇 */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-foreground mb-1">圖示</label>
                        <div className="flex flex-wrap gap-2">
                            {ICON_OPTIONS.map(name => {
                                const IconComp = ICON_MAP[name];
                                const active = icon === name;
                                return (
                                    <button key={name} type="button" onClick={() => setIcon(name)}
                                        aria-label={`選擇圖示 ${name}`}
                                        className={`w-9 h-9 rounded-lg flex items-center justify-center border transition-colors ${active ? 'border-brand-cta bg-brand-cta/10 text-brand-cta' : 'border-border text-muted-foreground hover:bg-muted'}`}>
                                        <IconComp size={18} />
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-foreground mb-1">顏色</label>
                        <div className="flex flex-wrap gap-2">
                            {COLOR_OPTIONS.map(col => {
                                const cc = colorClasses(col);
                                const active = color === col;
                                return (
                                    <button key={col} type="button" onClick={() => setColor(col)}
                                        aria-label={`選擇顏色 ${col}`}
                                        className={`w-9 h-9 rounded-lg flex items-center justify-center border transition-all ${cc.bg} ${active ? 'ring-2 ring-offset-1 ring-brand-cta border-transparent' : 'border-border'}`}>
                                        <span className={`w-3 h-3 rounded-full ${cc.dot}`} />
                                    </button>
                                );
                            })}
                        </div>
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
            {showErrors && validation.errors.sections && (
                <p className="text-xs text-status-error mb-3">{validation.errors.sections}</p>
            )}

            <div className="space-y-4">
                {sections.map((s, i) => {
                    const rowErr = showErrors ? validation.errors.rows[i] : undefined;
                    const overLimit = s.instruction.length > INSTRUCTION_MAX;
                    return (
                        <div key={i} className={`bg-card border rounded-xl p-4 ${rowErr ? 'border-status-error' : 'border-border'}`}>
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
                            {/* T-F3：窄螢幕改單欄 */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                                <input value={s.title} onChange={e => updateSection(i, 'title', e.target.value)}
                                    placeholder="段落標題（例如：待辦事項）" className="px-3 py-2 bg-muted border border-border rounded-lg text-sm" />
                                <div className="flex gap-2">
                                    <input value={s.output_key} onChange={e => updateSection(i, 'output_key', e.target.value)}
                                        placeholder="output_key（英文，如 todos）" className="flex-1 min-w-0 px-3 py-2 bg-muted border border-border rounded-lg text-sm font-mono" />
                                    <select value={s.output_type} onChange={e => updateSection(i, 'output_type', e.target.value)}
                                        className="px-2 py-2 bg-muted border border-border rounded-lg text-sm">
                                        <option value="string">一段文字</option>
                                        <option value="list">條列清單</option>
                                        <option value="object">結構化欄位</option>
                                    </select>
                                </div>
                            </div>
                            <textarea value={s.instruction} onChange={e => updateSection(i, 'instruction', e.target.value)}
                                placeholder="AI 指令，例如：列出所有待辦事項與負責人" rows={2} maxLength={INSTRUCTION_MAX}
                                className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-sm resize-none" />
                            {/* T-C2：字數計數器 */}
                            <div className="flex items-center justify-between mt-1">
                                {rowErr ? <p className="text-xs text-status-error">{rowErr}</p> : <span />}
                                <span className={`text-xs ${overLimit ? 'text-status-error' : 'text-muted-foreground'}`}>
                                    {s.instruction.length} / {INSTRUCTION_MAX}
                                </span>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* T-C3：離開確認 */}
            {confirmDiscard && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setConfirmDiscard(false)}>
                    <div className="bg-card rounded-2xl border border-border max-w-sm w-full p-6" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}>
                        <h2 className="text-lg font-bold text-foreground mb-2">放棄未儲存的修改？</h2>
                        <p className="text-sm text-muted-foreground mb-4">您有尚未儲存的變更，離開後將會遺失。</p>
                        <div className="flex justify-end gap-3">
                            <button onClick={() => setConfirmDiscard(false)} className="px-4 py-2 text-sm bg-muted rounded-lg hover:bg-muted/80 text-muted-foreground">繼續編輯</button>
                            <button onClick={onCancel} className="px-4 py-2 text-sm bg-status-error text-white rounded-lg hover:bg-status-error/90">放棄修改</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
