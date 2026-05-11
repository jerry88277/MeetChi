"use client";

import React from "react";
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import type { CrossMeetingRef } from "@/types/meeting";

interface CrossMeetingRefListProps {
    refs: CrossMeetingRef[];
}

/**
 * V2 Q7 — 跨會議參照。
 * 後端用 pgvector cosine similarity 找同 owner 近期相似會議 (≥ 0.7)。
 * 點 chip 開新分頁 (target="_blank") 讓使用者保留當前會議閱讀狀態。
 */
export function CrossMeetingRefList({ refs }: CrossMeetingRefListProps) {
    if (!refs || refs.length === 0) return null;

    return (
        <section className="bg-card rounded-xl border border-border p-5">
            <h3 className="text-sm font-bold text-foreground mb-3 flex items-center gap-2">
                🔗 跨會議參照
                <span className="text-[10px] font-normal text-muted-foreground">
                    （同類議題的歷史會議）
                </span>
            </h3>
            <ul className="space-y-2">
                {refs.map((r, i) => (
                    <li key={i}>
                        <Link
                            href={r.url}
                            target="_blank"
                            rel="noopener"
                            className="group flex items-start gap-3 p-3 rounded-lg border border-border hover:border-brand-cta/40 hover:bg-brand-cta/5 transition-colors"
                        >
                            <ExternalLink
                                size={14}
                                className="text-brand-cta mt-0.5 flex-shrink-0 group-hover:scale-110 transition-transform"
                            />
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-foreground group-hover:text-brand-cta transition-colors break-words">
                                    {r.relatedMeetingTitle}
                                </p>
                                {r.topic && r.topic !== r.relatedMeetingTitle && (
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        相關主題：{r.topic}
                                    </p>
                                )}
                            </div>
                            <span
                                className="text-xs font-mono text-muted-foreground flex-shrink-0"
                                title={`Cosine similarity: ${r.similarity.toFixed(3)}`}
                            >
                                {Math.round(r.similarity * 100)}%
                            </span>
                        </Link>
                    </li>
                ))}
            </ul>
        </section>
    );
}
