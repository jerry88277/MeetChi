/**
 * Feedback metadata helpers (PR24 / Sprint 2d frontend).
 *
 * 自動收集瀏覽器環境資訊，讓使用者送 feedback 時不必手動填。
 * 也提供 console.error / console.warn 緩衝，最近 N 筆隨 feedback 一起送。
 */

const SESSION_ID_KEY = "meetchi-session-id";
const CONSOLE_BUFFER_LIMIT = 20;

export interface BufferedConsoleEntry {
    level: "error" | "warn";
    message: string;
    timestamp: string;
    stack?: string;
}

let consoleBuffer: BufferedConsoleEntry[] = [];
let consoleHookInstalled = false;

export function installConsoleErrorHook() {
    if (typeof window === "undefined") return;
    if (consoleHookInstalled) return;
    consoleHookInstalled = true;

    const origError = console.error.bind(console);
    const origWarn = console.warn.bind(console);

    const push = (level: "error" | "warn", args: unknown[]) => {
        try {
            const msgParts = args.map((a) => {
                if (a instanceof Error) return `${a.message}\n${a.stack ?? ""}`;
                if (typeof a === "object") {
                    try {
                        return JSON.stringify(a);
                    } catch {
                        return String(a);
                    }
                }
                return String(a);
            });
            const stackArg = args.find((a): a is Error => a instanceof Error);
            consoleBuffer.push({
                level,
                message: msgParts.join(" "),
                timestamp: new Date().toISOString(),
                stack: stackArg?.stack,
            });
            if (consoleBuffer.length > CONSOLE_BUFFER_LIMIT) {
                consoleBuffer = consoleBuffer.slice(-CONSOLE_BUFFER_LIMIT);
            }
        } catch {
            // never let buffering break logging itself
        }
    };

    console.error = (...args: unknown[]) => {
        push("error", args);
        origError(...args);
    };
    console.warn = (...args: unknown[]) => {
        push("warn", args);
        origWarn(...args);
    };

    window.addEventListener("error", (e) => {
        consoleBuffer.push({
            level: "error",
            message: e.message,
            timestamp: new Date().toISOString(),
            stack: e.error?.stack,
        });
        if (consoleBuffer.length > CONSOLE_BUFFER_LIMIT) {
            consoleBuffer = consoleBuffer.slice(-CONSOLE_BUFFER_LIMIT);
        }
    });

    window.addEventListener("unhandledrejection", (e) => {
        const reason = (e as PromiseRejectionEvent).reason;
        consoleBuffer.push({
            level: "error",
            message: `UnhandledPromiseRejection: ${reason instanceof Error ? reason.message : String(reason)}`,
            timestamp: new Date().toISOString(),
            stack: reason instanceof Error ? reason.stack : undefined,
        });
        if (consoleBuffer.length > CONSOLE_BUFFER_LIMIT) {
            consoleBuffer = consoleBuffer.slice(-CONSOLE_BUFFER_LIMIT);
        }
    });
}

export function getRecentConsoleErrors(): BufferedConsoleEntry[] {
    return [...consoleBuffer];
}

export function getOrCreateSessionId(): string {
    if (typeof window === "undefined") return "";
    try {
        let sid = sessionStorage.getItem(SESSION_ID_KEY);
        if (!sid) {
            sid = `sess_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
            sessionStorage.setItem(SESSION_ID_KEY, sid);
        }
        return sid;
    } catch {
        return "";
    }
}

export function getBrowserInfo(): string {
    if (typeof window === "undefined" || typeof navigator === "undefined") return "";
    // 截短到 500 char (backend 限制)
    return (navigator.userAgent || "unknown").slice(0, 500);
}

export function getPageUrl(): string {
    if (typeof window === "undefined") return "";
    return window.location.href.slice(0, 500);
}

export function getFrontendVersion(): string {
    return process.env.NEXT_PUBLIC_APP_VERSION || "dev";
}

export interface CollectedMetadata {
    page_url: string;
    browser_info: string;
    session_id: string;
    frontend_version: string;
    console_errors: Array<Record<string, unknown>>;
}

/** 一次拿齊所有 auto metadata，前端送 feedback 時 spread 進 payload。 */
export function collectFeedbackMetadata(): CollectedMetadata {
    return {
        page_url: getPageUrl(),
        browser_info: getBrowserInfo(),
        session_id: getOrCreateSessionId(),
        frontend_version: getFrontendVersion(),
        console_errors: getRecentConsoleErrors().map((e) => ({
            level: e.level,
            message: e.message,
            timestamp: e.timestamp,
            ...(e.stack ? { stack: e.stack } : {}),
        })),
    };
}
