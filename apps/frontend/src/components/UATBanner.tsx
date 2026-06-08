"use client";
import { useState } from "react";
import { X, FlaskConical } from "lucide-react";
import { UAT_MODE } from "@/lib/config";

export function UATBanner() {
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === "undefined" || !UAT_MODE) return true;
    return sessionStorage.getItem('meetchi_uat_banner_dismissed') === '1';
  });

  if (!UAT_MODE || dismissed) return null;

  return (
    <div className="sticky top-0 z-50 flex items-center gap-3 px-4 py-2.5 bg-brand-chimei-orange/10 border-b border-brand-chimei-orange/30 text-brand-chimei-orange text-sm">
      <FlaskConical size={15} className="shrink-0" />
      <p className="flex-1">
        <span className="font-bold">UAT 測試環境</span>
        ・本系統目前為用戶驗收測試階段，資料可能隨時重置，請勿輸入機密或正式業務內容。
      </p>
      <button
        onClick={() => {
          sessionStorage.setItem('meetchi_uat_banner_dismissed', '1');
          setDismissed(true);
        }}
        className="p-1 rounded hover:bg-brand-chimei-orange/20 transition-colors shrink-0"
        aria-label="關閉通知"
      >
        <X size={14} />
      </button>
    </div>
  );
}
