"use client";

import React, { useEffect, useState, useRef } from "react";
import { Send, FileText, Loader2, History, ChevronDown, X, Sparkles, RefreshCw, MessageSquareWarning } from "lucide-react";
import { useSession } from "next-auth/react";
import ReactMarkdown from "react-markdown";
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
  // R-B2 / R-C1：錯誤氣泡渲染「重試」與「回報問題」動作
  isError?: boolean;
  retryQuery?: string;
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
      "哈囉！我是 ChiMemo — 您的會議小幫手。我會幫您**一次翻遍所有過去的會議**，找出同一件事在不同會議裡的相關討論並整理給您。\n\n" +
      "💡 建議用「想了解的主題或關鍵字」來問，不用打會議檔名。例如：\n" +
      "  • 最近幾場會議談到「客服流程改善」的內容幫我整理一下\n" +
      "  • 大家對「新產品上市時程」有沒有共識或不同意見？\n" +
      "  • 「預算」這件事在哪幾場會議被討論過？\n" +
      "  • 比較不同會議對「年度目標」的設定差異\n\n" +
      "一次問一個主題效果最好；如果找不到，我會提示您幾個比較接近的會議。",
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
  // R-B1：進行中查詢的 AbortController，供取消
  const abortRef = useRef<AbortController | null>(null);
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
    // R-B2：重試前先移除舊的錯誤氣泡，避免堆疊
    setMessages(prev => [...prev.filter(m => !m.isError), userMsg]);
    setInput("");
    setIsLoading(true);

    // R-B1：建立 AbortController，供使用者取消
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      // Extract history, skipping the first hardcoded welcome message
      const history = messages.filter(m => !m.isError).length > 1
        ? messages.filter(m => !m.isError).slice(1).map(m => ({ role: m.role, text: m.text }))
        : [];

      if (!userUpn) {
        throw new Error("尚未登入或無法取得使用者識別，請重新整理頁面後再試。");
      }
      const res = await api.askRag(userMsg.text, userUpn, history, undefined, controller.signal);
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
          "\n\n建議試試：聚焦該會議的具體主題再問一次。"
        );
        answerText = answerText + hint;
      }
      // R-A6：完全查無 citations 時也給引導，而非空手而回
      if (!hasCitations && res.confidence !== 'high') {
        answerText = answerText + (
          "\n\n💡 這次沒有找到相關的會議段落，可以試試：\n" +
          "  • 換個關鍵字或更廣的主題（例如用「預算」而非特定檔名）\n" +
          "  • 確認相關會議已上傳並完成處理（剛上傳的會議需幾分鐘建立索引）"
        );
      }
      setMessages(prev => [
        ...prev,
        { id: (Date.now() + 1).toString(), role: "ai", text: answerText, citations: res.citations }
      ]);
      // Y5：清掉 cached history，下次開 dropdown 重新拿（含這次新增的）
      setHistoryItems([]);
    } catch (err) {
      // R-B1：使用者主動取消——靜默停止，不顯示錯誤
      if (err instanceof DOMException && err.name === 'AbortError') {
        return;
      }
      console.error(err);
      // R-B2 / R-C1：錯誤氣泡帶「重試」與「回報問題」動作，不再叫使用者去看不到的 sidebar
      setMessages(prev => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "ai",
          text: `⚠️ 這次查詢沒有順利完成，請稍後再試。\n\n💡 您的問題：「${userMsg.text}」`,
          citations: [],
          isError: true,
          retryQuery: userMsg.text,
        }
      ]);
    } finally {
      abortRef.current = null;
      setIsLoading(false);
    }
  };

  // R-B1：取消進行中的查詢
  const cancelQuery = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsLoading(false);
  };

  // R-C1：透過全域事件開啟回報視窗（手機 Drawer 看不到 sidebar 的回報鈕）
  const openReport = () => {
    try {
      window.dispatchEvent(new CustomEvent('meetchi:open-feedback'));
    } catch { /* ignore */ }
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
    if (!citations || citations.length === 0) {
      return (
        <div className="prose prose-sm max-w-none dark:prose-invert prose-p:my-1.5 prose-li:my-0.5 prose-headings:my-2">
          <ReactMarkdown
            components={{
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-cta underline">{children}</a>
              ),
            }}
          >
            {text}
          </ReactMarkdown>
        </div>
      );
    }

    // Split text by citation markers [來源N], render each segment as Markdown
    const regex = /\[來源\s*:?\s*(\d+)\]/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        const segment = text.substring(lastIndex, match.index);
        parts.push(
          <span key={`md-${lastIndex}`} className="inline">
            <ReactMarkdown>{segment}</ReactMarkdown>
          </span>
        );
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
      const segment = text.substring(lastIndex);
      parts.push(
        <span key={`md-${lastIndex}`} className="inline">
          <ReactMarkdown>{segment}</ReactMarkdown>
        </span>
      );
    }

    return <div className="prose prose-sm max-w-none dark:prose-invert prose-p:my-1.5 prose-li:my-0.5">{parts}</div>;
  };

  return (
    <div className="flex flex-col h-full bg-surface relative">
      {/* 2026-05-25 Y5：歷史 dropdown 觸發 + 浮動列表 */}
      <div className="sticky top-0 z-20 bg-surface/95 backdrop-blur-sm border-b border-border px-4 py-2 flex items-center justify-end gap-1">
        {messages.length > 1 && (
          <button
            type="button"
            onClick={() => {
              setMessages([WELCOME_MESSAGE]);
              if (storageKey) sessionStorage.removeItem(storageKey);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-status-error hover:bg-status-error/10 rounded-lg transition-colors"
            title="清除對話，開始新主題"
          >
            <X size={12} />
            <span>清除對話</span>
          </button>
        )}
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
                        // R-A1：還原歷史對話的引用（後端 citations_json）
                        citations: item.citations ?? [],
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
                          {item.confidence === 'high' ? '高信心'
                            : item.confidence === 'low' ? '低信心'
                            : item.confidence === 'no_answer' ? '查無資料'
                            : item.confidence}
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
                      <button
                        key={topic}
                        type="button"
                        onClick={() => handleSuggestedClick(`彙整所有提到「${topic}」的會議討論`)}
                        className="text-xs px-2.5 py-1 rounded-full bg-brand-cta/10 text-brand-cta border border-brand-cta/20 hover:bg-brand-cta hover:text-white transition-colors cursor-pointer"
                      >
                        {topic}
                      </button>
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
        {/* R-C3：零會議專屬空狀態 — 引導先上傳，而非讓使用者對空系統提問 */}
        {!greetingLoading && greeting && greeting.meeting_count === 0 && (
          <div className="mb-2 p-5 rounded-2xl border border-dashed border-border bg-muted/30 text-center">
            <Sparkles size={22} className="text-brand-chimei-orange mx-auto mb-2" />
            <p className="text-sm font-medium text-foreground mb-1">還沒有可查詢的會議</p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              ChiMemo 會跨所有會議幫您找答案。<br />
              請先到「會議」頁上傳並完成處理一場會議，稍後回來即可開始提問。
            </p>
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
                      {cite.similarity != null && <span className="opacity-60 ml-1">{(cite.similarity * 100).toFixed(0)}%</span>}
                    </button>
                  ))}
                </div>
              )}

              {/* R-B2 / R-C1：錯誤氣泡內建「重試」與「回報問題」動作 */}
              {msg.isError && msg.role === "ai" && (
                <div className="mt-3 flex flex-wrap gap-2 pt-3 border-t border-border">
                  {msg.retryQuery && (
                    <button
                      type="button"
                      onClick={() => sendMessage(msg.retryQuery!)}
                      disabled={isLoading}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full bg-brand-cta text-white hover:bg-brand-cta/90 transition-colors shadow-sm disabled:opacity-50"
                    >
                      <RefreshCw size={12} /> 重試
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={openReport}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full border border-border bg-surface text-muted-foreground hover:bg-muted transition-colors"
                  >
                    <MessageSquareWarning size={12} /> 回報問題
                  </button>
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
              {/* R-B1：進行中可取消 */}
              <button
                type="button"
                onClick={cancelQuery}
                className="mt-2.5 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full border border-border bg-surface text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <X size={12} /> 取消查詢
              </button>
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
            onClick={() => handleSuggestedClick("最近有哪些重要的決策或結論？")}
            className="text-xs px-3 py-1.5 rounded-full border border-border bg-surface hover:bg-brand-cta/10 hover:border-brand-cta hover:text-brand-cta transition-colors text-muted-foreground whitespace-nowrap"
          >
            最近有哪些重要決策？
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
