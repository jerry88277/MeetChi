"use client";

import React, { useState, useEffect, useCallback } from 'react';
import {
    Activity, Users, Clock, AlertTriangle, CheckCircle2,
    Search, Filter, ChevronDown, Loader2, Shield, Database,
    DollarSign, BarChart3
} from 'lucide-react';
import { api } from '@/lib/api';
import type { OpsOverview, OpsMeetingItem, OpsUserStats } from '@/lib/api';

interface OpsAdminPanelProps {
    userRole: string; // 'admin' | 'super_admin'
}

export function OpsAdminPanel({ userRole }: OpsAdminPanelProps) {
    const [activeTab, setActiveTab] = useState<'overview' | 'meetings' | 'users'>('overview');
    const [overview, setOverview] = useState<OpsOverview | null>(null);
    const [meetings, setMeetings] = useState<OpsMeetingItem[]>([]);
    const [users, setUsers] = useState<OpsUserStats[]>([]);
    const [loading, setLoading] = useState(true);

    // Filters
    const [statusFilter, setStatusFilter] = useState('');
    const [userFilter, setUserFilter] = useState('');
    const [keyword, setKeyword] = useState('');
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');

    const loadOverview = useCallback(async () => {
        try {
            const data = await api.getOpsOverview();
            setOverview(data);
        } catch (e) { console.error('Failed to load overview', e); }
    }, []);

    const loadMeetings = useCallback(async () => {
        setLoading(true);
        try {
            const data = await api.listOpsMeetings({
                status_filter: statusFilter || undefined,
                user_upn: userFilter || undefined,
                keyword: keyword || undefined,
                date_from: dateFrom || undefined,
                date_to: dateTo || undefined,
            });
            setMeetings(data);
        } catch (e) { console.error('Failed to load meetings', e); }
        setLoading(false);
    }, [statusFilter, userFilter, keyword, dateFrom, dateTo]);

    const loadUsers = useCallback(async () => {
        try {
            const data = await api.listOpsUsers();
            setUsers(data);
        } catch (e) { console.error('Failed to load users', e); }
    }, []);

    useEffect(() => {
        loadOverview();
        loadMeetings();
        loadUsers();
    }, [loadOverview, loadMeetings, loadUsers]);

    const formatDuration = (seconds: number | null) => {
        if (!seconds) return '—';
        if (seconds < 60) return `${Math.round(seconds)}s`;
        if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
        return `${(seconds / 3600).toFixed(1)}h`;
    };

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return '—';
        return new Date(dateStr).toLocaleString('zh-TW', {
            month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
        });
    };

    const statusBadge = (status: string) => {
        const colors: Record<string, string> = {
            COMPLETED: 'bg-green-100 text-green-700',
            PROCESSING: 'bg-blue-100 text-blue-700',
            PENDING: 'bg-yellow-100 text-yellow-700',
            FAILED: 'bg-red-100 text-red-700',
        };
        return (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || 'bg-gray-100 text-gray-600'}`}>
                {status}
            </span>
        );
    };

    return (
        <div className="p-6 md:p-8 max-w-7xl mx-auto overflow-auto">
            {/* Header */}
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
                    <Activity size={24} className="text-brand-cta" />
                    系統維運管理
                </h1>
                <p className="text-muted-foreground mt-1">
                    {userRole === 'super_admin' ? '超級管理員' : '管理員'}模式 — 會議處理狀態、使用者統計、資源成本
                </p>
            </div>

            {/* Tab navigation */}
            <div className="flex gap-1 mb-6 border-b border-border">
                {[
                    { id: 'overview' as const, icon: BarChart3, label: '總覽' },
                    { id: 'meetings' as const, icon: Database, label: '會議明細' },
                    { id: 'users' as const, icon: Users, label: '使用者' },
                ].map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                            activeTab === tab.id
                                ? 'border-brand-cta text-brand-cta'
                                : 'border-transparent text-muted-foreground hover:text-foreground'
                        }`}
                    >
                        <tab.icon size={16} />
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Overview Tab */}
            {activeTab === 'overview' && overview && (
                <div className="space-y-6">
                    {/* KPI Cards */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <StatCard icon={Users} label="使用者" value={overview.total_users} />
                        <StatCard icon={Database} label="會議總數" value={overview.total_meetings} />
                        <StatCard icon={CheckCircle2} label="已完成" value={overview.meetings_completed} color="text-green-600" />
                        <StatCard icon={AlertTriangle} label="失敗" value={overview.meetings_failed} color="text-red-600" />
                        <StatCard icon={Clock} label="音源時數" value={`${overview.total_audio_hours.toFixed(1)}h`} />
                        <StatCard icon={BarChart3} label="逐字稿段落" value={overview.total_segments.toLocaleString()} />
                        <StatCard icon={Activity} label="處理中" value={overview.meetings_processing} color="text-blue-600" />
                        <StatCard icon={DollarSign} label="月預估成本" value={`$${overview.estimated_monthly_cost_usd}`} />
                    </div>
                </div>
            )}

            {/* Meetings Tab */}
            {activeTab === 'meetings' && (
                <div className="space-y-4">
                    {/* Filters */}
                    <div className="flex flex-wrap gap-3 items-center">
                        <div className="relative">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                            <input
                                type="text"
                                placeholder="搜尋會議名稱..."
                                value={keyword}
                                onChange={e => setKeyword(e.target.value)}
                                onKeyDown={e => e.key === 'Enter' && loadMeetings()}
                                className="pl-9 pr-3 py-2 text-sm border rounded-lg bg-background w-48"
                            />
                        </div>
                        <select
                            value={statusFilter}
                            onChange={e => { setStatusFilter(e.target.value); }}
                            className="px-3 py-2 text-sm border rounded-lg bg-background"
                        >
                            <option value="">全部狀態</option>
                            <option value="COMPLETED">COMPLETED</option>
                            <option value="PROCESSING">PROCESSING</option>
                            <option value="FAILED">FAILED</option>
                            <option value="PENDING">PENDING</option>
                        </select>
                        <input
                            type="text"
                            placeholder="Filter by user..."
                            value={userFilter}
                            onChange={e => setUserFilter(e.target.value)}
                            className="px-3 py-2 text-sm border rounded-lg bg-background w-48"
                        />
                        <input
                            type="date"
                            value={dateFrom}
                            onChange={e => setDateFrom(e.target.value)}
                            className="px-3 py-2 text-sm border rounded-lg bg-background"
                        />
                        <span className="text-muted-foreground text-sm">至</span>
                        <input
                            type="date"
                            value={dateTo}
                            onChange={e => setDateTo(e.target.value)}
                            className="px-3 py-2 text-sm border rounded-lg bg-background"
                        />
                        <button
                            onClick={loadMeetings}
                            className="px-4 py-2 text-sm bg-brand-cta text-white rounded-lg hover:opacity-90"
                        >
                            <Filter size={14} className="inline mr-1" />
                            篩選
                        </button>
                    </div>

                    {/* Meeting Table */}
                    {loading ? (
                        <div className="flex items-center justify-center py-12">
                            <Loader2 className="animate-spin text-brand-cta" size={24} />
                        </div>
                    ) : (
                        <div className="overflow-x-auto border rounded-xl">
                            <table className="w-full text-sm">
                                <thead className="bg-muted/50">
                                    <tr>
                                        <th className="px-4 py-3 text-left font-medium">會議 ID</th>
                                        <th className="px-4 py-3 text-left font-medium">標題</th>
                                        <th className="px-4 py-3 text-left font-medium">狀態</th>
                                        <th className="px-4 py-3 text-left font-medium">擁有者</th>
                                        <th className="px-4 py-3 text-left font-medium">建立時間</th>
                                        <th className="px-4 py-3 text-right font-medium">音源長度</th>
                                        <th className="px-4 py-3 text-right font-medium">段落數</th>
                                        <th className="px-4 py-3 text-right font-medium">處理耗時</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-border">
                                    {meetings.map(m => (
                                        <tr key={m.id} className="hover:bg-muted/30">
                                            <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                                                {m.id.slice(0, 8)}...
                                            </td>
                                            <td className="px-4 py-3 max-w-[200px] truncate">{m.title}</td>
                                            <td className="px-4 py-3">{statusBadge(m.status)}</td>
                                            <td className="px-4 py-3 text-xs">{m.owner_upn?.split('@')[0] || '—'}</td>
                                            <td className="px-4 py-3 text-xs">{formatDate(m.created_at)}</td>
                                            <td className="px-4 py-3 text-right">{formatDuration(m.duration)}</td>
                                            <td className="px-4 py-3 text-right">{m.segment_count || '—'}</td>
                                            <td className="px-4 py-3 text-right">
                                                {m.total_processing_seconds
                                                    ? formatDuration(m.total_processing_seconds)
                                                    : '—'}
                                            </td>
                                        </tr>
                                    ))}
                                    {meetings.length === 0 && (
                                        <tr>
                                            <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                                                無符合條件的會議
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {/* Users Tab */}
            {activeTab === 'users' && (
                <div className="space-y-4">
                    <div className="overflow-x-auto border rounded-xl">
                        <table className="w-full text-sm">
                            <thead className="bg-muted/50">
                                <tr>
                                    <th className="px-4 py-3 text-left font-medium">使用者</th>
                                    <th className="px-4 py-3 text-left font-medium">顯示名稱</th>
                                    <th className="px-4 py-3 text-right font-medium">會議數</th>
                                    <th className="px-4 py-3 text-right font-medium">音源時長</th>
                                    <th className="px-4 py-3 text-right font-medium">最後上傳</th>
                                    <th className="px-4 py-3 text-right font-medium">預估成本</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                                {users.map(u => (
                                    <tr key={u.user_upn} className="hover:bg-muted/30">
                                        <td className="px-4 py-3 text-xs">{u.user_upn}</td>
                                        <td className="px-4 py-3">{u.display_name || '—'}</td>
                                        <td className="px-4 py-3 text-right">{u.meeting_count}</td>
                                        <td className="px-4 py-3 text-right">{formatDuration(u.total_audio_seconds)}</td>
                                        <td className="px-4 py-3 text-right text-xs">{formatDate(u.last_upload_at)}</td>
                                        <td className="px-4 py-3 text-right font-medium">${u.estimated_cost_usd}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}

function StatCard({ icon: Icon, label, value, color }: {
    icon: React.ElementType;
    label: string;
    value: string | number;
    color?: string;
}) {
    return (
        <div className="bg-card rounded-xl border border-border p-4">
            <div className="flex items-center gap-2 mb-2">
                <Icon size={16} className={color || 'text-muted-foreground'} />
                <span className="text-xs text-muted-foreground">{label}</span>
            </div>
            <p className={`text-xl font-bold ${color || 'text-foreground'}`}>{value}</p>
        </div>
    );
}
