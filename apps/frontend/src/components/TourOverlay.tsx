"use client";
import React, { useEffect, useState, useCallback } from "react";
import { X, ChevronRight, ChevronLeft, Map } from "lucide-react";
import { TOUR_STORAGE_KEY } from "@/lib/config";

interface TourStep {
  target: string | null;
  title: string;
  description: string;
  position: 'bottom' | 'top' | 'right' | 'center';
}

const STEPS: TourStep[] = [
  {
    target: null,
    title: "歡迎使用 MeetChi！",
    description: "讓我帶您快速認識系統的核心功能，只需 1 分鐘。",
    position: 'center',
  },
  {
    target: "meetings-grid",
    title: "會議記錄列表",
    description: "這裡集中管理所有的會議記錄。AI 會自動整理摘要、決策、待辦事項與風險。點擊任一卡片可查看完整內容。",
    position: 'top',
  },
  {
    target: "upload-cta",
    title: "上傳會議錄音",
    description: "點擊上傳錄音檔（.m4a / .mp3 / .wav），AI 將在幾分鐘內完成轉錄與摘要。",
    position: 'bottom',
  },
  {
    target: "nav-rag",
    title: "跨會議知識庫",
    description: "跨所有會議進行智慧查詢，找出多場討論的共識、分歧與尚未解決的事項。",
    position: 'right',
  },
  {
    target: "feedback-btn",
    title: "回報問題",
    description: "使用中遇到問題或有建議，歡迎隨時回報，我們會持續改善系統。",
    position: 'top',
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

  const complete = () => {
    localStorage.setItem(TOUR_STORAGE_KEY, '1');
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
          className="absolute rounded-xl transition-all duration-300 pointer-events-none"
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
            onClick={complete}
            className="text-muted-foreground hover:text-foreground p-1 rounded transition-colors"
            aria-label="關閉導覽"
          >
            <X size={14} />
          </button>
        </div>

        <h3 className="font-bold text-foreground text-base mb-1.5">{current.title}</h3>
        <p className="text-sm text-muted-foreground leading-relaxed mb-4">{current.description}</p>

        <div className="flex items-center justify-between gap-2">
          {!isFirst ? (
            <button
              onClick={() => setStep((s) => s - 1)}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronLeft size={14} /> 上一步
            </button>
          ) : (
            <button onClick={complete} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
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
      className="flex items-center gap-1.5 text-xs text-white/30 hover:text-white/60 transition-colors"
      title="重新播放功能導覽"
    >
      <Map size={12} />
      <span>功能導覽</span>
    </button>
  );
}
