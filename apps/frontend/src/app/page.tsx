"use client";

import React from 'react';
import Link from 'next/link';
import {
    Mic,
    FileText,
    Users,
    Zap,
    ArrowRight,
    CheckCircle2,
    Globe
} from 'lucide-react';

/**
 * Landing page — DDG 配色重做（2026-05-10 / color-audit P1）
 * 從 slate-900 / indigo-900 hardcode 改為 brand-navy + brand-cta；
 * feature 卡片配色用 DDG 8 色（cta / green / violet）對應功能。
 */
export default function HomePage() {
    return (
        <div className="min-h-screen bg-gradient-to-br from-brand-navy via-brand-cta to-brand-navy text-white">

            {/* Navigation */}
            <nav className="container mx-auto px-6 py-6">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="w-10 h-10 bg-brand-cta rounded-xl flex items-center justify-center shadow-lg shadow-brand-cta/30">
                            <span className="font-bold text-xl">M</span>
                        </div>
                        <span className="text-2xl font-bold tracking-tight">MeetChi</span>
                    </div>
                    <Link
                        href="/dashboard"
                        className="px-5 py-2.5 bg-white/10 hover:bg-white/20 rounded-lg font-medium transition-colors backdrop-blur-sm border border-white/10"
                    >
                        進入應用
                    </Link>
                </div>
            </nav>

            {/* Hero Section */}
            <section className="container mx-auto px-6 py-20 md:py-32 text-center">
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-cta/30 text-white/90 text-sm font-medium mb-8 border border-white/20">
                    <Zap size={16} />
                    AI 驅動的會議智慧助理
                </div>

                <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold leading-tight mb-6">
                    <span className="bg-gradient-to-r from-white via-white/80 to-brand-amber bg-clip-text text-transparent">
                        讓每場會議
                    </span>
                    <br />
                    <span className="bg-gradient-to-r from-brand-amber to-brand-orange bg-clip-text text-transparent">
                        都有價值
                    </span>
                </h1>

                <p className="text-lg md:text-xl text-white/70 max-w-2xl mx-auto mb-12">
                    MeetChi 自動錄製您的會議，即時轉錄語音，並用 AI 生成摘要、
                    提取待辦事項，讓您專注於對話本身。
                </p>

                <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                    <Link
                        href="/dashboard"
                        className="w-full sm:w-auto px-8 py-4 bg-brand-orange hover:bg-brand-orange/90 rounded-xl font-semibold text-lg shadow-xl shadow-brand-orange/30 transition-all flex items-center justify-center gap-2"
                    >
                        開始使用 <ArrowRight size={20} />
                    </Link>
                    <button
                        type="button"
                        className="w-full sm:w-auto px-8 py-4 bg-white/5 hover:bg-white/10 rounded-xl font-semibold text-lg border border-white/10 transition-colors"
                    >
                        觀看演示
                    </button>
                </div>
            </section>

            {/* Features Section */}
            <section className="container mx-auto px-6 py-20">
                <div className="grid md:grid-cols-3 gap-8">

                    <div className="bg-white/5 rounded-2xl p-8 border border-white/10 hover:bg-white/10 transition-colors group">
                        <div className="w-14 h-14 bg-brand-cta/30 rounded-xl flex items-center justify-center mb-6 group-hover:bg-brand-cta/40 transition-colors">
                            <Mic size={28} className="text-white" />
                        </div>
                        <h3 className="text-xl font-bold mb-3">即時語音轉錄</h3>
                        <p className="text-white/70 leading-relaxed">
                            支援中文、英文及台語的高精度語音辨識，即時將會議對話轉為文字。
                        </p>
                    </div>

                    <div className="bg-white/5 rounded-2xl p-8 border border-white/10 hover:bg-white/10 transition-colors group">
                        <div className="w-14 h-14 bg-brand-green/30 rounded-xl flex items-center justify-center mb-6 group-hover:bg-brand-green/40 transition-colors">
                            <FileText size={28} className="text-brand-green" />
                        </div>
                        <h3 className="text-xl font-bold mb-3">AI 智慧摘要</h3>
                        <p className="text-white/70 leading-relaxed">
                            自動分析會議內容，生成簡潔摘要、重點決策和待辦事項。
                        </p>
                    </div>

                    <div className="bg-white/5 rounded-2xl p-8 border border-white/10 hover:bg-white/10 transition-colors group">
                        <div className="w-14 h-14 bg-brand-violet/30 rounded-xl flex items-center justify-center mb-6 group-hover:bg-brand-violet/40 transition-colors">
                            <Users size={28} className="text-white" />
                        </div>
                        <h3 className="text-xl font-bold mb-3">說話者識別</h3>
                        <p className="text-white/70 leading-relaxed">
                            自動區分不同說話者，清楚標記每段發言歸屬。
                        </p>
                    </div>

                </div>
            </section>

            {/* CTA Section */}
            <section className="container mx-auto px-6 py-20">
                <div className="bg-gradient-to-r from-brand-cta to-brand-violet rounded-3xl p-10 md:p-16 text-center relative overflow-hidden">
                    <div className="relative z-10">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4">
                            準備好提升會議效率了嗎？
                        </h2>
                        <p className="text-white/80 text-lg mb-8 max-w-xl mx-auto">
                            立即開始免費使用 MeetChi，讓 AI 成為您的會議助理。
                        </p>
                        <Link
                            href="/dashboard"
                            className="inline-flex items-center gap-2 px-8 py-4 bg-white text-brand-cta rounded-xl font-semibold text-lg hover:bg-white/90 transition-colors shadow-xl"
                        >
                            <Globe size={20} />
                            進入 Dashboard
                        </Link>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="container mx-auto px-6 py-10 border-t border-white/10">
                <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                    <div className="flex items-center gap-2 text-white/60">
                        <div className="w-6 h-6 bg-brand-cta rounded flex items-center justify-center">
                            <span className="font-bold text-xs">M</span>
                        </div>
                        <span>MeetChi © 2026</span>
                    </div>
                    <div className="flex items-center gap-6 text-white/60 text-sm">
                        <a href="#" className="hover:text-white transition-colors">隱私政策</a>
                        <a href="#" className="hover:text-white transition-colors">服務條款</a>
                        <a href="#" className="hover:text-white transition-colors">聯繫我們</a>
                    </div>
                </div>
            </footer>
        </div>
    );
}
