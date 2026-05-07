"use client";

import React, { useState } from "react";
import { Panel, Group, Separator } from "react-resizable-panels";
import { RagSidebar } from "./RagSidebar";
import { ChatPanel } from "./ChatPanel";
import { ReferencePanel } from "./ReferencePanel";
import { RagCitation } from "@/lib/api";

interface RagWorkspaceProps {
  onBack: () => void;
}

export function RagWorkspace({ onBack }: RagWorkspaceProps) {
  const [activeCitation, setActiveCitation] = useState<RagCitation | null>(null);

  return (
    <div className="w-full h-full bg-surface text-foreground font-sans flex overflow-hidden">
      <Group orientation="horizontal" className="w-full h-full">
        {/* Left Sidebar: 歷史紀錄與主控區 (20%) */}
        <Panel
          id="rag-sidebar"
          defaultSize={20}
          minSize={15}
          maxSize={30}
          className="border-r border-border/50 bg-background/50 h-full flex flex-col z-20"
        >
          <RagSidebar onBack={onBack} />
        </Panel>

        {/* 拖拉把手 (Resize Handle) */}
        <Separator id="rag-sep-1" className="w-1 bg-border/20 hover:bg-brand-cta transition-colors duration-200 cursor-col-resize active:bg-brand-cta z-30" />

        {/* Middle: 聊天交談室 (50% or 80%) */}
        <Panel id="rag-chat" className="bg-surface h-full flex flex-col relative z-10" defaultSize={50} minSize={30}>
          <ChatPanel onCitationClick={(citation) => setActiveCitation(citation)} />
        </Panel>

        {/* 若有選中引用，顯示右側面板 (30%) */}
        {activeCitation && (
          <>
            <Separator id="rag-sep-2" className="w-1 bg-border/20 hover:bg-brand-cta transition-colors duration-200 cursor-col-resize active:bg-brand-cta z-30" />
            <Panel
              id="rag-reference"
              defaultSize={30}
              minSize={20}
              collapsible
              className="border-l border-border/50 bg-background/50 h-full flex flex-col shadow-2xl z-20"
            >
              <ReferencePanel
                citation={activeCitation}
                onClose={() => setActiveCitation(null)}
              />
            </Panel>
          </>
        )}
      </Group>
    </div>
  );
}
