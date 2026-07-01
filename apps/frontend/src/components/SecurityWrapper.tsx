"use client";

import React, { useEffect, useRef, useState } from 'react';

interface SecurityWrapperProps {
    children: React.ReactNode;
    /** 顯示於浮水印的識別字串（建議帶入使用者 email 以利追責） */
    userIdentifier?: string;
    /** 是否啟用機密防護。false 時直接渲染 children，不做任何攔截 */
    isConfidential?: boolean;
}

/**
 * SecurityWrapper — 機密會議的前端防護層。
 *
 * 防護內容（僅在 isConfidential=true 時啟用）：
 *  - 禁止選取文字（user-select: none）
 *  - 攔截複製 / 剪下（copy / cut）
 *  - 攔截右鍵選單（contextmenu）
 *  - 攔截列印與另存（Ctrl/⌘ + P / S）
 *  - PrintScreen 盡力防護（清空剪貼簿並提示）
 *  - 動態浮水印（使用者識別 + 日期），並偵測浮水印是否被移除
 *
 * 注意：前端防護無法 100% 阻止截圖（OS 層級截圖、外接相機無法攔截）。
 * 浮水印的目的是「可追責」嚇阻，而非絕對阻擋。後端仍應記錄存取日誌。
 */
export const SecurityWrapper = ({
    children,
    userIdentifier = "MeetChi-Confidential",
    isConfidential = false,
}: SecurityWrapperProps) => {
    const wrapperRef = useRef<HTMLDivElement>(null);
    const watermarkRef = useRef<HTMLDivElement>(null);
    const [isViolation, setIsViolation] = useState(false);
    const [toast, setToast] = useState<string | null>(null);

    // --- Interaction guards (copy / cut / contextmenu / print / screenshot) ---
    useEffect(() => {
        if (!isConfidential) return;

        const notify = (msg: string) => {
            setToast(msg);
            window.setTimeout(() => setToast(null), 2500);
        };

        const blockEvent = (e: Event, msg?: string) => {
            e.preventDefault();
            e.stopPropagation();
            if (msg) notify(msg);
        };

        const onCopy = (e: Event) => blockEvent(e, "機密會議：已停用複製功能");
        const onCut = (e: Event) => blockEvent(e, "機密會議：已停用剪下功能");
        const onContextMenu = (e: Event) => blockEvent(e, "機密會議：已停用右鍵選單");
        const onSelectStart = (e: Event) => e.preventDefault();
        const onDragStart = (e: Event) => e.preventDefault();

        const onKeyDown = (e: KeyboardEvent) => {
            const mod = e.ctrlKey || e.metaKey;
            // 列印 / 另存 / 複製 / 剪下 / 全選
            if (mod && ['p', 's', 'c', 'x', 'a'].includes(e.key.toLowerCase())) {
                e.preventDefault();
                e.stopPropagation();
                notify("機密會議：已停用此操作");
                return;
            }
            // PrintScreen：盡力清空剪貼簿並提示（無法完全阻止 OS 截圖）
            if (e.key === 'PrintScreen') {
                try {
                    navigator.clipboard?.writeText('【機密內容已遮蔽】');
                } catch { /* clipboard 權限不足時忽略 */ }
                notify("機密會議：截圖已被記錄並標記浮水印");
            }
        };

        document.addEventListener('copy', onCopy, true);
        document.addEventListener('cut', onCut, true);
        document.addEventListener('contextmenu', onContextMenu, true);
        document.addEventListener('selectstart', onSelectStart, true);
        document.addEventListener('dragstart', onDragStart, true);
        document.addEventListener('keydown', onKeyDown, true);

        return () => {
            document.removeEventListener('copy', onCopy, true);
            document.removeEventListener('cut', onCut, true);
            document.removeEventListener('contextmenu', onContextMenu, true);
            document.removeEventListener('selectstart', onSelectStart, true);
            document.removeEventListener('dragstart', onDragStart, true);
            document.removeEventListener('keydown', onKeyDown, true);
        };
    }, [isConfidential]);

    // --- Watermark tamper detection (relaxed: only flag actual watermark removal/hide) ---
    useEffect(() => {
        if (!isConfidential || !wrapperRef.current) return;

        const isWatermarkHidden = () => {
            const node = watermarkRef.current;
            if (!node || !document.body.contains(node)) return true;
            const style = window.getComputedStyle(node);
            return style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0';
        };

        // 只觀察浮水印節點本身的屬性與其父層的子節點增刪，
        // 不再 subtree 監看整棵 DOM（避免瀏覽器擴充/廣告攔截改動造成誤判）。
        const observer = new MutationObserver(() => {
            if (isWatermarkHidden()) setIsViolation(true);
        });

        if (watermarkRef.current) {
            observer.observe(watermarkRef.current, { attributes: true, attributeFilter: ['style', 'class'] });
        }
        if (watermarkRef.current.parentElement) {
            observer.observe(watermarkRef.current.parentElement, { childList: true });
        }

        return () => observer.disconnect();
    }, [isConfidential]);

    if (!isConfidential) {
        return <>{children}</>;
    }

    if (isViolation) {
        return (
            <div className="fixed inset-0 z-[9999] bg-red-900/90 text-white flex flex-col items-center justify-center p-8 text-center backdrop-blur-xl">
                <h1 className="text-4xl font-bold mb-4">🚨 系統安全警報 🚨</h1>
                <p className="text-xl">偵測到機密浮水印被移除。為保護機密資料，此頁面已停止顯示內容。</p>
                <p className="mt-4 opacity-70">此事件已記錄。請重新整理頁面以恢復檢視。</p>
                <button
                    onClick={() => window.location.reload()}
                    className="mt-8 px-6 py-3 bg-white text-red-900 rounded-lg font-bold hover:bg-gray-200 transition-colors"
                >
                    重新整理
                </button>
            </div>
        );
    }

    return (
        <div
            ref={wrapperRef}
            className="relative w-full h-full"
            style={{ userSelect: 'none', WebkitUserSelect: 'none' }}
        >
            {children}

            {/* Toast 提示 */}
            {toast && (
                <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[9991] px-4 py-2 rounded-lg bg-status-error text-white text-sm font-medium shadow-lg pointer-events-none">
                    {toast}
                </div>
            )}

            {/* 動態浮水印 */}
            <div
                ref={watermarkRef}
                className="pointer-events-none fixed inset-0 z-[9990] overflow-hidden"
                style={{ mixBlendMode: 'multiply', opacity: 0.1 }}
                aria-hidden="true"
            >
                <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <pattern id="watermark-pattern" x="0" y="0" width="300" height="200" patternUnits="userSpaceOnUse">
                            <text
                                x="50%"
                                y="50%"
                                fontSize="14"
                                fontFamily="monospace"
                                fill="currentColor"
                                textAnchor="middle"
                                dominantBaseline="middle"
                                transform="rotate(-30 150 100)"
                                className="text-slate-900 dark:text-white"
                            >
                                {userIdentifier} · {new Date().toISOString().slice(0, 10)}
                            </text>
                        </pattern>
                    </defs>
                    <rect x="0" y="0" width="100%" height="100%" fill="url(#watermark-pattern)" />
                </svg>
            </div>
        </div>
    );
};
