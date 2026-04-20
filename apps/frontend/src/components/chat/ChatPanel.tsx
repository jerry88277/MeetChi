'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, Loader2 } from 'lucide-react';
import { RagService, RagResponse, RagReference } from '@/services/RagService';
import { Button } from '@/components/ui/button';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  references?: RagReference[];
}

interface ChatPanelProps {
  onCitationClick: (ref: RagReference) => void;
  className?: string;
  // If true, it might show a close button or something for sidebar mode
  isSidebar?: boolean; 
  onClose?: () => void;
  onBack?: () => void;
}

export function ChatPanel({ onCitationClick, className = '', isSidebar = false, onClose, onBack }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSubmit = async (text: string) => {
    if (!text.trim() || isLoading) return;
    
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsLoading(true);

    try {
      const response = await RagService.askQuestion(text);
      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.answer,
        references: response.citations
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (error) {
       setMessages(prev => [...prev, {
         id: (Date.now() + 1).toString(),
         role: 'assistant',
         content: '很抱歉，在查詢知識庫時發生錯誤。請稍後再試。'
       }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleHintClick = (hint: string) => {
    handleSubmit(hint);
  };

  // Helper to parse text and replace [1], [2] with clickable buttons
  const renderMessageContent = (text: string, references?: RagReference[]) => {
    if (!references || references.length === 0) return <p className="whitespace-pre-wrap">{text}</p>;

    // Regex to match [1], [2], etc.
    const parts = text.split(/(\[\d+\])/g);
    
    return (
      <p className="whitespace-pre-wrap leading-relaxed text-slate-800">
        {parts.map((part, index) => {
          const match = part.match(/\[(\d+)\]/);
          if (match) {
            const refIndex = parseInt(match[1], 10) - 1; // 1-based index to 0-based
            const ref = references[refIndex];
            if (ref) {
              return (
                <button
                  key={index}
                  onClick={() => onCitationClick(ref)}
                  className="inline-flex items-center justify-center w-5 h-5 mx-1 text-xs font-medium rounded-full bg-blue-100 text-blue-700 hover:bg-blue-600 hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-1"
                  title={ref.meeting_title}
                >
                  {match[1]}
                </button>
              );
            }
          }
          return <span key={index}>{part}</span>;
        })}
      </p>
    );
  };

  return (
    <div className={`flex flex-col h-full bg-[#f1f3f9] ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-[#ffffff] shadow-[0_4px_20px_rgba(24,28,32,0.06)] z-10 rounded-t-xl">
        <div className="flex items-center gap-2">
          <div className="bg-[#0052cc]/10 p-2 rounded-lg">
            <Sparkles className="w-5 h-5 text-[#0052cc]" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-slate-900 font-['Manrope'] tracking-tight">Intelligence Architect</h2>
            <p className="text-xs text-slate-500 font-medium">跨會議知識庫助理</p>
          </div>
        </div>
        {isSidebar && typeof onClose === 'function' && (
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-full transition-colors">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
        )}
        {!isSidebar && typeof onBack === 'function' && (
          <button onClick={onBack} className="flex items-center gap-1.5 px-3 py-1.5 text-slate-500 hover:text-[#0052cc] hover:bg-[#0052cc]/10 rounded-lg transition-colors text-sm font-medium">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
            返回
          </button>
        )}
      </div>

      {/* Chat History */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-8 scroll-smooth">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-6">
            <div className="w-16 h-16 bg-[#eef4ff] rounded-2xl flex items-center justify-center shadow-[0_8px_32px_rgba(0,82,204,0.08)]">
              <Sparkles className="w-8 h-8 text-[#0052cc]" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-slate-900 font-['Manrope'] mb-2">我可以幫忙尋找什麼？</h3>
              <p className="text-sm text-slate-500 max-w-sm">
                快速在所有會議紀錄中檢索、總結重點，並追蹤跨會議的決策脈絡。
              </p>
            </div>
            <div className="flex flex-col w-full max-w-md gap-3 mt-4">
              {['最近一次針對 ASR 的會議結論是？', '列出本週所有的待辦行動', '誰在會議中負責 Cloud Run 部署？'].map((hint) => (
                <button
                  key={hint}
                  onClick={() => handleHintClick(hint)}
                  className="px-4 py-3 text-sm text-left text-slate-700 bg-white hover:bg-blue-50/80 rounded-xl shadow-[0_4px_16px_rgba(24,28,32,0.03)] transition-all flex items-center justify-between group border-l-2 border-transparent hover:border-[#0052cc]"
                >
                  <span>{hint}</span>
                  <span className="text-[#0052cc] opacity-0 group-hover:opacity-100 transition-opacity">→</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div 
                  className={`max-w-[85%] px-5 py-4 ${
                    msg.role === 'user' 
                      ? 'bg-[#0052cc] text-white rounded-2xl rounded-tr-sm shadow-[0_8px_24px_rgba(0,82,204,0.15)]' 
                      : 'bg-white text-slate-900 rounded-2xl rounded-tl-sm shadow-[0_4px_20px_rgba(24,28,32,0.06)]'
                  }`}
                >
                  {msg.role === 'user' ? (
                    <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                  ) : (
                    renderMessageContent(msg.content, msg.references)
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white rounded-2xl rounded-tl-sm px-5 py-4 shadow-[0_4px_20px_rgba(24,28,32,0.06)] flex items-center gap-3">
                  <Loader2 className="w-5 h-5 text-[#0052cc] animate-spin" />
                  <span className="text-sm font-medium text-slate-500">正在查閱知識庫...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white m-4 rounded-2xl shadow-[0_8px_32px_rgba(24,28,32,0.08)] ring-1 ring-slate-100">
        <form 
          onSubmit={(e) => { e.preventDefault(); handleSubmit(inputValue); }}
          className="flex items-end gap-2"
        >
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(inputValue);
              }
            }}
            placeholder="詢問任何關於會議內容的問題..."
            className="flex-1 max-h-32 min-h-[44px] resize-none bg-transparent border-none focus:ring-0 px-2 py-2 text-sm text-slate-900 placeholder:text-slate-400"
            rows={1}
          />
          <button 
            type="submit"
            disabled={!inputValue.trim() || isLoading}
            className="p-2 mb-1 rounded-xl bg-[#0052cc] text-white hover:bg-[#0040a2] disabled:opacity-50 disabled:bg-slate-200 disabled:text-slate-400 transition-all shadow-[0_4px_12px_rgba(0,82,204,0.2)] disabled:shadow-none"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
      </div>
    </div>
  );
}
