"use client";

import React from 'react';
import { LayoutList } from 'lucide-react';
import type { TemplateSectionMeta } from '@/types/meeting';

interface TemplateSectionsProps {
    /** 模板專屬區塊資料：key=output_key，value 為原始值 */
    extraSections: Record<string, unknown>;
    /** 由會議模板定義提供的 output_key → {title, outputType} 對照 */
    sectionMeta: Record<string, TemplateSectionMeta>;
}

/** 常見系統模板 output_key → 中文標題（模板查不到時的 fallback，避免顯示英文 key） */
const KNOWN_KEY_LABELS: Record<string, string> = {
    key_learnings: '學習要點',
    qa_summary: 'Q&A 摘要',
    further_reading: '延伸學習',
    ideas: '點子清單',
    top_picks: '優先候選',
    BANT: 'BANT 分析',
    candidate_summary: '候選人摘要',
    STAR_stories: 'STAR 故事',
    key_strengths: '核心優勢',
    technical_decisions: '技術決策',
    challenges: '挑戰',
    milestones: '里程碑進度',
    blockers: '阻塞點',
    went_well: '做得好的地方',
    to_improve: '待改善的地方',
    requirements: '需求清單',
    constraints: '限制條件',
    yesterday: '昨日完成',
    today: '今日計畫',
};

/** 把 output_key 轉成可讀標題（模板查不到時的 fallback） */
function humanizeKey(key: string): string {
    if (KNOWN_KEY_LABELS[key]) return KNOWN_KEY_LABELS[key];
    return key
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());
}

/** 判斷 value 是否為「物件陣列」（每筆用卡片呈現） */
function isObjectArray(v: unknown): v is Record<string, unknown>[] {
    return Array.isArray(v) && v.length > 0 && v.every(
        item => item !== null && typeof item === 'object' && !Array.isArray(item)
    );
}

/** 把單一 scalar 值轉為顯示字串 */
function renderScalar(v: unknown): string {
    if (v === null || v === undefined) return '';
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v);
    return JSON.stringify(v);
}

const FieldLabelValue: React.FC<{ label: string; value: unknown }> = ({ label, value }) => {
    if (value === null || value === undefined || value === '') return null;
    let display: React.ReactNode;
    if (Array.isArray(value)) {
        display = (
            <ul className="list-disc list-inside space-y-0.5">
                {value.map((it, i) => <li key={i}>{renderScalar(it)}</li>)}
            </ul>
        );
    } else if (typeof value === 'object') {
        display = <span className="text-foreground/80">{JSON.stringify(value)}</span>;
    } else {
        display = <span className="text-foreground/80">{renderScalar(value)}</span>;
    }
    return (
        <div className="text-sm">
            <span className="font-medium text-foreground">{humanizeKey(label)}：</span>
            {display}
        </div>
    );
};

/** 渲染單一區塊的 value（依型別分流） */
const SectionValue: React.FC<{ value: unknown }> = ({ value }) => {
    // string → 段落
    if (typeof value === 'string') {
        return <p className="text-sm text-foreground/80 leading-relaxed whitespace-pre-wrap">{value}</p>;
    }
    // 物件陣列 → 卡片
    if (isObjectArray(value)) {
        return (
            <div className="space-y-2">
                {value.map((obj, i) => (
                    <div key={i} className="rounded-lg border border-border bg-muted/30 p-3 space-y-1">
                        {Object.entries(obj).map(([k, v]) => (
                            <FieldLabelValue key={k} label={k} value={v} />
                        ))}
                    </div>
                ))}
            </div>
        );
    }
    // 字串陣列 → 條列
    if (Array.isArray(value)) {
        return (
            <ul className="space-y-1.5">
                {value.map((it, i) => (
                    <li key={i} className="flex gap-2 text-sm text-foreground/80">
                        <span className="text-brand-cta mt-0.5 flex-shrink-0">•</span>
                        <span>{renderScalar(it)}</span>
                    </li>
                ))}
            </ul>
        );
    }
    // 純物件 → 鍵值
    if (value !== null && typeof value === 'object') {
        return (
            <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-1">
                {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
                    <FieldLabelValue key={k} label={k} value={v} />
                ))}
            </div>
        );
    }
    return <p className="text-sm text-foreground/80">{renderScalar(value)}</p>;
};

/**
 * TemplateSections — 動態渲染「模板專屬」區塊（策略 a：V2 核心之後的加值層）。
 *
 * 依會議實際套用的模板定義（sectionMeta）決定每個 output_key 的標題與型別，
 * 查不到定義時以 humanizeKey fallback。這讓不同模板（教育訓練/腦力激盪/業務...）
 * 產生的專屬欄位真正顯示出來，不再與「一般會議」長得一樣。
 */
export const TemplateSections: React.FC<TemplateSectionsProps> = ({ extraSections, sectionMeta }) => {
    const keys = Object.keys(extraSections);
    if (keys.length === 0) return null;

    // 依模板 sections 的原始順序排序；模板未定義的 key 排在後面
    const orderMap = new Map<string, number>();
    Object.values(sectionMeta).forEach((m, i) => orderMap.set(m.outputKey, i));
    const sortedKeys = [...keys].sort((a, b) => {
        const oa = orderMap.has(a) ? orderMap.get(a)! : Number.MAX_SAFE_INTEGER;
        const ob = orderMap.has(b) ? orderMap.get(b)! : Number.MAX_SAFE_INTEGER;
        return oa - ob;
    });

    return (
        <section>
            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
                <LayoutList size={14} /> 模板專屬整理
            </h3>
            <div className="space-y-4">
                {sortedKeys.map(key => {
                    const meta = sectionMeta[key];
                    const title = meta?.title || humanizeKey(key);
                    return (
                        <div key={key} className="rounded-xl border border-border bg-card p-4">
                            <h4 className="text-sm font-semibold text-foreground mb-2">{title}</h4>
                            <SectionValue value={extraSections[key]} />
                        </div>
                    );
                })}
            </div>
        </section>
    );
};
