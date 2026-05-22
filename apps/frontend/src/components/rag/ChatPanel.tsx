"use client";

import React, { useState } from "react";
import { Send, FileText, Loader2 } from "lucide-react";
import { useSession } from "next-auth/react";
import { api, RagCitation } from "@/lib/api";

interface ChatPanelProps {
  onCitationClick: (citation: RagCitation) => void;
}

type Message = {
  id: string;
  role: "user" | "ai";
  text: string;
  citations: RagCitation[];
};

export function ChatPanel({ onCitationClick }: ChatPanelProps) {
  // 2026-05-22 (feedback #9 RAG 查不到)：原硬編 'global_test@company.com' 與
  // 任何 meeting_participants 都不匹配 → 查無資料。改用 session.user.email
  // 拿登入者 UPN，後端用此 JOIN meeting_participants enforce 存取控制。
  const { data: session } = useSession();
  const userUpn = session?.user?.email ?? undefined;

  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "ai",
      text: "哈囉！我是您的跨會議助理。您可以問我任何在過去會議紀錄中出現過的討論，例如「之前的行銷週會決定了什麼 KPI？」或「產品架構規劃會議中提到的 RAG 模組在哪裡？」。",
      citations: []
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    
    const userMsg: Message = { id: Date.now().toString(), role: "user", text: input, citations: [] };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      // Extract history, skipping the first hardcoded welcome message
      const history = messages.length > 1
        ? messages.slice(1).map(m => ({ role: m.role, text: m.text }))
        : [];

      if (!userUpn) {
        throw new Error("尚未登入或無法取得使用者識別，請重新整理頁面後再試。");
      }
      const res = await api.askRag(userMsg.text, userUpn, history);
      setMessages(prev => [
        ...prev,
        { id: (Date.now() + 1).toString(), role: "ai", text: res.answer, citations: res.citations }
      ]);
    } catch (err) {
      console.error(err);
      setMessages(prev => [
        ...prev,
        { id: (Date.now() + 1).toString(), role: "ai", text: "抱歉，發生異常錯誤，無法取得回答。", citations: [] }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSuggestedClick = (suggestedText: string) => {
    if (isLoading) return;
    setInput(suggestedText);
    // Option: also auto-send
  };

  const renderMessageTextWithCitations = (text: string, citations: RagCitation[]) => {
    if (!citations || citations.length === 0) return <span className="whitespace-pre-wrap">{text}</span>;

    // Regex to match formats like [來源3], [來源 3], [來源:3]
    const regex = /\[來源\s*:?\s*(\d+)\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(<span key={`text-${lastIndex}`} className="whitespace-pre-wrap">{text.substring(lastIndex, match.index)}</span>);
      }

      const citationIndex = parseInt(match[1], 10) - 1;
      if (citationIndex >= 0 && citationIndex < citations.length) {
        parts.push(
          <button
             key={`match-${match.index}`}
             onClick={() => onCitationClick(citations[citationIndex])}
             className="inline-flex items-center justify-center px-1.5 py-0.5 mx-0.5 text-xs font-bold leading-none bg-brand-cta/15 text-brand-cta hover:bg-brand-cta hover:text-white rounded border border-brand-cta/20 shadow-sm transition-colors cursor-pointer align-baseline"
             title={`展開原文: ${citations[citationIndex].meeting_title}`}
          >
            來源 {match[1]}
          </button>
        );
      } else {
        parts.push(<span key={`text-raw-${match.index}`}>{match[0]}</span>);
      }
      lastIndex = regex.lastIndex;
    }

    if (lastIndex < text.length) {
      parts.push(<span key={`text-${lastIndex}`} className="whitespace-pre-wrap">{text.substring(lastIndex)}</span>);
    }

    return <>{parts}</>;
  };

  return (
    <div className="flex flex-col h-full bg-surface">
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] md:max-w-[75%] rounded-2xl p-4 md:p-5 ${msg.role === "user" ? "bg-brand-cta text-white rounded-br-none shadow-md" : "bg-card text-foreground rounded-bl-none shadow-sm border border-border"}`}>
              <div className="leading-relaxed text-[15px]">
                {msg.role === "user" ? (
                   <span className="whitespace-pre-wrap">{msg.text}</span>
                ) : (
                   renderMessageTextWithCitations(msg.text, msg.citations)
                )}
              </div>

              {/* Citations array */}
              {msg.citations && msg.citations.length > 0 && msg.role === "ai" && (
                <div className="mt-4 flex flex-wrap gap-2 pt-3 border-t border-border">
                  {msg.citations.map((cite, index) => (
                    <button
                      key={`${cite.meeting_id}-${index}`}
                      onClick={() => onCitationClick(cite)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full bg-brand-cta/10 text-brand-cta hover:bg-brand-cta hover:text-white transition-colors border border-brand-cta/20 shadow-sm"
                    >
                      <FileText size={12} />
                      [{index + 1}] {cite.meeting_title}
                      {cite.similarity && <span className="opacity-60 ml-1">{(cite.similarity * 100).toFixed(0)}%</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-card text-foreground rounded-2xl rounded-bl-none p-4 shadow-sm border border-border flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 size={16} className="animate-spin" /> 正在搜尋文獻並生成回答...
            </div>
          </div>
        )}
      </div>

      <div className="p-4 bg-card border-t border-border">
        <div className="flex flex-wrap gap-2 mb-3">
          <button
            type="button"
            onClick={() => handleSuggestedClick("總結最近所有會議對於產品推廣的提案與進度")}
            className="text-xs px-3 py-1.5 rounded-full border border-border bg-surface hover:bg-brand-cta/10 hover:border-brand-cta hover:text-brand-cta transition-colors text-muted-foreground whitespace-nowrap"
          >
            總結產品推廣提案與進度
          </button>
          <button
            type="button"
            onClick={() => handleSuggestedClick("有誰提到關於 RAG 架構的事？")}
            className="text-xs px-3 py-1.5 rounded-full border border-border bg-surface hover:bg-brand-cta/10 hover:border-brand-cta hover:text-brand-cta transition-colors text-muted-foreground whitespace-nowrap"
          >
            誰提過 RAG 架構？
          </button>
        </div>

        <form onSubmit={handleSend} className="relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
            placeholder="請輸入您的問題，例如：回顧昨天的行銷週會討論了什麼？"
            className="w-full bg-muted text-foreground border border-border rounded-2xl pl-5 pr-14 py-4 focus:outline-none focus:ring-2 focus:ring-brand-cta/50 transition-all disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="absolute right-2 p-2.5 bg-brand-cta text-white rounded-xl hover:bg-brand-cta/90 disabled:opacity-50 disabled:hover:bg-brand-cta transition-colors shadow-sm"
            aria-label="送出問題"
          >
            {isLoading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
          </button>
        </form>
      </div>
    </div>
  );
}
