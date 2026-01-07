'use client';

import { useState, useEffect } from 'react';
import { api, Meeting } from '@/lib/api';
import { ArrowLeft, Clock, Calendar, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

interface HistoryPageProps {
    isDrawer?: boolean;
}

export default function HistoryPage({ isDrawer = false }: HistoryPageProps) {
    const [meetings, setMeetings] = useState<Meeting[]>([]);
    const [loading, setLoading] = useState(true);
    const router = useRouter();

    useEffect(() => {
        const fetchMeetings = async () => {
            try {
                const data = await api.getMeetings();
                setMeetings(data);
            } catch (e) {
                console.error(e);
            } finally {
                setLoading(false);
            }
        };
        fetchMeetings();
    }, []);

    const handleDelete = async (id: string, e: React.MouseEvent) => {
        e.stopPropagation(); // Prevent navigation
        if (!confirm('Are you sure you want to delete this meeting? This action cannot be undone.')) return;
        
        try {
            await api.deleteMeeting(id);
            setMeetings(prev => prev.filter(m => m.id !== id));
        } catch (error) {
            console.error(error);
            alert('Failed to delete meeting');
        }
    };

    const handleCardClick = (id: string) => {
        router.push(`/history/${id}`);
    };

    const formatTime = (dateString: string) => {
        try {
            // Append 'Z' if missing to treat as UTC, assuming backend stores UTC
            const date = new Date(dateString.endsWith('Z') ? dateString : dateString + 'Z');
            return date.toLocaleString('zh-TW', {
                timeZone: 'Asia/Taipei',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
        } catch (e) {
            return dateString;
        }
    };

    return (
        <div className={`min-h-screen text-white ${isDrawer ? 'p-4 bg-transparent' : 'p-6 bg-black/90'}`}>
            {!isDrawer && (
                <div className="flex items-center gap-4 mb-8">
                    <Link href="/" className="p-2 hover:bg-white/10 rounded-full transition-colors">
                        <ArrowLeft className="w-6 h-6" />
                    </Link>
                    <h1 className="text-2xl font-bold">Meeting History</h1>
                </div>
            )}

            {loading ? (
                <div className="text-center text-white/50">Loading...</div>
            ) : (
                <div className="grid gap-4">
                    {meetings.map((meeting) => (
                        <div 
                            key={meeting.id} 
                            onClick={() => handleCardClick(meeting.id)}
                            className="bg-white/5 p-4 rounded-xl hover:bg-white/10 transition-colors border border-white/10 cursor-pointer group"
                        >
                            <div className="flex justify-between items-start mb-2">
                                <h3 className="font-semibold text-lg">{meeting.title}</h3>
                                <button 
                                    onClick={(e) => handleDelete(meeting.id, e)}
                                    className="p-1.5 hover:bg-red-500/20 text-white/20 hover:text-red-400 rounded-full transition-colors opacity-0 group-hover:opacity-100"
                                    title="Delete Meeting"
                                >
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                            <div className="flex gap-4 text-sm text-white/60">
                                <div className="flex items-center gap-1">
                                    <Calendar className="w-4 h-4" />
                                    <span>{formatTime(meeting.created_at).split(' ')[0]}</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <Clock className="w-4 h-4" />
                                    <span>{formatTime(meeting.created_at).split(' ')[1]}</span>
                                </div>
                                <div className="ml-auto bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded text-xs uppercase">
                                    {meeting.status}
                                </div>
                            </div>
                        </div>
                    ))}
                    {meetings.length === 0 && (
                        <div className="text-center text-white/30 py-12">No meetings found.</div>
                    )}
                </div>
            )}
        </div>
    );
}
