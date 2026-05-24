"use client";

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * useDragSelect — 2026-05-24 (request #1) 拖曳框選 hook
 *
 * 在指定 container 內按住滑鼠拖曳會出現選取框（rubber-band），放開時
 * 偵測與框重疊的子節點（用 `data-select-id` 屬性標記），把它們的 id
 * 加入 selection set。
 *
 * 設計（第一性原理）：
 *   - 不耦合 React state 子元件 → 用 DOM bbox 計算交集，效能 O(n) 線性
 *   - mousedown 必須在「空白處」才啟動拖曳，點到 card 內走 click 邏輯
 *   - touch device 不啟用（行動裝置慣用 long-press 多選，本 PR 不做）
 *
 * 整合方式：
 *   1. 用 hook 拿 selectedIds + clearSelection + setSelectedIds
 *   2. 把 containerRef 綁到 grid 外層 div
 *   3. 每個 card 加 `data-select-id={meeting.id}` 與 selected 視覺
 *   4. 子元件 onClick 自行決定是否 toggle 選取（如 shift+click）
 */
export function useDragSelect<T extends HTMLElement>() {
    const containerRef = useRef<T | null>(null);
    const [selectedIds, setSelectedIdsState] = useState<Set<string>>(new Set());
    const [dragRect, setDragRect] = useState<{
        left: number;
        top: number;
        width: number;
        height: number;
    } | null>(null);

    // Drag start anchor (in container-relative coords)
    const anchorRef = useRef<{ x: number; y: number } | null>(null);

    const clearSelection = useCallback(() => setSelectedIdsState(new Set()), []);
    const setSelectedIds = useCallback((next: Set<string>) => setSelectedIdsState(next), []);
    const toggleId = useCallback((id: string) => {
        setSelectedIdsState(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }, []);

    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const onMouseDown = (e: MouseEvent) => {
            // 只接 left button 主鍵
            if (e.button !== 0) return;
            // 點到 card 本體不啟動拖曳（讓 card 自己的 onClick 處理）
            const target = e.target as HTMLElement;
            if (target.closest('[data-select-id]')) return;
            // 點到 button / input / a / 其他互動元素也不啟動
            if (target.closest('button, a, input, [role="dialog"]')) return;

            const rect = container.getBoundingClientRect();
            anchorRef.current = {
                x: e.clientX - rect.left + container.scrollLeft,
                y: e.clientY - rect.top + container.scrollTop,
            };
            setDragRect({ left: anchorRef.current.x, top: anchorRef.current.y, width: 0, height: 0 });
        };

        const onMouseMove = (e: MouseEvent) => {
            if (!anchorRef.current || !container) return;
            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left + container.scrollLeft;
            const y = e.clientY - rect.top + container.scrollTop;
            const left = Math.min(anchorRef.current.x, x);
            const top = Math.min(anchorRef.current.y, y);
            const width = Math.abs(x - anchorRef.current.x);
            const height = Math.abs(y - anchorRef.current.y);
            setDragRect({ left, top, width, height });
        };

        const onMouseUp = (e: MouseEvent) => {
            if (!anchorRef.current || !container) {
                anchorRef.current = null;
                setDragRect(null);
                return;
            }
            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left + container.scrollLeft;
            const y = e.clientY - rect.top + container.scrollTop;
            const left = Math.min(anchorRef.current.x, x);
            const top = Math.min(anchorRef.current.y, y);
            const right = Math.max(anchorRef.current.x, x);
            const bottom = Math.max(anchorRef.current.y, y);

            // 拖曳距離 < 5px 視為單擊（不選取）
            const dist = Math.hypot(right - left, bottom - top);
            if (dist >= 5) {
                const cards = container.querySelectorAll<HTMLElement>('[data-select-id]');
                const additive = e.shiftKey || e.ctrlKey || e.metaKey;
                const next = new Set<string>(additive ? selectedIds : []);
                cards.forEach(card => {
                    const id = card.dataset.selectId;
                    if (!id) return;
                    const cardRect = card.getBoundingClientRect();
                    const cardLeft = cardRect.left - rect.left + container.scrollLeft;
                    const cardTop = cardRect.top - rect.top + container.scrollTop;
                    const cardRight = cardLeft + cardRect.width;
                    const cardBottom = cardTop + cardRect.height;
                    // 矩形相交
                    const intersects =
                        cardLeft < right && cardRight > left &&
                        cardTop < bottom && cardBottom > top;
                    if (intersects) next.add(id);
                });
                setSelectedIdsState(next);
            }

            anchorRef.current = null;
            setDragRect(null);
        };

        // Esc 清空選取
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                setSelectedIdsState(new Set());
                anchorRef.current = null;
                setDragRect(null);
            }
        };

        container.addEventListener('mousedown', onMouseDown);
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
        window.addEventListener('keydown', onKey);
        return () => {
            container.removeEventListener('mousedown', onMouseDown);
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
            window.removeEventListener('keydown', onKey);
        };
    }, [selectedIds]);

    return {
        containerRef,
        selectedIds,
        toggleId,
        setSelectedIds,
        clearSelection,
        dragRect,
        isDragging: dragRect !== null && dragRect.width + dragRect.height > 5,
    };
}
