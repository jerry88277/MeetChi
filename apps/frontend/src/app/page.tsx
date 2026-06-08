"use client";

import React, { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { ArrowRight, Loader2 } from 'lucide-react';

/**
 * Enterprise portal entry page (2026-06-08 redesign).
 *
 * Approach: taste-skill "Soft Structuralism" — same warm-surface language as login page.
 * No marketing copy, no feature cards, no dark gradient.
 * Authenticated users → redirect to /dashboard immediately.
 * Unauthenticated users → minimal branded entry with single CTA to /login.
 */
export default function HomePage() {
    const router = useRouter();
    const { data: session, status } = useSession();

    useEffect(() => {
        if (status === 'authenticated' && session?.user) {
            router.replace('/dashboard');
        }
        if (status === 'unauthenticated') {
            router.replace('/login');
        }
    }, [status, session, router]);

    // Show loading spinner while session resolves
    return (
        <div className="min-h-screen bg-surface flex items-center justify-center">
            <div className="text-center space-y-4">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-brand-navy rounded-2xl shadow-lg">
                    <span className="text-3xl font-bold text-white">M</span>
                </div>
                {status === 'loading' ? (
                    <Loader2 className="w-6 h-6 text-brand-cta animate-spin mx-auto" />
                ) : (
                    <div className="flex flex-col items-center gap-3">
                        <p className="text-muted-foreground text-sm">正在導向...</p>
                        <Link
                            href="/login"
                            className="inline-flex items-center gap-2 px-5 py-2.5 bg-brand-cta text-white rounded-xl text-sm font-medium hover:bg-brand-cta/90 transition-colors"
                        >
                            前往登入 <ArrowRight size={16} />
                        </Link>
                    </div>
                )}
            </div>
        </div>
    );
}
