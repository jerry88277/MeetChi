"use client";

import React, { useEffect, useState, useRef } from "react";
import { Send, FileText, Loader2, History, ChevronDown, X, Sparkles } from "lucide-react";
import { useSession } from "next-auth/react";
import { api, RagCitation, RagHistoryItem, RagGreetingResponse } from "@/lib/api";
import { RAG_INACTIVITY_MS } from "@/lib/config";

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

  const WELCOME_MESSAGE: Message = {
    id: "welcome",
    role: "ai",
    text:
      "哈囉！我是 ChiMemo — 您的跨會議 AI 助理。我會搜尋並**彙整您所有過去會議中同一主題**的相關內容。\n\n" +
      "💡 建議用「主題 / 關鍵字」提問，避免直接用會議檔名。例如：\n" +
      "  • 彙整最近所有提到 AI 投資 ROI 的討論\n" +
      "  • 各場會議對 RAG 架構的看法有什麼共識或分歧？\n" +
      "  • 客服流程改善在哪幾場會議被提到？\n" +
      "  • 比較不同會議對 KPI 的設定差異\n\n" +
      "聚焦單一主題每次效果最好；找不到答案時我會提示可能的近似主題。",
    citations: []
  };

  // 2026-06-08: Restore messages from sessionStorage so conversation survives tab switching.
  // Key is scoped to userUpn so switching accounts always starts fresh.
  const storageKey = userUpn ? `rag_messages_${userUpn}` : null;

  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window === "undefined" || !storageKey || !userUpn) return [WELCOME_MESSAGE];
    try {
      // Clear on page reload (navigation type = reload)
      const navEntries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
      const isReload = navEntries[0]?.type === 'reload';
      if (isReload) {
        sessionStorage.removeItem(storageKey);
        localStorage.removeItem(`rag_last_active_${userUpn}`);
        return [WELCOME_MESSAGE];
      }

      // Clear on 30min inactivity
      const lastActive = localStorage.getItem(`rag_last_active_${userUpn}`);
      if (lastActive && Date.now() - parseInt(lastActive, 10) > RAG_INACTIVITY_MS) {
        sessionStorage.removeItem(storageKey);
        localStorage.removeItem(`rag_last_active_${userUpn}`);
        return [WELCOME_MESSAGE];
      }

      const saved = sessionStorage.getItem(storageKey);
      if (saved) return JSON.parse(saved) as Message[];
    } catch {
      // ignore parse errors
    }
    return [WELCOME_MESSAGE];
  });

  // Sync messages to sessionStorage on every change
  React.useEffect(() => {
    if (!storageKey) return;
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(messages));
    } catch {
      // quota exceeded or private browsing — silently ignore
    }
  }, [messages, storageKey]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll only when user is near bottom (within 150px threshold)
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150;
    if (isNearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isLoading]);

  // 2026-06-08 g6: Personalized greeting card (five-star hotel check-in UX)
  const [greeting, setGreeting] = useState<RagGreetingResponse | null>(null);
  const [greetingLoading, setGreetingLoading] = useState(false);
  const [greetingCollapsed, setGreetingCollapsed] = useState(false);

  useEffect(() => {
    if (!userUpn) return;
    setGreetingLoading(true);
    api.getRagGreeting(userUpn)
      .then(setGreeting)
      .catch(() => {}) // silently hide on error — greeting is non-critical
      .finally(() => setGreetingLoading(false));
  }, [userUpn]);

  // 2026-05-25 Y5：RAG 查詢歷史。Drop-down 顯示近 90 天的查詢，點擊可 re-fire。
  const [historyItems, setHistoryItems] = useState<RagHistoryItem[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);

  const [historyError, setHistoryError] = useState(false);

  const loadHistory = React.useCallback(async () => {
    if (!userUpn) return;
    setIsHistoryLoading(true);
    setHistoryError(false);
    try {
      const items = await api.getRagHistory(userUpn, 90, 50);
      setHistoryItems(items);
    } catch (err) {
      console.error('Load RAG history failed:', err);
      setHistoryError(true);
    } finally {
      setIsHistoryLoading(false);
    }
  }, [userUpn]);

  useEffect(() => {
    if (isHistoryOpen && historyItems.length === 0) loadHistory();
  }, [isHistoryOpen, historyItems.length, loadHistory]);

  const sendMessage = async (text: string) => {
    const messageText = text.trim();
    if (!messageText || isLoading) return;

    const userMsg: Message = { id: Date.now().toString(), role: "user", text: messageText, citations: [] };
    // Update last active timestamp for 30min inactivity tracking
    if (userUpn) {
      try { localStorage.setItem(`rag_last_active_${userUpn}`, Date.now().toString()); } catch {}
    }
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
      // 2026-05-25 (Y3) low-score fallback：當所有 citations similarity 都偏低
      // (< 0.6) 或回應屬 no_answer，主動提供「最接近的相關段落 + 試另一個主題」
      // 引導，避免使用者卡住不知道下一步。
      let answerText = res.answer;
      const hasCitations = res.citations && res.citations.length > 0;
      const maxSim = hasCitations
        ? Math.max(...res.citations.map(c => c.similarity ?? 0))
        : 0;
      const lowConfidence = (res.confidence === 'no_answer' || res.confidence === 'low')
        || (hasCitations && maxSim < 0.6);
      if (lowConfidence && hasCitations) {
        // List unique meeting titles in top citations as topic suggestions
        const uniqueMeetings = Array.from(
          new Set(res.citations.slice(0, 5).map(c => c.meeting_title))
        ).slice(0, 5);
        const hint = (
          "\n\n💡 我沒有找到很精準的答案，可能因為：\n" +
          "  1. 提問主題與會議內容差距較大\n" +
          "  2. 用了會議檔名而非主題關鍵字\n\n" +
          "**最接近的相關會議**（相似度 " + (maxSim * 100).toFixed(0) + "% 以下）：\n" +
          uniqueMeetings.map((t, i) => `  ${i + 1}. ${t}`).join('\n') +
          "\n\n建議試試：聚焦該會議的具體主題（如 AI、KPI、流程改善）再問一次。"
        );
        answerText = answerText + hint;
      }
      setMessages(prev => [
        ...prev,
        { id: (Date.now() + 1).toString(), role: "ai", text: answerText, citations: res.citations }
      ]);
      // Y5：清掉 cached history，下次開 dropdown 重新拿（含這次新增的）
      setHistoryItems([]);
    } catch (err) {
      console.error(err);
      setMessages(prev => [
        ...prev,
        { id: (Date.now() + 1).toString(), role: "ai", text: `⚠️ 這次查詢沒有順利完成，請稍後再試。若持續失敗，可透過左側邊欄「回報問題」按鈕反饋。\n\n---\n💡 您的問題：「${userMsg.text}」`, citations: [] }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    await sendMessage(input);
  };

  const handleSuggestedClick = (suggestedText: string) => {
    if (isLoading) return;
    setInput(suggestedText);
    void sendMessage(suggestedText);
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
    <div className="flex flex-col h-full bg-surface relative">
      {/* 2026-05-25 Y5：歷史 dropdown 觸發 + 浮動列表 */}
      <div className="sticky top-0 z-20 bg-surface/95 backdrop-blur-sm border-b border-border px-4 py-2 flex items-center justify-end">
        <button
          type="button"
          onClick={() => setIsHistoryOpen(v => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
          title="查看過去 90 天的查詢紀錄"
          aria-expanded={isHistoryOpen}
          aria-controls="rag-history-panel"
        >
          <History size={14} />
          <span>歷史查詢</span>
          <ChevronDown size={12} className={`transition-transform ${isHistoryOpen ? 'rotate-180' : ''}`} />
        </button>
      </div>
      {isHistoryOpen && (
        <div id="rag-history-panel" className="absolute top-12 right-4 z-30 w-[min(28rem,calc(100%-2rem))] max-h-96 overflow-y-auto bg-card border border-border rounded-xl shadow-xl">
          <div className="sticky top-0 bg-card border-b border-border px-3 py-2 flex items-center justify-between">
            <span className="text-xs font-bold text-foreground">過去 90 天查詢紀錄</span>
            <button onClick={() => setIsHistoryOpen(false)} className="text-muted-foreground hover:text-foreground" aria-label="關閉歷史紀錄">
              <X size={14} />
            </button>
          </div>
          {isHistoryLoading && (
            <div className="p-4 text-center text-xs text-muted-foreground">
              <Loader2 size={14} className="inline animate-spin mr-1" /> 載入中...
            </div>
          )}
          {!isHistoryLoading && !historyError && historyItems.length === 0 && (
            <div className="p-6 text-center text-xs text-muted-foreground">
              還沒有查詢紀錄
            </div>
          )}
          {!isHistoryLoading && historyError && (
            <div className="p-6 text-center">
              <p className="text-xs text-status-error mb-2">載入歷史紀錄失敗</p>
              <button
                type="button"
                onClick={loadHistory}
                className="text-xs px-3 py-1.5 text-brand-cta hover:bg-brand-cta/10 rounded-lg transition-colors"
              >
                重試
              </button>
            </div>
          )}
          {!isHistoryLoading && historyItems.length > 0 && (
            <ul className="divide-y divide-border" role="listbox">
              {historyItems.map(item => (
                <li key={item.id} role="option">
                  <button
                    type="button"
                    className="w-full text-left p-3 hover:bg-muted cursor-pointer transition-colors focus:outline-none focus:bg-muted"
                    onClick={() => {
                    // 載入歷史對話（問 + 答），而非僅填入輸入框
                    const historyMessages: Message[] = [
                      { id: `h-${item.id}-q`, role: "user", text: item.query, citations: [] },
                    ];
                    if (item.answer_preview) {
                      historyMessages.push({
                        id: `h-${item.id}-a`,
                        role: "ai",
                        text: item.answer_preview,
                        citations: [],
                      });
                    }
                    setMessages(prev => {
                      // 保留第一則歡迎訊息，加入歷史對話
                      const welcome = prev.length > 0 ? [prev[0]] : [];
                      return [...welcome, ...historyMessages];
                    });
                    setIsHistoryOpen(false);
                  }}
                  title="點擊載入歷史對話"
                >
                  <p className="text-sm text-foreground line-clamp-2 mb-1">{item.query}</p>
                  {item.answer_preview && (
                    <p className="text-xs text-muted-foreground line-clamp-1 mb-1">{item.answer_preview}</p>
                  )}
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <span>{new Date(item.created_at).toLocaleString('zh-TW', { hour12: false, timeZone: 'Asia/Taipei' })}</span>
                    <span>·</span>
                    <span>{item.citation_count} 個來源</span>
                    {item.confidence && (
                      <>
                        <span>·</span>
                        <span className={item.confidence === 'high' ? 'text-status-success' : item.confidence === 'no_answer' ? 'text-status-warning' : ''}>
                          {item.confidence}
                        </span>
                      </>
                    )}
                  </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {/* Greeting Card — loads once on mount, collapses after first interaction */}
        {greetingLoading && (
          <div className="mb-2 p-4 rounded-2xl border border-border bg-card animate-pulse">
            <div className="h-4 bg-muted rounded w-3/4 mb-2" />
            <div className="h-3 bg-muted rounded w-1/2" />
          </div>
        )}
        {!greetingLoading && greeting && (
          <div className="mb-2 rounded-2xl border border-brand-cta/20 bg-card shadow-sm overflow-hidden">
            {/* Header — always visible, toggles collapse */}
            <button
              type="button"
              onClick={() => setGreetingCollapsed(v => !v)}
              className="w-full flex items-start justify-between gap-3 p-4 hover:bg-muted/50 transition-colors text-left"
            >
              <div className="flex items-start gap-2.5 min-w-0">
                <Sparkles size={15} className="text-brand-chimei-orange mt-0.5 shrink-0" />
                <p className="text-sm text-foreground leading-snug">{greeting.greeting_text}</p>
              </div>
              <ChevronDown
                size={14}
                className={`shrink-0 mt-1 text-muted-foreground transition-transform ${greetingCollapsed ? "" : "rotate-180"}`}
              />
            </button>

            {/* Expanded body */}
            {!greetingCollapsed && (
              <div className="px-4 pb-4 space-y-3 border-t border-border/50">
                {/* Top topic pills */}
                {greeting.top_topics.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-3">
                    {greeting.top_topics.map(topic => (
                      <span
                        key={topic}
                        className="text-xs px-2.5 py-1 rounded-full bg-brand-cta/10 text-brand-cta border border-brand-cta/20"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                )}

                {/* Pending action count */}
                {greeting.pending_action_count > 0 && (
                  <p className="text-xs text-muted-foreground">
                    📌 您有{" "}
                    <span className="font-semibold text-foreground">
                      {greeting.pending_action_count}
                    </span>{" "}
                    項待辦行動項目尚未完成
                  </p>
                )}

                {/* Suggested question chips → inject into input */}
                {greeting.suggested_questions.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {greeting.suggested_questions.map(q => (
                      <button
                        key={q}
                        type="button"
                        onClick={() => handleSuggestedClick(q)}
                        className="text-xs px-3 py-1.5 rounded-full border border-border bg-surface hover:bg-brand-cta/10 hover:border-brand-cta hover:text-brand-cta transition-colors text-muted-foreground text-left"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
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
            <div className="bg-card text-foreground rounded-2xl rounded-bl-none p-4 shadow-sm border border-border">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 size={16} className="animate-spin" />
                <span>正在搜尋所有會議段落並彙整回答...</span>
              </div>
              <p className="text-xs text-muted-foreground/60 mt-1.5">通常需要 5-15 秒，取決於會議數量</p>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
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
            className="w-full bg-muted text-foreground border border-border rounded-2xl pl-5 pr-14 py-4 focus:outline-none focus:ring-2 focus:ring-brand-cta/50 transition-[colors,shadow] disabled:opacity-50"
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
