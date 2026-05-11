"use client";

import React from "react";
import type { NextStep } from "@/types/meeting";

interface NextStepsTableProps {
    nextSteps: NextStep[];
}

const isOverdue = (due?: string): boolean => {
    if (!due) return false;
    try {
        return new Date(due).getTime() < Date.now();
    } catch {
        return false;
    }
};

/**
 * V2 Q7 — 後續追蹤事項。
 * 區隔 action_items（會議中決定）：next_steps 是會議**之後**該追蹤。
 * Due 過期紅字。
 */
export function NextStepsTable({ nextSteps }: NextStepsTableProps) {
    if (!nextSteps || nextSteps.length === 0) return null;

    return (
        <section className="bg-card rounded-xl border border-border p-5">
            <h3 className="text-sm font-bold text-foreground mb-3 flex items-center gap-2">
                🔭 後續追蹤
                <span className="text-[10px] font-normal text-muted-foreground">
                    （會議之後的事項；與「待辦」區隔）
                </span>
            </h3>
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-xs text-muted-foreground border-b border-border">
                            <th className="text-left font-medium py-2 pr-3">任務</th>
                            <th className="text-left font-medium py-2 pr-3">負責人</th>
                            <th className="text-left font-medium py-2 pr-3">期限</th>
                            <th className="text-left font-medium py-2">後續會議</th>
                        </tr>
                    </thead>
                    <tbody>
                        {nextSteps.map((step, i) => {
                            const overdue = isOverdue(step.due);
                            return (
                                <tr key={i} className="border-b border-border/40 last:border-0">
                                    <td className="py-2 pr-3 text-foreground/85 break-words">
                                        {step.task}
                                    </td>
                                    <td className="py-2 pr-3 text-muted-foreground whitespace-nowrap">
                                        {step.assignee || "—"}
                                    </td>
                                    <td
                                        className={`py-2 pr-3 whitespace-nowrap font-mono text-xs ${
                                            overdue ? "text-status-error font-semibold" : "text-muted-foreground"
                                        }`}
                                    >
                                        {step.due || "—"}
                                        {overdue && <span className="ml-1">⚠️</span>}
                                    </td>
                                    <td className="py-2 text-muted-foreground text-xs">
                                        {step.followUpMeeting || "—"}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
