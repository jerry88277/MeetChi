'use client';

import React, { useState } from 'react';
import { ChatPanel } from './ChatPanel';
import { ReferencePanel } from './ReferencePanel';
import { RagReference } from '@/services/RagService';

export interface RagWorkspaceProps {
  onBack?: () => void;
}

export function RagWorkspace({ onBack }: RagWorkspaceProps = {}) {
  const [activeReference, setActiveReference] = useState<RagReference | null>(null);

  const handleCitationClick = (reference: RagReference) => {
    setActiveReference(reference);
  };

  return (
    <div className="flex h-[calc(100vh-theme(spacing.16))] w-full bg-[#f1f3f9] overflow-hidden rounded-tl-2xl border-t border-l border-white/50">
      
      {/* Left Column - Chat Workspace (60%) */}
      <div className="flex-grow flex-shrink w-[60%] min-w-[400px] border-r border-[#e0e2e8]/50 shadow-[4px_0_24px_rgba(24,28,32,0.02)] z-10">
        <ChatPanel onCitationClick={handleCitationClick} className="rounded-tl-2xl bg-white/50" onBack={onBack} />
      </div>

      {/* Right Column - Permanent Reference Panel (40%) */}
      <div className="flex-grow-0 flex-shrink-0 w-[40%] min-w-[320px] bg-[#f7f9ff] z-0">
        <ReferencePanel reference={activeReference} />
      </div>

    </div>
  );
}
