"use client";

import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Chapter, SpeakerMappings } from "@/types/meeting";
import { QuoteCard } from "./QuoteCard";

interface ChapterSectionProps {
    chapter: Chapter;
    speakerMappings?: SpeakerMappings;
    onTimestampClick?: (time: number) => void;
    /** 第幾章（從 1 起算），顯示前綴用 */
    index: number;
}

const formatTimeRange = (start: number, end: number): string => {
    const fmt = (s: number) => {
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        const sec = Math.floor(s % 60);
        if (h > 0)
            return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
        return `${m}:${String(sec).padStart(2, "0")}`;
    };
    return `${fmt(start)}–${fmt(end)}`;
};

/**
 * ChapterSection — V2 Layer 2 章節區塊（永遠展開），含【展開時序】toggle 進 Layer 3。
 *
 * 顆粒度（Q1+Q2 結合 B+C 結構）：
 *   - title + 100-150 字 summary + 3-5 條 bullets + 0-2 條引言（Layer 2）
 *   - 點 toggle 後展開 sub_chapters（Layer 3 時序索引）
 */
export function ChapterSection({
    chapter,
    speakerMappings,
    onTimestampClick,
    index,
}: ChapterSectionProps) {
    const [expanded, setExpanded] = useState(false);
    const hasSubChapters = chapter.subChapters && chapter.subChapters.length > 0;

    return (
        <section className="bg-card rounded-xl border border-border overflow-hidden">
            {/* Layer 2 主章節內容 */}
            <div className="p-5">
                <h3 className="text-base font-bold text-foreground mb-2 flex items-start gap-2">
                    <span className="text-xs font-mono text-muted-foreground mt-1 flex-shrink-0">
                        {String(index).padStart(2, "0")}
                    </span>
                    <span>{chapter.title}</span>
                </h3>

                <p className="text-sm text-foreground/85 leading-relaxed mb-3">
                    {chapter.summary}
                </p>

                {chapter.bullets.length > 0 && (
                    <ul className="space-y-1.5 mb-3">
                        {chapter.bullets.map((b, i) => (
                            <li key={i} className="text-sm text-foreground/80 flex gap-2 leading-snug">
                                <span className="text-brand-cta flex-shrink-0">•</span>
                                <span className="flex-1 break-words">{b}</span>
                            </li>
                        ))}
                    </ul>
                )}

                {chapter.keyQuotes.length > 0 && (
                    <div className="space-y-1">
                        {chapter.keyQuotes.map((q, i) => (
                            <QuoteCard
                                key={i}
                                quote={q}
                                speakerMappings={speakerMappings}
                                onTimestampClick={onTimestampClick}
                            />
                        ))}
                    </div>
                )}
            </div>

            {/* Layer 3 toggle */}
            {hasSubChapters && (
                <>
                    <button
                        type="button"
                        onClick={() => setExpanded((v) => !v)}
                        aria-expanded={expanded}
                        className="w-full px-5 py-2.5 flex items-center justify-between text-xs text-muted-foreground hover:bg-muted border-t border-border transition-colors"
                    >
                        <span className="flex items-center gap-2">
                            <ChevronDown
                                size={14}
                                className={`transition-transform ${expanded ? "rotate-180" : ""}`}
                            />
                            {expanded ? "收合時序細節" : `展開時序細節（${chapter.subChapters.length} 段）`}
                        </span>
                        <span className="text-muted-foreground/70">Layer 3</span>
                    </button>

                    {expanded && (
                        <div className="bg-surface border-t border-border divide-y divide-border/50">
                            {chapter.subChapters.map((sc, i) => (
                                <div key={i} className="px-5 py-3">
                                    <div className="flex items-baseline gap-2 mb-1.5">
                                        <button
                                            type="button"
                                            onClick={() => onTimestampClick?.(sc.timeStart)}
                                            className="text-xs font-mono text-brand-cta hover:underline cursor-pointer"
                                            title="點擊跳音檔"
                                            aria-label={`跳到 ${formatTimeRange(sc.timeStart, sc.timeEnd)}`}
                                        >
                                            {formatTimeRange(sc.timeStart, sc.timeEnd)}
                                        </button>
                                    </div>
                                    <p className="text-sm text-foreground/85 leading-relaxed mb-2">
                                        {sc.summary}
                                    </p>
                                    {sc.bullets.length > 0 && (
                                        <ul className="space-y-1 mb-2">
                                            {sc.bullets.map((b, j) => (
                                                <li key={j} className="text-xs text-muted-foreground flex gap-1.5 leading-snug">
                                                    <span>·</span>
                                                    <span className="flex-1">{b}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                    {sc.keyQuotes.map((q, j) => (
                                        <QuoteCard
                                            key={j}
                                            quote={q}
                                            speakerMappings={speakerMappings}
                                            onTimestampClick={onTimestampClick}
                                        />
                                    ))}
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </section>
    );
}
