"use client"

import { SessionProvider } from "next-auth/react"
import { ThemeProvider } from "next-themes"
import { Toaster } from "sonner"

export function Providers({ children }: { children: React.ReactNode }) {
    return (
        <SessionProvider>
            <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
                {children}
                {/* sonner — 統一 toast 出口；取代手寫 inline banner */}
                <Toaster
                    position="top-right"
                    richColors
                    closeButton
                    toastOptions={{
                        duration: 5000,
                        classNames: {
                            toast: "rounded-xl shadow-lg",
                        },
                    }}
                />
            </ThemeProvider>
        </SessionProvider>
    )
}
