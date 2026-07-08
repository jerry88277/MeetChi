"use client";

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, Trash2, BookOpen, Loader2, RefreshCw, GripHorizontal, ChevronDown } from 'lucide-react';
import { api, GlossaryEntry } from '@/lib/api';
import { createPortal } from 'react-dom';

interface FloatingGlossaryPanelProps {
    meetingId: string;
    userUpn: string;
    /** 可選：預設開啟狀態 */
    defaultOpen?: boolean;
    /** 可選：外部控制開啟狀態 */
    isOpen?: boolean;
    /** 可選：關閉時回調 */
    onClose?: () => void;
    /** 可選：套用修正成功後回調（讓父層即時覆蓋逐字稿顯示，免重整） */
    onCorrectionApplied?: (corrections: { wrong: string; correct: string }[]) => void;
    /** 可選：初始位置 */
    defaultPosition?: { x: number; y: number };
    /** 可選：初始大小 */
    defaultSize?: { width: number; height: number };
}

interface Position {
    x: number;
    y: number;
}

interface Size {
    width: number;
    height: number;
}

interface DragState {
    isDragging: boolean;
    startX: number;
    startY: number;
    offsetX: number;
    offsetY: number;
}

interface ResizeState {
    isResizing: boolean;
    startX: number;
    startY: number;
    startWidth: number;
    startHeight: number;
}

/**
 * FloatingGlossaryPanel — 可拖拉、可縮放的浮窗版專有名詞面板
 * 
 * 特性：
 * - 可任意拖拉位置
 * - 可從右下角縮放大小（min 280px × 300px）
 * - 可最小化/最大化
 * - 不受逐字稿滾動影響（portal 渲染）
 * - localStorage 記憶位置和大小
 */
export const FloatingGlossaryPanel: React.FC<FloatingGlossaryPanelProps> = ({
    meetingId,
    userUpn,
    defaultOpen = true,
    isOpen: externalIsOpen,
    onClose,
    onCorrectionApplied,
    defaultPosition = { x: window?.innerWidth ? window.innerWidth - 320 : 400, y: 60 },
    defaultSize = { width: 300, height: 450 },
}) => {
    const [isOpen, setIsOpen] = useState(defaultOpen);
    // 如果提供了外部 isOpen prop，則使用外部狀態
    const shouldBeOpen = externalIsOpen !== undefined ? externalIsOpen : isOpen;
    const [isMinimized, setIsMinimized] = useState(false);
    const [position, setPosition] = useState<Position>(defaultPosition);
    const [size, setSize] = useState<Size>(defaultSize);
    
    const [entries, setEntries] = useState<GlossaryEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [wrongText, setWrongText] = useState('');
    const [correctText, setCorrectText] = useState('');
    const [adding, setAdding] = useState(false);
    const [applying, setApplying] = useState(false);
    const [applyResult, setApplyResult] = useState<string | null>(null);
    // 2026-07-08：新增/刪除詞後標記「待套用」，讓「套用修正」鈕高亮提示新手記得按。
    const [needsApply, setNeedsApply] = useState(false);
    const [error, setError] = useState('');

    const windowRef = useRef<HTMLDivElement>(null);
    const dragState = useRef<DragState>({
        isDragging: false,
        startX: 0,
        startY: 0,
        offsetX: 0,
        offsetY: 0,
    });
    const resizeState = useRef<ResizeState>({
        isResizing: false,
        startX: 0,
        startY: 0,
        startWidth: 0,
        startHeight: 0,
    });

    const STORAGE_KEY = `meetchi_glossary_panel_${meetingId}`;

    // 從 localStorage 恢復位置和大小
    useEffect(() => {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                const data = JSON.parse(saved);
                if (data.position) setPosition(data.position);
                if (data.size) setSize(data.size);
                if (data.isMinimized !== undefined) setIsMinimized(data.isMinimized);
            }
        } catch (e) {
            console.error('Failed to restore glossary panel state:', e);
        }
    }, [STORAGE_KEY]);

    // 保存位置和大小到 localStorage
    const saveState = useCallback((pos: Position, sz: Size, minimized: boolean) => {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify({
                position: pos,
                size: sz,
                isMinimized: minimized,
            }));
        } catch (e) {
            console.error('Failed to save glossary panel state:', e);
        }
    }, [STORAGE_KEY]);

    // 拖拉邏輯
    const handleDragStart = (e: React.MouseEvent<HTMLDivElement>) => {
        const target = e.target as HTMLElement;
        if (target.tagName === 'BUTTON' || target.closest('button')) return;
        if (target.closest('[data-no-drag]')) return;
        dragState.current = {
            isDragging: true,
            startX: e.clientX,
            startY: e.clientY,
            offsetX: e.clientX - position.x,
            offsetY: e.clientY - position.y,
        };
    };

    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!dragState.current.isDragging) return;
            const newX = e.clientX - dragState.current.offsetX;
            const newY = e.clientY - dragState.current.offsetY;
            setPosition({ x: Math.max(0, newX), y: Math.max(0, newY) });
        };

        const handleMouseUp = () => {
            if (!dragState.current.isDragging) return;
            dragState.current.isDragging = false;
            saveState(position, size, isMinimized);
        };

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
    }, [saveState, position, size, isMinimized]);

    // 縮放邏輯（右下角）
    const handleResizeStart = (e: React.MouseEvent<HTMLDivElement>) => {
        e.preventDefault();
        resizeState.current = {
            isResizing: true,
            startX: e.clientX,
            startY: e.clientY,
            startWidth: size.width,
            startHeight: size.height,
        };
    };

    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!resizeState.current.isResizing) return;
            const deltaX = e.clientX - resizeState.current.startX;
            const deltaY = e.clientY - resizeState.current.startY;
            const newWidth = Math.max(280, resizeState.current.startWidth + deltaX);
            const newHeight = Math.max(300, resizeState.current.startHeight + deltaY);
            setSize({ width: newWidth, height: newHeight });
        };

        const handleMouseUp = () => {
            if (!resizeState.current.isResizing) return;
            resizeState.current.isResizing = false;
            saveState(position, size, isMinimized);
        };

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
    }, [saveState, position, size, isMinimized]);

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
            setNeedsApply(true);
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
            setNeedsApply(true);
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
            setNeedsApply(false);
            // 即時覆蓋父層逐字稿顯示，免使用者手動重整。
            // 後端已將修正持久化至 DB；此處以相同的字串替換套用於當前畫面，
            // 兩者結果一致（idempotent），重整後仍正確。
            if (onCorrectionApplied && entries.length > 0) {
                onCorrectionApplied(
                    entries.map(e => ({ wrong: e.wrong_text, correct: e.correct_text }))
                );
            }
            setTimeout(() => setApplyResult(null), 5000);
        } catch (e) {
            console.error('Apply failed:', e);
            setApplyResult('修正失敗');
        } finally {
            setApplying(false);
        }
    };

    if (!shouldBeOpen) return null;

    const content = (
        <div
            ref={windowRef}
            className="fixed bg-card border border-border rounded-xl shadow-2xl flex flex-col"
            style={{
                left: `${position.x}px`,
                top: `${position.y}px`,
                width: isMinimized ? '300px' : `${size.width}px`,
                height: isMinimized ? 'auto' : `${size.height}px`,
                zIndex: 50,
            }}
        >
            {/* Header — 可拖拉 */}
            <div
                onMouseDown={handleDragStart}
                className="flex items-center gap-2 p-3 bg-muted/50 border-b border-border rounded-t-xl cursor-move hover:bg-muted/70 transition-colors select-none group"
            >
                <GripHorizontal size={14} className="text-muted-foreground group-hover:text-foreground" />
                <BookOpen size={14} className="text-primary" />
                <h4 className="font-semibold text-sm text-foreground flex-1">專有名詞</h4>
                <span className="text-xs text-muted-foreground">{entries.length}</span>
                <button
                    onClick={() => {
                        setIsMinimized(!isMinimized);
                        saveState(position, size, !isMinimized);
                    }}
                    className="p-1 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    title={isMinimized ? '展開' : '最小化'}
                >
                    <ChevronDown size={14} className={`transition-transform ${isMinimized ? 'rotate-180' : ''}`} />
                </button>
                <button
                    onClick={() => {
                        if (externalIsOpen !== undefined && onClose) {
                            onClose();
                        } else {
                            setIsOpen(false);
                        }
                    }}
                    className="p-1 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    title="關閉"
                >
                    ×
                </button>
            </div>

            {/* Content — 可捲動 */}
            {!isMinimized && (
                <div className="flex-1 flex flex-col overflow-hidden">
                    <div className="flex-1 p-3 overflow-y-auto space-y-3 text-xs">
                        {/* Instruction */}
                        <p className="text-muted-foreground">
                            新增本會議特有的名詞修正。
                        </p>

                        {/* Add row */}
                        <div className="space-y-1.5" data-no-drag>
                            <div className="flex gap-1.5">
                                <input
                                    type="text"
                                    value={wrongText}
                                    onChange={(e) => setWrongText(e.target.value)}
                                    placeholder="錯誤轉錄"
                                    className="flex-1 px-2 py-1 text-xs border border-border rounded bg-background text-foreground"
                                    onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                                />
                                <span className="self-center text-muted-foreground">→</span>
                                <input
                                    type="text"
                                    value={correctText}
                                    onChange={(e) => setCorrectText(e.target.value)}
                                    placeholder="正確名稱"
                                    className="flex-1 px-2 py-1 text-xs border border-border rounded bg-background text-foreground"
                                    onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                                />
                                <button
                                    onClick={handleAdd}
                                    disabled={adding || !wrongText.trim() || !correctText.trim()}
                                    className="px-2 py-1 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
                                >
                                    {adding ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
                                </button>
                            </div>
                            {error && <p className="text-xs text-destructive">{error}</p>}
                        </div>

                        {/* Entry list */}
                        {loading ? (
                            <div className="flex justify-center py-2">
                                <Loader2 className="animate-spin text-muted-foreground" size={12} />
                            </div>
                        ) : entries.length > 0 && (
                            <div className="space-y-0.5">
                                {entries.map(entry => (
                                    <div key={entry.id} className="flex items-center gap-1.5 px-2 py-0.5 rounded hover:bg-muted/50 group text-xs">
                                        <span className="text-foreground truncate">{entry.wrong_text}</span>
                                        <span className="text-muted-foreground">→</span>
                                        <span className="font-medium text-foreground truncate">{entry.correct_text}</span>
                                        <button
                                            onClick={() => handleDelete(entry.id)}
                                            className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:text-destructive flex-shrink-0"
                                        >
                                            <Trash2 size={11} />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Footer buttons */}
                    <div className="p-3 border-t border-border space-y-2" data-no-drag>
                        {needsApply && (
                            <p className="text-[11px] text-brand-cta font-medium text-center">
                                新增後記得按「套用修正」——逐字稿與摘要會一起更新
                            </p>
                        )}
                        <button
                            onClick={handleApply}
                            disabled={applying}
                            className={`w-full flex items-center justify-center gap-1 px-3 py-1.5 text-xs rounded transition-colors disabled:opacity-50 ${
                                needsApply
                                    ? 'bg-brand-cta text-white hover:bg-brand-cta/90 font-semibold shadow-sm animate-pulse'
                                    : 'bg-muted hover:bg-muted/80 text-foreground'
                            }`}
                        >
                            {applying ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                            套用修正
                        </button>
                        {applyResult && (
                            <p className="text-xs text-center text-status-success">{applyResult}</p>
                        )}
                    </div>
                </div>
            )}

            {/* Resize handle — 右下角 */}
            {!isMinimized && (
                <div
                    onMouseDown={handleResizeStart}
                    className="absolute bottom-0 right-0 w-5 h-5 cursor-se-resize hover:bg-primary/20 rounded-tl transition-colors"
                    title="拖拉以縮放"
                />
            )}
        </div>
    );

    // 使用 portal 渲染到 document.body，避免受容器滾動影響
    return typeof window !== 'undefined' ? createPortal(content, document.body) : null;
};
