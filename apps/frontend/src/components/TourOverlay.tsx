"use client";
import React, { useEffect, useState, useCallback } from "react";
import { X, ChevronRight, ChevronLeft, Map } from "lucide-react";
import { TOUR_STORAGE_KEY, TOUR_DISMISSED_KEY } from "@/lib/config";

interface TourStep {
  target: string | null;
  title: string;
  description: string;
  position: 'bottom' | 'top' | 'right' | 'center';
  // CS-12：spotlight 目標不存在時的替代說明（例如新使用者尚無會議卡片）
  fallbackHint?: string;
}

const STEPS: TourStep[] = [
  {
    target: null,
    title: "歡迎使用 MeetChi！",
    description: "簡單說，MeetChi 會把開會的錄音變成文字，再自動幫你整理出重點、要做的事和決定。只要 1 分鐘，帶你看看怎麼用。",
    position: 'center',
  },
  {
    target: "meetings-grid",
    title: "你的會議都在這裡",
    description: "每上傳一場會議錄音，這裡就會多一張卡片。AI 會幫你整理成「摘要、決定了什麼、待辦事項、要注意的風險」。點卡片就能看完整內容。",
    position: 'top',
    fallbackHint: "會議卡片會出現在主畫面中央。你現在還沒有會議，先上傳一場就會看到。",
  },
  {
    target: "upload-cta",
    title: "從這裡上傳錄音",
    description: "點這顆按鈕，選一個錄音檔（手機或錄音筆常見的 .m4a / .mp3 / .wav 都可以），AI 幾分鐘內就會把內容整理好。",
    position: 'bottom',
    fallbackHint: "「上傳音檔」按鈕在主畫面右上角。",
  },
  {
    target: "nav-rag",
    title: "ChiMemo：一次問所有會議",
    description: "有很多場會議後，可以在這裡直接用問的，例如「上週決定的預算是多少？」，它會跨所有會議幫你找答案。",
    position: 'right',
    fallbackHint: "「ChiMemo」在左側選單的「工作區」分組。",
  },
  {
    target: "feedback-btn",
    title: "遇到問題就回報",
    description: "使用中卡住或有想法，點這裡告訴我們，會持續改善。",
    position: 'top',
    fallbackHint: "「回報問題」在左側選單下方。",
  },
];

interface TourOverlayProps {
  open: boolean;
  onClose: () => void;
}

export function TourOverlay({ open, onClose }: TourOverlayProps) {
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  const updateRect = useCallback(() => {
    const target = STEPS[step]?.target;
    if (!target) {
      setRect(null);
      return;
    }
    const el = document.querySelector(`[data-tour="${target}"]`);
    if (el) setRect(el.getBoundingClientRect());
    else setRect(null);
  }, [step]);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(updateRect);
    window.addEventListener('resize', updateRect);
    window.addEventListener('scroll', updateRect, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', updateRect);
      window.removeEventListener('scroll', updateRect, true);
    };
  }, [open, updateRect]);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => setStep(0));
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  // Keyboard navigation for tour overlay
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        dismiss();
      } else if (e.key === 'Enter' || e.key === 'ArrowRight') {
        e.preventDefault();
        if (step >= STEPS.length - 1) complete();
        else setStep(s => s + 1);
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        if (step > 0) setStep(s => s - 1);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, step]);

  // CS-1：真正「看完」才寫永久完成旗標——之後不再自動開、零會議首頁也不再顯示常駐入口。
  const complete = () => {
    localStorage.setItem(TOUR_STORAGE_KEY, '1');
    localStorage.removeItem(TOUR_DISMISSED_KEY);
    onClose();
  };

  // CS-1：反射性「跳過 / 關閉 / Esc」只寫本次略過旗標（避免每次重載又跳出來），
  // 但不算完成——零會議首頁仍常駐「觀看導覽」入口，給使用者二次機會。
  const dismiss = () => {
    localStorage.setItem(TOUR_DISMISSED_KEY, '1');
    onClose();
  };

  if (!open) return null;

  const current = STEPS[step];
  const isFirst = step === 0;
  const isLast = step === STEPS.length - 1;
  const PADDING = 12;
  const TOOLTIP_W = 320;

  let tooltipStyle: React.CSSProperties = {
    position: 'fixed',
    width: TOOLTIP_W,
    zIndex: 10001,
  };

  if (rect && current.position !== 'center') {
    const safeLeft = (x: number) => Math.max(8, Math.min(x, window.innerWidth - TOOLTIP_W - 8));
    if (current.position === 'bottom') {
      tooltipStyle = { ...tooltipStyle, top: rect.bottom + PADDING, left: safeLeft(rect.left + rect.width / 2 - TOOLTIP_W / 2) };
    } else if (current.position === 'top') {
      tooltipStyle = { ...tooltipStyle, bottom: window.innerHeight - rect.top + PADDING, left: safeLeft(rect.left + rect.width / 2 - TOOLTIP_W / 2) };
    } else if (current.position === 'right') {
      tooltipStyle = { ...tooltipStyle, top: Math.max(8, rect.top + rect.height / 2 - 90), left: rect.right + PADDING };
    }
  } else {
    tooltipStyle = { ...tooltipStyle, top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: TOOLTIP_W };
  }

  return (
    <div className="fixed inset-0" style={{ zIndex: 10000 }}>
      <div
        className="absolute inset-0"
        style={{ background: 'rgba(0,0,0,0.65)' }}
        onClick={(e) => e.stopPropagation()}
      />

      {/* spotlight cutout */}
      {rect && current.position !== 'center' && (
        <div
          className="absolute rounded-xl transition-[inset,width,height] duration-300 pointer-events-none"
          style={{
            top: rect.top - PADDING,
            left: rect.left - PADDING,
            width: rect.width + PADDING * 2,
            height: rect.height + PADDING * 2,
            boxShadow: '0 0 0 9999px rgba(0,0,0,0.65)',
            background: 'transparent',
            border: '2px solid rgba(255,255,255,0.5)',
            zIndex: 10001,
          }}
        />
      )}

      <div
        className="bg-white rounded-2xl shadow-2xl p-5 pointer-events-auto"
        style={tooltipStyle}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex gap-1.5">
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={`w-2 h-2 rounded-full transition-colors ${i === step ? 'bg-brand-cta' : 'bg-muted'}`}
              />
            ))}
          </div>
          <button
            onClick={dismiss}
            className="text-muted-foreground hover:text-foreground p-1 rounded transition-colors"
            aria-label="關閉導覽"
          >
            <X size={14} />
          </button>
        </div>

        <h3 className="font-bold text-foreground text-base mb-1.5">{current.title}</h3>
        <p className="text-sm text-muted-foreground leading-relaxed mb-4">{current.description}</p>

        {/* CS-12：spotlight 目標不存在時（例如新使用者尚無會議卡片），顯示替代位置說明 */}
        {current.target && !rect && current.fallbackHint && (
          <p className="text-xs text-brand-cta bg-brand-cta/10 rounded-lg px-3 py-2 mb-4">
            💡 {current.fallbackHint}
          </p>
        )}

        <div className="flex items-center justify-between gap-2">
          {!isFirst ? (
            <button
              onClick={() => setStep((s) => s - 1)}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronLeft size={14} /> 上一步
            </button>
          ) : (
            <button onClick={dismiss} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              跳過導覽
            </button>
          )}
          {isLast ? (
            <button
              onClick={complete}
              className="flex items-center gap-1.5 px-4 py-2 bg-brand-cta text-white rounded-xl text-sm font-medium hover:bg-brand-cta/90 transition-colors"
            >
              完成導覽 🎉
            </button>
          ) : (
            <button
              onClick={() => setStep((s) => s + 1)}
              className="flex items-center gap-1.5 px-4 py-2 bg-brand-cta text-white rounded-xl text-sm font-medium hover:bg-brand-cta/90 transition-colors"
            >
              下一步 <ChevronRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function RestartTourButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-2.5 py-1.5 text-sm font-bold text-white/70 hover:text-white bg-white/10 hover:bg-white/15 border border-white/20 rounded-lg transition-colors"
      title="重新播放功能導覽"
    >
      <Map size={14} />
      <span>功能導覽</span>
    </button>
  );
}
