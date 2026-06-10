"use client";

import { useState, useEffect, useCallback } from 'react';

/**
 * useFontSize — 2026-05-24 (request #2 高齡使用者字體放大)
 *
 * 全域字體縮放（85% ~ 150%），透過 :root font-size 變化讓所有 rem 單位元素
 * 同步放大/縮小。Tailwind 預設 1rem=16px，所以 root font-size 90% → 14.4px。
 *
 * 設計選擇：用 rem-scale 而非個別 element 改 px，因為：
 *   - tailwind text-sm / text-base / text-lg 等都是 rem 單位
 *   - 一處改 root，全頁面同步
 *   - 不需 audit 每個 text-* class
 *
 * localStorage key 與 useTheme 同前綴。
 */

export const MIN_FONT_PCT = 85;
export const MAX_FONT_PCT = 150;
export const DEFAULT_FONT_PCT = 110;
const STORAGE_KEY = 'meetchi-font-size-pct';

export function useFontSize() {
    const [fontSizePct, setFontSizePctState] = useState<number>(DEFAULT_FONT_PCT);

    useEffect(() => {
        const saved = localStorage.getItem(STORAGE_KEY);
        const initial = saved ? Math.min(MAX_FONT_PCT, Math.max(MIN_FONT_PCT, parseInt(saved, 10) || DEFAULT_FONT_PCT)) : DEFAULT_FONT_PCT;
        setFontSizePctState(initial);
        document.documentElement.style.fontSize = `${initial}%`;
    }, []);

    const setFontSizePct = useCallback((pct: number) => {
        const clamped = Math.min(MAX_FONT_PCT, Math.max(MIN_FONT_PCT, pct));
        setFontSizePctState(clamped);
        localStorage.setItem(STORAGE_KEY, String(clamped));
        document.documentElement.style.fontSize = `${clamped}%`;
    }, []);

    const reset = useCallback(() => setFontSizePct(DEFAULT_FONT_PCT), [setFontSizePct]);

    return { fontSizePct, setFontSizePct, reset };
}
