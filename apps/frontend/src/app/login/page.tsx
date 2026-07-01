"use client"

import { signIn } from "next-auth/react"
import { useSearchParams } from "next/navigation"
import { Suspense, useState } from "react"
import { AlertCircle, Loader2, TestTube2 } from "lucide-react"

const MS_AUTH_ENABLED = process.env.NEXT_PUBLIC_MS_AUTH_ENABLED === "true"
// UAT_ENABLED: hidden from main flow — only visible via ?uat=1 query param.
// Prevents normal employees from seeing the test path; testers/admins still accessible.
const UAT_ENABLED = true

const ERROR_MESSAGES: Record<string, string> = {
    OAuthSignin: "啟動登入時發生錯誤，請稍後再試。",
    OAuthCallback: "OAuth 回呼處理失敗，請再試一次。",
    OAuthCreateAccount: "建立帳號時發生錯誤。",
    EmailCreateAccount: "建立 Email 帳號失敗。",
    Callback: "登入回呼失敗，請重新登入。",
    OAuthAccountNotLinked: "此 Email 已有其他登入方式，請改用原本的登入方式。",
    EmailSignin: "Email 登入連結寄送失敗。",
    CredentialsSignin: "帳號或密碼錯誤，請確認測試帳號資訊。",
    SessionRequired: "請先登入再繼續。",
    Default: "登入失敗，請稍後再試。",
};

type SigningInProvider = "google" | "microsoft" | "credentials" | null

function LoginContent() {
    const searchParams = useSearchParams()
    const callbackUrl = searchParams.get("callbackUrl") || "/dashboard"
    const errorParam = searchParams.get("error")
    const errorMessage = errorParam ? (ERROR_MESSAGES[errorParam] ?? ERROR_MESSAGES.Default) : null
    const [signingIn, setSigningIn] = useState<SigningInProvider>(null)
    const [uatEmail, setUatEmail] = useState("")
    const [uatPassword, setUatPassword] = useState("")
    // UAT form only visible when ?uat=1 is in the URL — keeps main path clean for real users
    const showUAT = UAT_ENABLED && searchParams.get("uat") === "1"

    const handleSignIn = async (provider: "google" | "microsoft") => {
        if (signingIn) return
        setSigningIn(provider)
        try {
            await signIn(provider === "microsoft" ? "microsoft-entra-id" : "google", { callbackUrl })
        } catch (e) {
            console.error("signIn error:", e)
            setSigningIn(null)
        }
    }

    const handleUATSignIn = async (e: React.FormEvent) => {
        e.preventDefault()
        if (signingIn || !uatEmail || !uatPassword) return
        setSigningIn("credentials")
        try {
            const result = await signIn("credentials", {
                email: uatEmail,
                password: uatPassword,
                callbackUrl,
                redirect: false,
            })
            if (result?.error) {
                setSigningIn(null)
            } else if (result?.url) {
                window.location.href = result.url
            }
        } catch (e) {
            console.error("UAT signIn error:", e)
            setSigningIn(null)
        }
    }

    return (
        <div className="min-h-screen bg-surface flex items-center justify-center p-6">
            {/* DDG §1「永續×人文」: 底色改 surface (#FAFAF8) 減輕主色佔比；
                品牌識別集中在 logo card（brand-navy 底），不再全版深色漸層。
                參考 Granola calm productivity 低彩基調。*/}
            <div className="w-full max-w-md">
                {/* Logo — brand-navy 集中於此，維持品牌識別但不佔滿畫面 */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 bg-brand-navy rounded-2xl mb-4 shadow-lg">
                        <span className="text-3xl font-bold text-white">M</span>
                    </div>
                    <h1 className="text-3xl font-bold text-foreground">MeetChi</h1>
                    <p className="text-muted-foreground mt-2">把每場討論整理成下一步</p>
                    {/* CS-3：冷啟動者一眼看懂用途的白話說明 */}
                    <p className="text-sm text-muted-foreground/80 mt-1">
                        會議錄音 → AI 自動轉成文字，並整理出摘要、決策與待辦
                    </p>
                </div>

                {/* Login Card */}
                <div className="bg-card rounded-2xl p-8 border border-border shadow-lg">
                    <h2 className="text-xl font-semibold text-foreground text-center mb-6">
                        使用奇美帳戶繼續
                    </h2>

                    {errorMessage && (
                        <div role="alert" className="mb-5 bg-status-error/10 border border-status-error/30 rounded-xl p-3 flex items-start gap-2 text-sm">
                            <AlertCircle className="w-4 h-4 text-status-error flex-shrink-0 mt-0.5" />
                            <span className="text-foreground">{errorMessage}</span>
                        </div>
                    )}

                    <div className="flex flex-col gap-3">
                        {/* Microsoft SSO — 主要入口（需設定 NEXT_PUBLIC_MS_AUTH_ENABLED=true） */}
                        {MS_AUTH_ENABLED && (
                            <button
                                type="button"
                                onClick={() => handleSignIn("microsoft")}
                                disabled={signingIn !== null}
                                aria-label="使用奇美帳戶（Microsoft）登入"
                                className="w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl font-medium transition-all duration-200 shadow-sm hover:shadow-md disabled:opacity-60 disabled:cursor-not-allowed text-white"
                                style={{ backgroundColor: signingIn === "microsoft" ? "#005a9e" : "#0078D4" }}
                            >
                                {signingIn === "microsoft" ? (
                                    <>
                                        <Loader2 className="w-5 h-5 animate-spin" />
                                        正在前往 Microsoft 登入...
                                    </>
                                ) : (
                                    <>
                                        {/* Microsoft logo */}
                                        <svg className="w-5 h-5" viewBox="0 0 23 23" aria-hidden="true">
                                            <path fill="#f3f3f3" d="M0 0h23v23H0z" />
                                            <path fill="#f35325" d="M1 1h10v10H1z" />
                                            <path fill="#81bc06" d="M12 1h10v10H12z" />
                                            <path fill="#05a6f0" d="M1 12h10v10H1z" />
                                            <path fill="#ffba08" d="M12 12h10v10H12z" />
                                        </svg>
                                        使用奇美帳戶（Microsoft）登入
                                    </>
                                )}
                            </button>
                        )}

                        {/* Google 登入 — 作為備用或非 MS 環境主入口 */}
                        <button
                            type="button"
                            onClick={() => handleSignIn("google")}
                            disabled={signingIn !== null}
                            aria-label="使用 Google 帳戶登入"
                            className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-muted rounded-xl text-foreground font-medium hover:bg-border transition-all duration-200 shadow-sm hover:shadow-md disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                            {signingIn === "google" ? (
                                <>
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                    正在前往 Google 登入...
                                </>
                            ) : (
                                <>
                                    <svg className="w-5 h-5" viewBox="0 0 24 24" aria-hidden="true">
                                        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                                        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                                        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                                        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                                    </svg>
                                    使用 Google 帳戶登入
                                </>
                            )}
                        </button>
                    </div>

                    <p className="text-center text-muted-foreground text-sm mt-6">
                        僅供奇美集團內部同仁使用
                    </p>
                </div>

                {/* UAT 測試帳號登入 — 隱藏於主路徑，僅 ?uat=1 可見 */}
                {showUAT && (
                    <>
                        <div className="flex items-center gap-3 my-2">
                            <div className="flex-1 h-px bg-border" />
                            <span className="text-xs text-muted-foreground px-2">或使用測試帳號</span>
                            <div className="flex-1 h-px bg-border" />
                        </div>
                        <div className="bg-card rounded-2xl p-6 border border-border shadow-sm">
                            <div className="flex items-center gap-2 mb-4">
                                <TestTube2 size={14} className="text-muted-foreground" />
                                <span className="text-sm font-medium text-foreground">UAT 測試帳號</span>
                                <span className="ml-auto text-[10px] px-2 py-0.5 bg-muted text-muted-foreground rounded-full font-medium tracking-wide">
                                    測試專用
                                </span>
                            </div>
                            <form onSubmit={handleUATSignIn} className="space-y-3">
                                <input
                                    type="email"
                                    placeholder="測試 Email"
                                    value={uatEmail}
                                    onChange={(e) => setUatEmail(e.target.value)}
                                    required
                                    disabled={signingIn !== null}
                                    className="w-full px-4 py-3 bg-surface border border-border rounded-xl text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-brand-cta disabled:opacity-60"
                                />
                                <input
                                    type="password"
                                    placeholder="密碼"
                                    value={uatPassword}
                                    onChange={(e) => setUatPassword(e.target.value)}
                                    required
                                    disabled={signingIn !== null}
                                    className="w-full px-4 py-3 bg-surface border border-border rounded-xl text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-brand-cta disabled:opacity-60"
                                />
                                <button
                                    type="submit"
                                    disabled={signingIn !== null || !uatEmail || !uatPassword}
                                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-brand-cta text-white rounded-xl text-sm font-medium hover:bg-brand-cta/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {signingIn === "credentials" ? (
                                        <><Loader2 size={16} className="animate-spin" />登入中...</>
                                    ) : (
                                        "以測試帳號登入"
                                    )}
                                </button>
                            </form>
                        </div>
                    </>
                )}

                {/* Footer */}
                <p className="text-center text-muted-foreground text-sm mt-8">
                    © 2026 MeetChi. All rights reserved.
                </p>
            </div>
        </div>
    )
}

export default function LoginPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-brand-navy flex items-center justify-center">
                <Loader2 className="w-8 h-8 text-brand-cta animate-spin" />
            </div>
        }>
            <LoginContent />
        </Suspense>
    )
}
