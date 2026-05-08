import type { Metadata } from "next";
import { Inter, Noto_Sans_TC } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

// PR20 (Sprint 2a): 思源黑體繁中 — Adobe + Google 開源，與「思源黑體 TW」
// 同字符表（Noto Sans TC = Source Han Sans TC 國際版）。subset 限定常用權重，
// 避免 bundle 過大。display=swap 讓 fallback 字體先顯示再換正式字。
const notoSansTC = Noto_Sans_TC({
  subsets: ["latin"],
  variable: "--font-noto-sans-tc",
  weight: ["400", "500", "600", "700"],
  display: "swap",
  preload: false,
});

export const metadata: Metadata = {
  title: "MeetChi - AI 會議助理",
  description: "智慧會議記錄與分析平台，自動生成摘要、待辦事項和逐字稿",
  keywords: ["會議記錄", "語音轉文字", "AI", "會議摘要", "MeetChi"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-TW">
      <body className={`${inter.variable} ${notoSansTC.variable} font-sans antialiased`}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
