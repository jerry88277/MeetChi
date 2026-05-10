"use client"

import { signIn } from "next-auth/react"
import { useSearchParams } from "next/navigation"
import { Suspense, useState } from "react"
import { AlertCircle, Loader2 } from "lucide-react"

const ERROR_MESSAGES: Record<string, string> = {
    OAuthSignin: "啟動 Google 登入時發生錯誤，請稍後再試。",
    OAuthCallback: "Google 回呼處理失敗，請再試一次。",
    OAuthCreateAccount: "建立帳號時發生錯誤。",
    EmailCreateAccount: "建立 Email 帳號失敗。",
    Callback: "登入回呼失敗，請重新登入。",
    OAuthAccountNotLinked: "此 Email 已有其他登入方式，請改用原本的登入方式。",
    EmailSignin: "Email 登入連結寄送失敗。",
    CredentialsSignin: "帳號或密碼錯誤。",
    SessionRequired: "請先登入再繼續。",
    Default: "登入失敗，請稍後再試。",
};

function LoginContent() {
    const searchParams = useSearchParams()
    const callbackUrl = searchParams.get("callbackUrl") || "/dashboard"
    // P1 a11y/UX：將 NextAuth ?error=... 顯示給 user，不要靜默
    const errorParam = searchParams.get("error")
    const errorMessage = errorParam ? (ERROR_MESSAGES[errorParam] ?? ERROR_MESSAGES.Default) : null
    const [isSigningIn, setIsSigningIn] = useState(false)

    const handleSignIn = async () => {
        if (isSigningIn) return  // 避免雙開 popup
        setIsSigningIn(true)
        try {
            await signIn("google", { callbackUrl })
        } catch (e) {
            console.error("signIn error:", e)
            setIsSigningIn(false)
        }
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-brand-navy via-brand-cta to-brand-navy flex items-center justify-center p-6">
            <div className="w-full max-w-md">
                {/* Logo */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 bg-brand-cta rounded-2xl mb-4 shadow-lg">
                        <span className="text-3xl font-bold text-white">M</span>
                    </div>
                    <h1 className="text-3xl font-bold text-white">MeetChi</h1>
                    <p className="text-white/60 mt-2">AI 會議助理</p>
                </div>

                {/* Login Card */}
                <div className="bg-card/10 backdrop-blur-xl rounded-2xl p-8 border border-white/20 shadow-2xl">
                    <h2 className="text-xl font-semibold text-white text-center mb-6">
                        登入您的帳戶
                    </h2>

                    {errorMessage && (
                        <div role="alert" className="mb-5 bg-status-error/15 border border-status-error/30 rounded-xl p-3 flex items-start gap-2 text-sm">
                            <AlertCircle className="w-4 h-4 text-status-error flex-shrink-0 mt-0.5" />
                            <span className="text-white/90">{errorMessage}</span>
                        </div>
                    )}

                    <button
                        type="button"
                        onClick={handleSignIn}
                        disabled={isSigningIn}
                        aria-label="使用 Google 帳戶登入"
                        className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-card rounded-xl text-foreground font-medium hover:bg-muted transition-all duration-200 shadow-lg hover:shadow-xl disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                        {isSigningIn ? (
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

                    <p className="text-center text-white/60 text-sm mt-6">
                        登入即表示您同意我們的服務條款與隱私政策
                    </p>
                </div>

                {/* Footer */}
                <p className="text-center text-white/50 text-sm mt-8">
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
