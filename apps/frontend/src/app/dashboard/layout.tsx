/**
 * Dashboard layout — 不再無條件包 <SecurityWrapper>。
 *
 * 2026-05-12 修（feedback 4504f2e3）：
 *   原本整個 /dashboard/* 都被 SecurityWrapper 包，導致 select-none /
 *   contextmenu 攔截 / Ctrl+C 攔截全域生效，**一般會議也無法反白複製**。
 *   使用者回報：「現在所有的一般會議或是介面訊息無法反白或是複製」。
 *
 *   改動：layout 不包，改由 DetailView 內讀 meeting.is_confidential
 *   條件式套用。一般會議使用者可正常複製，機密會議才啟用保護。
 */

interface DashboardLayoutProps {
  children: React.ReactNode;
}

import { ApiTokenSync } from "@/components/ApiTokenSync";

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  // Per-meeting confidential 保護移到 DetailView。
  // 2026-07-08：全域佈線 API token（涵蓋 deep-link 詳情頁），供 AUTH_REQUIRED=true 後使用。
  return (
    <>
      <ApiTokenSync />
      {children}
    </>
  );
}
