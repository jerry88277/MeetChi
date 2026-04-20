'use client';

import React from 'react';
import { FileText, Link as LinkIcon, Calendar, Clock } from 'lucide-react';
import { RagReference } from '@/services/RagService';
import Link from 'next/link';

interface ReferencePanelProps {
  reference: RagReference | null;
  className?: string;
}

export function ReferencePanel({ reference, className = '' }: ReferencePanelProps) {
  if (!reference) {
    return (
      <div className={`flex flex-col items-center justify-center p-8 text-center bg-[#f7f9ff] ${className}`}>
        <div className="w-16 h-16 rounded-2xl bg-white shadow-[0_4px_20px_rgba(24,28,32,0.03)] flex items-center justify-center mb-6">
          <FileText className="w-8 h-8 text-slate-300" />
        </div>
        <h3 className="text-lg font-medium text-slate-400 font-['Manrope']">引用來源</h3>
        <p className="text-sm text-slate-400 mt-2 max-w-[200px]">點擊對話中的引用標記，即在此處檢視該會議的逐字稿段落。</p>
      </div>
    );
  }

  // A helper to highlight part of the text if needed (the RAG could return the specific content)
  // For MVP, we just display the content as-is inside a beautifully styled block.

  return (
    <div className={`flex flex-col h-full bg-[#f7f9ff] overflow-y-auto ${className}`}>
      <div className="p-8 space-y-6">
        
        {/* Header Topic */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 mb-4 rounded-full bg-[#eef4ff] text-[#0052cc] text-xs font-semibold uppercase tracking-wider">
              <Calendar className="w-3.5 h-3.5" />
              <span>Reference Source</span>
            </div>
            <h2 className="text-2xl font-semibold text-slate-900 font-['Manrope'] mb-2 leading-tight">
              {reference.meeting_title}
            </h2>
            <div className="flex items-center gap-3 text-sm text-slate-500 font-medium">
              <span className="flex items-center gap-1"><Clock className="w-4 h-4" /> 引用段落</span>
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-600">ID: {reference.meeting_id.slice(0, 8)}</span>
            </div>
          </div>
          
          {/* Deep link button */}
          <Link 
            href={`/dashboard/${reference.meeting_id}${reference.start_time !== undefined ? `?t=${reference.start_time}` : ''}`} 
            className="flex-shrink-0 p-3 bg-white rounded-xl shadow-[0_4px_16px_rgba(24,28,32,0.05)] text-slate-600 hover:text-[#0052cc] hover:shadow-[0_8px_24px_rgba(0,82,204,0.1)] transition-all group"
            title="開啟完整會議記錄"
          >
            <LinkIcon className="w-5 h-5 group-hover:scale-110 transition-transform" />
          </Link>
        </div>

        {/* Content Block - The Transcript Excerpt */}
        <div className="relative mt-8">
          <div className="absolute -left-[1px] top-4 bottom-4 w-1 bg-gradient-to-b from-[#0052cc] to-transparent rounded-full z-10" />
          <div className="bg-white rounded-2xl p-6 shadow-[0_4px_20px_rgba(24,28,32,0.04)] text-slate-800 leading-relaxed font-['Inter'] relative overflow-hidden">
             
             <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
               <FileText className="w-24 h-24" />
             </div>

             <div className="relative z-10">
               {/* Just showing the excerpt content */}
               <p className="whitespace-pre-wrap text-[15px]">{reference.content}</p>
             </div>
          </div>
        </div>

        {/* Technical Data (Context similarity) */}
        {reference.similarity !== undefined && (
          <div className="flex justify-end pt-4">
            <span className="text-xs text-slate-400 font-medium">
              Relevance: {(reference.similarity * 100).toFixed(1)}%
            </span>
          </div>
        )}

      </div>
    </div>
  );
}
