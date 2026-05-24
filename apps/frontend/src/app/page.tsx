"use client";

import React, { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import {
    LogIn,
    ArrowRight,
    Mic,
    Brain,
    FileText,
    Sparkles,
} from 'lucide-react';

/**
 * Landing — 企業內部入口頁（2026-05-24 重做）。
 *
 * 第一性原理：MeetChi 是企業內部會議助理，使用者非「行銷漏斗轉化目標」，
 * 而是被指定使用的內部同仁。原 landing 為 SaaS 行銷風（hero / 3 特色 /
 * 「準備好提升效率了嗎？」），對內部 user 不必要。
 *
 * MECE 5 種內部使用者需求：
 *   1. 認知（進對地方）✅ logo + 系統名
 *   2. 操作（進入應用）✅ 一個明確 CTA
 *   3. 學習（怎麼用）⚠️ 簡短 3-step quick start
 *   4. 信任（系統可用）⚠️ 系統狀態（暫略）
 *   5. 行銷說服 ❌ 不需 — 公司指定使用
 *
 * 已登入 → 直接 redirect /dashboard（內部使用者通常已 SSO 登入，不必再看 landing）。
 * 未登入 → 顯示簡化入口（logo + 系統名 + 進入按鈕 + 3-step quick start）。
 */
export default function HomePage() {
    const router = useRouter();
    const { data: session, status } = useSession();

    useEffect(() => {
        // 已登入直接送進 dashboard，省一次點擊
        if (status === 'authenticated' && session?.user) {
            router.replace('/dashboard');
        }
    }, [status, session, router]);

    return (
        <div className="min-h-screen bg-gradient-to-br from-brand-navy via-brand-cta to-brand-navy text-white">
            {/* Top nav */}
            <nav className="container mx-auto px-6 py-6 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <div className="w-10 h-10 bg-brand-cta rounded-xl flex items-center justify-center shadow-lg shadow-brand-cta/30">
                        <span className="font-bold text-xl">M</span>
                    </div>
                    <div>
                        <span className="text-xl font-bold tracking-tight">MeetChi</span>
                        <span className="ml-2 text-xs text-white/60 hidden sm:inline">企業 AI 會議助理</span>
                    </div>
                </div>
                {status === 'authenticated' ? (
                    <Link
                        href="/dashboard"
                        className="px-5 py-2.5 bg-white text-brand-cta hover:bg-white/90 rounded-lg font-semibold transition-colors flex items-center gap-2"
                    >
                        進入工作台 <ArrowRight size={16} />
                    </Link>
                ) : (
                    <Link
                        href="/login"
                        className="px-5 py-2.5 bg-white/10 hover:bg-white/20 rounded-lg font-medium transition-colors backdrop-blur-sm border border-white/10 flex items-center gap-2"
                    >
                        <LogIn size={16} /> 登入
                    </Link>
                )}
            </nav>

            {/* Hero（極簡，無行銷文案）*/}
            <section className="container mx-auto px-6 py-16 md:py-24 text-center">
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/10 text-white/80 text-sm font-medium mb-6 border border-white/20">
                    <Sparkles size={14} /> 內部部署 · 資料留在公司
                </div>
                <h1 className="text-3xl md:text-5xl font-bold leading-tight mb-4 text-white">
                    上傳會議錄音，AI 自動產出摘要
                </h1>
                <p className="text-base md:text-lg text-white/70 max-w-xl mx-auto mb-10">
                    為公司同仁設計的會議筆記助理：自動轉錄、生成摘要、提取待辦，
                    並可跨會議查詢過去討論。
                </p>
                <Link
                    href={status === 'authenticated' ? '/dashboard' : '/login'}
                    className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-brand-orange hover:bg-brand-orange/90 rounded-xl font-semibold text-lg shadow-xl shadow-brand-orange/30 transition-all"
                >
                    {status === 'authenticated' ? '進入工作台' : '使用公司帳號登入'}
                    <ArrowRight size={20} />
                </Link>
            </section>

            {/* Quick Start — 3 步驟 */}
            <section className="container mx-auto px-6 py-12">
                <h2 className="text-center text-sm font-bold uppercase tracking-[0.2em] text-white/60 mb-8">
                    使用流程
                </h2>
                <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">
                    <QuickStepCard
                        step="1"
                        icon={<Mic size={22} />}
                        title="上傳音檔"
                        desc="支援 mp3 / mp4 / wav 等常見格式，最長 4 小時"
                    />
                    <QuickStepCard
                        step="2"
                        icon={<Brain size={22} />}
                        title="AI 自動處理"
                        desc="平均 5-20 分鐘完成轉錄與摘要，背景執行不阻塞"
                    />
                    <QuickStepCard
                        step="3"
                        icon={<FileText size={22} />}
                        title="查看摘要"
                        desc="主題章節、待辦事項、原音引言、跨會議搜尋一站到位"
                    />
                </div>
            </section>

            {/* Footer */}
            <footer className="container mx-auto px-6 py-10 mt-10 border-t border-white/10">
                <div className="flex flex-col md:flex-row items-center justify-between gap-3 text-sm text-white/50">
                    <div className="flex items-center gap-2">
                        <div className="w-6 h-6 bg-brand-cta rounded flex items-center justify-center">
                            <span className="font-bold text-[10px]">M</span>
                        </div>
                        <span>MeetChi · 內部會議助理 © 2026</span>
                    </div>
                    <div>
                        問題回報請進入應用後點右上「回報問題」
                    </div>
                </div>
            </footer>
        </div>
    );
}

function QuickStepCard({
    step,
    icon,
    title,
    desc,
}: {
    step: string;
    icon: React.ReactNode;
    title: string;
    desc: string;
}) {
    return (
        <div className="bg-white/5 backdrop-blur-sm rounded-2xl p-6 border border-white/10 hover:bg-white/10 transition-colors">
            <div className="flex items-start gap-4">
                <div className="shrink-0 w-10 h-10 bg-brand-cta/30 rounded-xl flex items-center justify-center text-white">
                    {icon}
                </div>
                <div>
                    <div className="text-xs font-bold text-brand-amber mb-1">STEP {step}</div>
                    <h3 className="text-base font-bold mb-1.5">{title}</h3>
                    <p className="text-sm text-white/70 leading-relaxed">{desc}</p>
                </div>
            </div>
        </div>
    );
}
