"use client";

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

interface SecurityWrapperProps {
    children: React.ReactNode;
    userIdentifier?: string;
    isConfidential?: boolean;
}

export const SecurityWrapper = ({ children, userIdentifier = "MeetChi-Confidential", isConfidential = false }: SecurityWrapperProps) => {
    const wrapperRef = useRef<HTMLDivElement>(null);
    const watermarkRef = useRef<HTMLDivElement>(null);
    const router = useRouter();
    const [isViolation, setIsViolation] = useState(false);

    useEffect(() => {
        // Only restrict print for confidential meetings
        const handleKeyDown = (e: KeyboardEvent) => {
            if (isConfidential && (e.ctrlKey || e.metaKey) && (e.key === 'p')) {
                e.preventDefault();
            }
        };

        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [isConfidential]);

    // MutationObserver to prevent tampering with watermark
    useEffect(() => {
        if (!wrapperRef.current || !watermarkRef.current) return;

        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.removedNodes.length > 0) {
                    for (let i = 0; i < mutation.removedNodes.length; i++) {
                        if (mutation.removedNodes[i] === watermarkRef.current || 
                            !document.body.contains(watermarkRef.current!)) {
                            setIsViolation(true);
                            break;
                        }
                    }
                }
                if (mutation.target === watermarkRef.current) {
                    const style = window.getComputedStyle(watermarkRef.current);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                        setIsViolation(true);
                    }
                }
            });
        });

        observer.observe(wrapperRef.current, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['style', 'class']
        });

        return () => observer.disconnect();
    }, []);

    if (isViolation) {
        return (
            <div className="fixed inset-0 z-[9999] bg-red-900/90 text-white flex flex-col items-center justify-center p-8 text-center backdrop-blur-xl">
                <h1 className="text-4xl font-bold mb-4">🚨 系統安全警報 🚨</h1>
                <p className="text-xl">偵測到異常的畫面竄改行為。為保護機密資料，此工作階段已被強制中止。</p>
                <p className="mt-4 opacity-70">此事件已紀錄並將通知系統管理員。</p>
                <button
                    onClick={() => window.location.href = '/'}
                    className="mt-8 px-6 py-3 bg-white text-red-900 rounded-lg font-bold hover:bg-gray-200 transition-colors"
                >
                    返回安全首頁
                </button>
            </div>
        );
    }

    return (
        <div ref={wrapperRef} className="relative w-full h-full">
            {children}
            
            {/* Dynamic Watermark Overlay */}
            <div 
                ref={watermarkRef}
                className="pointer-events-none fixed inset-0 z-[9990] overflow-hidden"
                style={{
                    mixBlendMode: 'multiply',
                    opacity: 0.04
                }}
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
                                {userIdentifier} - {new Date().toISOString().slice(0, 10)}
                            </text>
                        </pattern>
                    </defs>
                    <rect x="0" y="0" width="100%" height="100%" fill="url(#watermark-pattern)" />
                </svg>
            </div>
        </div>
    );
};
