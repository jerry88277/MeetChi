"use client";

import React from "react";
import { Play } from "lucide-react";
import type { KeyQuote, SpeakerMappings } from "@/types/meeting";
import { SpeakerName } from "./SpeakerName";

interface QuoteCardProps {
    quote: KeyQuote;
    speakerMappings?: SpeakerMappings;
    onTimestampClick?: (time: number) => void;
}

const formatTime = (seconds: number): string => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    return `${m}:${String(s).padStart(2, "0")}`;
};

/**
 * QuoteCard — V2 Q4：引言一律 transform SPEAKER_xx → display_name，
 *   時戳可點跳音檔。三層摘要中重複使用，視覺保持輕量。
 */
export function QuoteCard({ quote, speakerMappings, onTimestampClick }: QuoteCardProps) {
    return (
        <blockquote className="my-2 pl-3 border-l-2 border-brand-cta/40 bg-brand-cta/5 rounded-r py-1.5 pr-2">
            <p className="text-foreground/90 italic text-sm leading-relaxed">
                「{quote.text}」
            </p>
            <footer className="mt-1 text-xs flex items-center gap-2 text-muted-foreground">
                <SpeakerName speakerId={quote.speaker} speakerMappings={speakerMappings} />
                {typeof quote.time === "number" && (
                    <button
                        type="button"
                        onClick={() => onTimestampClick?.(quote.time!)}
                        className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-brand-cta hover:bg-brand-cta/10 transition-colors font-mono"
                        title="點擊跳音檔"
                        aria-label={`跳到 ${formatTime(quote.time)}`}
                    >
                        <Play size={10} />
                        {formatTime(quote.time)}
                    </button>
                )}
            </footer>
        </blockquote>
    );
}
