import React from 'react';
import { AlertTriangle, MicOff, Volume1, Volume2, CheckCircle2, AudioWaveform } from 'lucide-react';
import type { AudioStats } from '@/types/meeting';

/**
 * 上傳音檔「原始狀態」健康報告卡片（2026-07-03）。
 *
 * 讓使用者知道自己上傳音檔的原始狀態：時長、聲道、取樣率、音量（peak/mean dBFS），
 * 並針對常見問題明確提示：
 *   - silent      未偵測到可辨識語音（麥克風未開/權限被擋/錄到無聲音源）
 *   - low_volume  音量偏低（辨識可能受影響）
 *   - clipping    音量過大/削波失真
 *   - ok          音檔正常
 *
 * 動機：靜音/無訊號音檔會轉錄出 0 段落但 status=COMPLETED，過去使用者誤以為系統壞掉。
 */

function fmtDbfs(v?: number | null): string {
    if (v === null || v === undefined) return '—';
    return `${v.toFixed(1)} dBFS`;
}

function fmtDuration(sec?: number | null): string {
    if (!sec && sec !== 0) return '—';
    const s = Math.round(sec);
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m > 0 ? `${m} 分 ${r} 秒` : `${r} 秒`;
}

function fmtChannels(ch?: number | null): string {
    if (ch === null || ch === undefined) return '—';
    if (ch === 1) return '單聲道 (mono)';
    if (ch === 2) return '立體聲 (stereo)';
    return `${ch} 聲道`;
}

const THEME: Record<string, { border: string; bg: string; text: string; Icon: React.ElementType }> = {
    silent: { border: 'border-status-error/40', bg: 'bg-status-error/5', text: 'text-status-error', Icon: MicOff },
    low_volume: { border: 'border-status-warning/40', bg: 'bg-status-warning/5', text: 'text-status-warning', Icon: Volume1 },
    clipping: { border: 'border-status-warning/40', bg: 'bg-status-warning/5', text: 'text-status-warning', Icon: Volume2 },
    ok: { border: 'border-border', bg: 'bg-card', text: 'text-status-success', Icon: CheckCircle2 },
    unknown: { border: 'border-border', bg: 'bg-card', text: 'text-muted-foreground', Icon: AudioWaveform },
};

export function AudioHealthReport({ stats }: { stats?: AudioStats | null }) {
    if (!stats) return null;

    const health = stats.health ?? 'unknown';
    const theme = THEME[health] ?? THEME.unknown;
    const { Icon } = theme;
    const isProblem = health === 'silent' || health === 'low_volume' || health === 'clipping';

    return (
        <section className={`rounded-xl border ${theme.border} ${theme.bg} p-4 shadow-sm`}>
            <div className="flex items-start gap-3">
                <div className={`shrink-0 mt-0.5 ${theme.text}`}>
                    <Icon size={20} />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="text-sm font-semibold text-foreground">上傳音檔狀態</h4>
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-md border ${theme.border} ${theme.text}`}>
                            {health === 'ok' ? '正常'
                                : health === 'silent' ? '⚠ 無有效聲音'
                                : health === 'low_volume' ? '⚠ 音量偏低'
                                : health === 'clipping' ? '⚠ 疑似削波'
                                : '無法判定'}
                        </span>
                    </div>

                    {stats.health_label_zh && (
                        <p className={`text-sm mt-1 leading-relaxed ${isProblem ? theme.text : 'text-muted-foreground'}`}>
                            {isProblem && <AlertTriangle size={13} className="inline-block mr-1 -mt-0.5" />}
                            {stats.health_label_zh}
                        </p>
                    )}

                    {/* 音檔規格：時長 / 聲道 / 取樣率 / 音量 */}
                    <dl className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2 text-xs">
                        <div>
                            <dt className="text-muted-foreground">時長</dt>
                            <dd className="text-foreground font-medium mt-0.5">{fmtDuration(stats.duration_sec)}</dd>
                        </div>
                        <div>
                            <dt className="text-muted-foreground">聲道</dt>
                            <dd className="text-foreground font-medium mt-0.5">{fmtChannels(stats.channels)}</dd>
                        </div>
                        <div>
                            <dt className="text-muted-foreground">取樣率</dt>
                            <dd className="text-foreground font-medium mt-0.5">
                                {stats.sample_rate ? `${(stats.sample_rate / 1000).toFixed(stats.sample_rate % 1000 === 0 ? 0 : 1)} kHz` : '—'}
                            </dd>
                        </div>
                        <div>
                            <dt className="text-muted-foreground" title="峰值音量 / 平均音量（dBFS，0 為滿刻度，越負越小聲）">
                                音量（峰值/平均）
                            </dt>
                            <dd className="text-foreground font-medium mt-0.5 font-mono">
                                {fmtDbfs(stats.peak_dbfs)} / {fmtDbfs(stats.mean_dbfs)}
                            </dd>
                        </div>
                    </dl>
                </div>
            </div>
        </section>
    );
}
