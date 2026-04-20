'use client';

import React, { useState } from 'react';
import { ChatPanel } from './ChatPanel';
import { RagReference } from '@/services/RagService';
import { useRouter } from 'next/navigation';

interface RagSidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function RagSidebar({ isOpen, onClose }: RagSidebarProps) {
  const router = useRouter();

  // In the quick sidebar, if user clicks a citation, we probably want to navigate them 
  // to the actual detail view since there is no permanent right panel here.
  const handleCitationClick = (reference: RagReference) => {
    // Navigate to the meeting detail view for this document
    router.push(`/dashboard/meetings/${reference.meeting_id}`);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-40 transition-opacity"
        onClick={onClose}
      />
      
      {/* Drawer */}
      <div className="fixed inset-y-0 right-0 w-[440px] max-w-[90vw] bg-white shadow-2xl flex flex-col z-50 animate-in slide-in-from-right duration-300">
        <ChatPanel 
          onCitationClick={handleCitationClick} 
          isSidebar={true}
          onClose={onClose}
        />
      </div>
    </>
  );
}
