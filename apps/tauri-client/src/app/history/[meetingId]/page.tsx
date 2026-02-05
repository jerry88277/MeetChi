'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { api, Meeting, TranscriptSegment } from '@/lib/api';
import { ArrowLeft, FileText, List, CheckSquare, AlertTriangle, Play, Download, Settings as SettingsIcon } from 'lucide-react';
import Link from 'next/link';
import { SummarySettingsModal } from '@/components/SummarySettingsModal';

interface SummaryData {
    summary: string;
    action_items?: string[];
    decisions?: string[];
    risks?: string[];
}

export default function MeetingDetailPage() {
    const params = useParams();
    const meetingId = params.meetingId as string;

    const [meeting, setMeeting] = useState<Meeting | null>(null);
    const [loading, setLoading] = useState(true);
    const [generatingSummary, setGeneratingSummary] = useState(false);
    const [summaryData, setSummaryData] = useState<SummaryData | null>(null);
    const [isPolling, setIsPolling] = useState(false);
    const [showSummarySettingsModal, setShowSummarySettingsModal] = useState(false);

    const fetchMeeting = async () => {
        try {
            const data = await api.getMeeting(meetingId);
            setMeeting(data);
            if (data.summary_json) {
                try {
                    const parsed = JSON.parse(data.summary_json);
                    setSummaryData(parsed);
                    setIsPolling(false); // Stop polling if summary is found
                } catch (e) {
                    console.error("Failed to parse summary JSON", e);
                }
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (meetingId) {
            fetchMeeting();
        }
    }, [meetingId]);

    // Polling effect
    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (isPolling) {
            interval = setInterval(() => {
                fetchMeeting();
            }, 5000);
        }
        return () => clearInterval(interval);
    }, [isPolling]);

    const handleGenerateSummary = async (options?: { template: string, context: string, length: string, style: string }) => {
        if (!meetingId) return;
        setGeneratingSummary(true);
        try {
            // Send new options to the backend API
            const template = options?.template || meeting?.template_name || 'general';
            const context = options?.context || '';
            const length = options?.length || '';
            const style = options?.style || '';

            await api.generateSummary(meetingId, template, context, length, style); // Update API call
            setIsPolling(true); // Start polling
        } catch (e) {
            console.error(e);
            alert('Failed to start summary generation');
        } finally {
            setGeneratingSummary(false);
        }
    };

    if (loading) return <div className="min-h-screen bg-black/90 text-white flex items-center justify-center">Loading...</div>;
    if (!meeting) return <div className="min-h-screen bg-black/90 text-white flex items-center justify-center">Meeting not found</div>;

    return (
        <div className="min-h-screen bg-black/90 text-white flex flex-col h-screen">
            {/* Header */}
            <header className="flex items-center gap-4 p-4 border-b border-white/10 bg-black/50 backdrop-blur-md sticky top-0 z-10">
                <Link href="/history" className="p-2 hover:bg-white/10 rounded-full transition-colors">
                    <ArrowLeft className="w-5 h-5" />
                </Link>
                <div>
                    <h1 className="text-xl font-bold">{meeting.title}</h1>
                    <div className="text-xs text-white/50 flex gap-2">
                        <span>{new Date(meeting.created_at).toLocaleString()}</span>
                        <span>•</span>
                        <span>{meeting.template_name}</span>
                    </div>
                </div>
                <div className="ml-auto flex gap-2">
                    <button className="p-2 hover:bg-white/10 rounded-full transition-colors" title="Export">
                        <Download className="w-5 h-5" />
                    </button>
                    {/* Settings for Summary */}
                    {!summaryData && ( // Only show settings if no summary is generated yet
                        <button
                            onClick={() => setShowSummarySettingsModal(true)}
                            className="p-2 hover:bg-white/10 rounded-full transition-colors"
                            title="Summary Settings"
                        >
                            <SettingsIcon className="w-5 h-5" />
                        </button>
                    )}
                </div>
            </header>

            {/* Content - Split View */}
            <div className="flex-1 flex overflow-hidden">
                {/* Left: Transcript (60%) */}
                <div className="flex-1 overflow-y-auto p-6 border-r border-white/10 w-3/5">
                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                        <FileText className="w-5 h-5 text-blue-400" />
                        Transcript
                    </h2>
                    <div className="space-y-4">
                        {meeting.transcript_segments?.map((seg) => (
                            <div key={seg.id || seg.order} className="flex gap-4 group hover:bg-white/5 p-2 rounded-lg transition-colors">
                                <div className="text-xs text-white/30 w-12 pt-1 font-mono flex flex-col items-end gap-1">
                                    <span>{new Date(seg.start_time * 1000).toISOString().substr(14, 5)}</span>
                                    {seg.speaker && (
                                        <span className="text-[10px] px-1 py-0.5 bg-blue-500/20 text-blue-300 rounded uppercase tracking-wider">
                                            {seg.speaker.replace('SPEAKER_', 'S')}
                                        </span>
                                    )}
                                </div>
                                <div className="flex-1">
                                    <div className="text-sm text-white/90 mb-1">
                                        {seg.content_polished || seg.content_raw}
                                    </div>
                                    {seg.content_translated && (
                                        <div className="text-sm text-white/50 italic">
                                            {seg.content_translated}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                        {(!meeting.transcript_segments || meeting.transcript_segments.length === 0) && (
                            <div className="text-white/30 text-center py-10">No transcript available.</div>
                        )}
                    </div>
                </div>

                {/* Right: Summary (40%) */}
                <div className="w-2/5 overflow-y-auto p-6 bg-white/5">
                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                        <List className="w-5 h-5 text-green-400" />
                        Summary & Intelligence
                    </h2>

                    {summaryData ? (
                        <div className="space-y-6">
                            <div className="bg-white/5 p-4 rounded-xl border border-white/10">
                                <h3 className="text-sm font-bold text-white/70 uppercase mb-2">Executive Summary</h3>
                                <p className="text-sm leading-relaxed text-white/90">{summaryData.summary}</p>
                            </div>

                            {summaryData.action_items && summaryData.action_items.length > 0 && (
                                <div>
                                    <h3 className="text-sm font-bold text-white/70 uppercase mb-2 flex items-center gap-2">
                                        <CheckSquare className="w-4 h-4 text-blue-400" />
                                        Action Items
                                    </h3>
                                    <ul className="space-y-2">
                                        {summaryData.action_items.map((item, i) => (
                                            <li key={i} className="flex gap-2 text-sm bg-blue-500/10 p-2 rounded border border-blue-500/20">
                                                <span className="text-blue-400">•</span>
                                                <span>{item}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            {summaryData.decisions && summaryData.decisions.length > 0 && (
                                <div>
                                    <h3 className="text-sm font-bold text-white/70 uppercase mb-2 flex items-center gap-2">
                                        <CheckSquare className="w-4 h-4 text-green-400" />
                                        Decisions
                                    </h3>
                                    <ul className="space-y-2">
                                        {summaryData.decisions.map((item, i) => (
                                            <li key={i} className="flex gap-2 text-sm bg-green-500/10 p-2 rounded border border-green-500/20">
                                                <span className="text-green-400">•</span>
                                                <span>{item}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            {summaryData.risks && summaryData.risks.length > 0 && (
                                <div>
                                    <h3 className="text-sm font-bold text-white/70 uppercase mb-2 flex items-center gap-2">
                                        <AlertTriangle className="w-4 h-4 text-orange-400" />
                                        Risks & Blockers
                                    </h3>
                                    <ul className="space-y-2">
                                        {summaryData.risks.map((item, i) => (
                                            <li key={i} className="flex gap-2 text-sm bg-orange-500/10 p-2 rounded border border-orange-500/20">
                                                <span className="text-orange-400">•</span>
                                                <span>{item}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center h-64 text-center">
                            {isPolling ? (
                                <div className="flex flex-col items-center gap-4">
                                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
                                    <p className="text-white/60 text-sm animate-pulse">Generating summary with AI...</p>
                                </div>
                            ) : (
                                <>
                                    <p className="text-white/40 mb-4">No summary generated yet.</p>
                                    <button
                                        onClick={() => setShowSummarySettingsModal(true)} // Open modal instead of direct generation
                                        disabled={generatingSummary}
                                        className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                                    >
                                        {generatingSummary ? 'Starting...' : 'Configure & Generate Summary'}
                                    </button>
                                </>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Render Summary Settings Modal */}
            <SummarySettingsModal
                isOpen={showSummarySettingsModal}
                onClose={() => setShowSummarySettingsModal(false)}
                meetingId={meetingId}
                currentTemplate={meeting.template_name}
                onGenerateSummary={handleGenerateSummary}
                generatingSummary={generatingSummary}
            />
        </div>
    );
}
