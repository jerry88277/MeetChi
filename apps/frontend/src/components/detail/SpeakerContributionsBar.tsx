"use client";

import React from "react";
import type { SpeakerContribution, SpeakerMappings } from "@/types/meeting";
import { SpeakerName } from "./SpeakerName";

interface SpeakerContributionsBarProps {
    contributions: SpeakerContribution[];
    speakerMappings?: SpeakerMappings;
}

/**
 * V2 Q7 — 與會者貢獻度。橫條圖 + 主導議題 + 一句話貢獻描述。
 */
export function SpeakerContributionsBar({
    contributions,
    speakerMappings,
}: SpeakerContributionsBarProps) {
    if (!contributions || contributions.length === 0) return null;

    return (
        <section className="bg-card rounded-xl border border-border p-5">
            <h3 className="text-sm font-bold text-foreground mb-3 flex items-center gap-2">
                🎤 與會者貢獻度
            </h3>
            <div className="space-y-4">
                {contributions.map((c, i) => {
                    const mapping = speakerMappings?.[c.speaker];
                    const color = mapping?.color || "var(--brand-cta)";
                    return (
                        <div key={i}>
                            <div className="flex items-baseline justify-between gap-2 mb-1.5">
                                <SpeakerName
                                    speakerId={c.speaker}
                                    speakerMappings={speakerMappings}
                                    withDot={false}
                                    className="text-sm"
                                />
                                <span className="text-xs font-mono text-muted-foreground tabular-nums">
                                    {Math.round(c.speakTimePct)}% 發言時長
                                </span>
                            </div>
                            <div
                                className="w-full h-1.5 rounded-full bg-muted overflow-hidden mb-2"
                                aria-label={`${c.speaker} 發言占比 ${c.speakTimePct}%`}
                            >
                                <div
                                    className="h-full rounded-full transition-all"
                                    style={{
                                        width: `${Math.min(100, Math.max(0, c.speakTimePct))}%`,
                                        backgroundColor: color,
                                    }}
                                />
                            </div>
                            {c.mainTopics.length > 0 && (
                                <div className="flex flex-wrap gap-1 mb-1">
                                    {c.mainTopics.map((t, j) => (
                                        <span
                                            key={j}
                                            className="text-[10px] px-2 py-0.5 rounded bg-muted text-muted-foreground"
                                        >
                                            {t}
                                        </span>
                                    ))}
                                </div>
                            )}
                            {c.keyContribution && (
                                <p className="text-xs text-foreground/75 leading-relaxed">
                                    {c.keyContribution}
                                </p>
                            )}
                        </div>
                    );
                })}
            </div>
        </section>
    );
}
