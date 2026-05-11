"use client";

import React from "react";
import type { SpeakerMappings } from "@/types/meeting";

interface SpeakerNameProps {
    /** SPEAKER_xx 原始 ID（從 backend summary_json 的 quote.speaker / contribution.speaker 來） */
    speakerId: string;
    speakerMappings?: SpeakerMappings;
    /** 是否包含顏色 dot（預設 true） */
    withDot?: boolean;
    className?: string;
}

/**
 * SpeakerName — V2 Q4 落地：永遠用 display_name 不顯示 SPEAKER_xx 原始標籤。
 *
 * 規則：
 *   - speakerMappings 有對應 → display_name + role（若有）
 *   - 無對應但格式 SPEAKER_xx → 顯示「講者 1」「講者 2」...（不顯示原始 ID）
 *   - 其他狀況 → 顯示原值（不會有此狀況除非 LLM 回傳怪格式）
 */
export function SpeakerName({
    speakerId,
    speakerMappings,
    withDot = true,
    className = "",
}: SpeakerNameProps) {
    const mapping = speakerMappings?.[speakerId];

    let displayName = mapping?.display_name;
    let role = mapping?.role;
    let color = mapping?.color || "var(--brand-cta)";

    if (!displayName) {
        // 從 SPEAKER_02 / Speaker_2 / SPEAKER_2 抽出編號
        const match = speakerId?.match(/(?:speaker|spk)[_\s-]?(\d+)/i);
        if (match) {
            const num = parseInt(match[1], 10);
            displayName = `講者 ${num + 1}`;  // 從 1 起算 (0-indexed → 1-indexed)
        } else {
            displayName = speakerId || "未知講者";
        }
    }

    return (
        <span
            className={`inline-flex items-center gap-1.5 ${className}`}
            style={{ color: mapping?.color || undefined }}
        >
            {withDot && (
                <span
                    className="w-1.5 h-1.5 rounded-full inline-block flex-shrink-0"
                    style={{ backgroundColor: color }}
                    aria-hidden="true"
                />
            )}
            <span className="font-medium">{displayName}</span>
            {role && (
                <span className="opacity-60 text-xs">({role})</span>
            )}
        </span>
    );
}
