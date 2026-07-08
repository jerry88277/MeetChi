"use client";

import { useEffect } from "react";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";

/**
 * 2026-07-08：全域 API token 佈線。
 *
 * `api` 是 module 級 singleton；先前只有 dashboard/page.tsx 呼叫 setToken，
 * 導致直接進入 deep-link 詳情頁（重整/分享連結）時 token 為 null。
 * 一旦後端啟用 AUTH_REQUIRED=true，這些頁面的 API 呼叫會全部 401。
 *
 * 本元件掛在 dashboard layout，涵蓋所有 /dashboard/* 路由，於 session 就緒時
 * 同步 idToken 到 api client，確保任何進入點都攜帶有效憑證。
 */
export function ApiTokenSync() {
    const { data: session, status } = useSession();

    useEffect(() => {
        if (status === "authenticated" && session?.idToken) {
            api.setToken(session.idToken);
        } else if (status === "unauthenticated") {
            api.setToken(null);
        }
    }, [status, session?.idToken]);

    return null;
}
