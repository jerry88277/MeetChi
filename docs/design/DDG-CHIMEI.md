# MeetChi 設計系統 — DDG 奇美 (ChiMei) 視覺規範

> **版本**：1.0｜**最後更新**：2026-05-10｜**主分支實作**：[apps/frontend/src/app/globals.css](../../apps/frontend/src/app/globals.css)
>
> 本文記錄 MeetChi 前端設計系統「DDG 奇美」的設計哲學、token 規格、使用準則、反模式。
> 本文是**唯一真相來源**（single source of truth）；任何 PR 修改 token 時必須同步更新本文，否則 review reject。

---

## 1. 設計哲學

MeetChi 是企業會議 AI 助理，目標是**讓會議結論在 30 秒內被吸收**。設計概念承接奇美實業集團 (ChiMei) 的 DDG (Digital Design Guidelines)，核心三軸：

| 軸 | 來源 | 在 MeetChi 的展現 |
|---|---|---|
| **工業** | 奇美材料工業背景 | 結構化卡片、明確邊界、tabular numerals、grid-aligned 排版 |
| **人文** | 奇美博物館/文化品牌延伸 | 暖橙/暖黃補色、思源黑體、可閱讀行長 (max-w-3xl) |
| **永續** | DDG 2024 重塑主軸 | 微暖中性灰白底 (#FAFAF8 取代純冷灰)、避免高飽和螢光色 |

**設計氣質目標**: calm productivity（借鑑 Granola 對標品）。會議產出本身已資訊密集，UI 不再加負擔——預設低彩、層級清楚、動效克制。

---

## 2. Q1–Q8 設計訪談決策表

PR20 (Sprint 2a, commit `7b22cf0`) 與使用者進行 8 題結構化訪談確認設計方向。**所有後續 design token 與佈局決策都必須對齊這 8 條**。

| # | 主題 | 選定方案 | 落地位置 |
|---|---|---|---|
| **Q1** | 整體調性 | **c. 工業×人文（DDG 奇美承接）** | brand-cta 深藍主色 + 暖橙暖黃補色 |
| **Q2** | 配色系統 | **b. DDG 8 色活力** | 8 個 brand-* token；單一深藍延伸 |
| **Q3** | 螢光青去留 | **b. 移除 #5BFAE6** | brand-highlight alias 改指 brand-green；dark mode ring 改 brand-green |
| **Q4** | 字體 | **c. 思源黑體** | Inter (拉丁) + Noto Sans TC (中文) + 5 段 fallback chain |
| **Q5** | 資訊密度 | **c. 折衷密度** | radius-lg 0.75rem (中圓角)、padding-base 1.5rem、leading-relaxed |
| **Q6** | 動效強度 | **b. 微動效 200-300ms** | `--duration-base 200ms` `--ease-standard cubic-bezier(.2,0,0,1)`；禁止 hover scale > 1.02 |
| **Q7** | 詳情頁 IA | **c. 單欄垂直** | DetailView 5 section 由大到小：TL;DR → 結論三欄 → 完整摘要 → 引言 → 折疊逐字稿 |
| **Q8** | 對標品 | **Granola** (calm productivity) | 真實截圖 hero、單欄 reading layout、低彩配色、動效克制 |

> 訪談原始 prompt 與選項見 [附錄 A](#附錄-a-q1q8-訪談 prompt 紀錄)。

---

## 3. Token 規格

### 3.1 品牌色 (Brand Colors) — 8 色活力

| Token | HEX | 語意角色 | 使用時機 |
|---|---|---|---|
| `brand-navy` | `#041E42` | 既有奇美深藍 | Sidebar 背景；保留向後相容 |
| `brand-cta` | `#2D428B` | **主 CTA 深藍** | 主按鈕、連結、focus ring、品牌識別 |
| `brand-orange` | `#FF6B35` | 暖橙：能量／行動 | 待辦 (action items)、上傳 hover、銷售類模板 |
| `brand-green` | `#06D6A0` | 亮綠：永續／清新 | success state、聊天確認、ring (dark) |
| `brand-forest` | `#1E5128` | 深綠：材料／自然 | 環境/永續類分類；備用 |
| `brand-amber` | `#F2C14E` | 暖黃：溫度／人文 | 講者 dot、警告非錯誤等級的提示 |
| `brand-violet` | `#4D5CB7` | 靛紫：科技延伸 | 模板/AI 生成相關（取代舊 #7C3AED 高飽和紫） |
| `brand-coral` | `#C5283D` | 莓紅：重要／警示 | 主管簡報重點、不到 error 等級的高度提醒 |
| `brand-azure` | `#4A90E2` | 海藍：流動／資訊 | 研發類分類、info 資訊提示 |

**Alias（向後相容，逐步淘汰）**：

| Alias | 實際指向 | 為何保留 |
|---|---|---|
| `brand-accent` | `brand-violet` | 舊代碼 hardcoded `bg-brand-accent`，未一次遷移 |
| `brand-highlight` | `brand-green` | 取代被移除的 `#5BFAE6` 螢光青（Q3=b） |

### 3.2 狀態色 (Status Colors)

| Token | HEX | 語意 |
|---|---|---|
| `status-success` | `#48B070` | 完成、成功、健康 |
| `status-warning` | `#E4831A` | 處理中、需注意 |
| `status-error` | `#D2343D` | 失敗、錯誤、刪除確認 |

> ⚠️ **嚴禁** 使用 Tailwind 預設狀態色（如 `text-red-500`、`bg-green-100`）— 不在 DDG 色票中。

### 3.3 語意色 (Semantic Colors)

雙模式自動切換。永遠用 semantic token，不要 hardcoded `bg-white` / `bg-slate-*`。

| Token | Light | Dark | 用途 |
|---|---|---|---|
| `background` | `#ffffff` | `#0f172a` | 頁面最底層 |
| `foreground` | `#0f172a` | `#f1f5f9` | 主要文字 |
| `surface` | `#FAFAF8` | `#1e293b` | 大區塊背景（detail 頁主滾動容器） |
| `card` | `#ffffff` | `#1e293b` | 卡片、modal、彈窗 |
| `muted` | `#f1f5f9` | `#334155` | 次要區塊（footer、次要按鈕） |
| `muted-foreground` | `#64748b` | `#94a3b8` | 次要文字（時間戳、標籤） |
| `border` | `#e2e8f0` | `#334155` | 所有邊框 |
| `ring` | `#2D428B` | `#06D6A0` | focus ring（dark 用 brand-green 比深藍柔和） |

> **微暖中性灰白**：`surface` 用 `#FAFAF8` 而不是 Tailwind 預設冷灰 `#f8fafc`，呼應「永續＋人文」基調。

### 3.4 字體 (Typography)

```css
--font-sans:
  var(--font-inter),                              /* 拉丁字 */
  var(--font-noto-sans-tc),                       /* 思源黑體（next/font self-host） */
  "Source Han Sans TC", "Noto Sans CJK TC",       /* 系統字 */
  "PingFang TC", "Microsoft JhengHei", "微軟正黑體",
  ui-sans-serif, system-ui, sans-serif;
```

- **Inter** 用於拉丁字與 tabular numerals（`tabular-nums` class）
- **思源黑體 (Noto Sans TC)** 用於中文，Adobe + Google 開源同字符表
- 關鍵：兩者都用 `var(--font-*)` 由 `next/font` self-host，**不依賴 fonts.googleapis.com runtime**（企業內網/防火牆友善）

### 3.5 動效 (Motion)

| Token | 值 | 用途 |
|---|---|---|
| `--duration-fast` | `100ms` | 按鈕按下回饋（active:scale-[0.99]） |
| `--duration-base` | `200ms` | 預設：hover、fade、color transition |
| `--duration-slow` | `300ms` | modal 淡入、drawer 滑入 |
| `--duration-slower` | `500ms` | 大型過場（罕用） |
| `--ease-standard` | `cubic-bezier(.2, 0, 0, 1)` | IBM Carbon 標準曲線，人因工程偏好 |
| `--ease-enter` | `cubic-bezier(0, 0, .2, 1)` | 元素進入時的減速曲線 |
| `--ease-exit` | `cubic-bezier(.4, 0, 1, 1)` | 元素退場時的加速曲線 |

> **動效紅線**（anti-AI-slop）：
> - 禁 hover scale > 1.02
> - 禁無意義的 bounce / spring 動效
> - 禁 spinner 以外的 `animation: spin`
> - 整頁 page transition 一律用 fade，不用 slide

### 3.6 圓角 (Radius)

| Token | 值 | 使用 |
|---|---|---|
| `--radius-sm` | `0.25rem` | chip、small badge |
| `--radius-md` | `0.5rem` | 按鈕、input |
| `--radius-lg` | `0.75rem` | 卡片、modal、區塊容器 |

> 維持中圓角不追求 brutalist 銳角；避免全圓 `rounded-full` 在卡片上。

---

## 4. 使用準則

### 4.1 何時用哪個 brand 色？

不是隨意挑顏色。Brand 色語意化對應：

| 情境 | 用 token |
|---|---|
| 主 CTA、連結、focus、表單 submit | `brand-cta` |
| 待辦事項 (action items)、上傳/錄音類動作 | `brand-orange` |
| 完成 / 成功 / 永續類 | `brand-green`（或 `status-success` for 純狀態） |
| 警告但非錯誤、講者 highlight | `brand-amber` |
| 模板分類 / AI 生成 | `brand-violet` |
| 高重要性提醒（不到 error） | `brand-coral` |
| 研發類分類 / info | `brand-azure` |
| 失敗 / 刪除確認 | `status-error` |

### 4.2 卡片結構標準

```tsx
<div className="bg-card border border-border rounded-xl p-6 shadow-sm">
  ...
</div>
```

- 永遠用 `bg-card`、不用 `bg-white`
- 永遠用 `border-border`、不用 `border-gray-200`
- shadow 用 Tailwind `shadow-sm` / `shadow-md`，不要堆 `shadow-2xl`
- padding 預設 `p-6`（24px），緊湊版 `p-4`，鬆散版 `p-8`

### 4.3 文字層級

```tsx
<h1 className="text-3xl font-bold text-foreground">         // 頁面標題
<h2 className="text-xl font-bold text-foreground">          // 區塊標題
<h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">  // section label
<p className="text-base text-foreground/85 leading-relaxed">  // 內文
<p className="text-xs text-muted-foreground">                // 時間戳/標籤
```

### 4.4 Reading layout

詳情頁類「閱讀為主」內容用 `max-w-3xl mx-auto`（Granola 借鑑）— 行長 60-80 字符範圍，最佳閱讀體驗。

更寬的螢幕（≥ 1920px）可用 `max-w-5xl` 但保留兩側留白；**不應**讓單欄滿版 stretch。

---

## 5. 反模式（Anti-patterns）

從 [2026-05-10 顏色 audit](../audits/2026-05-10-color-audit.md) 與 [user flow audit](../audits/2026-05-10-user-flow-audit.md) 整理出的紅線：

### 5.1 配色

| ❌ 反模式 | ✅ 正確做法 |
|---|---|
| `bg-[#0052cc]`、`bg-[#FF6B35]` 任意 hex | 用 `bg-brand-cta`、`bg-brand-orange` |
| `bg-white` 卡片 | `bg-card` |
| `dark:bg-slate-900` 手動覆寫 | 用 semantic token；dark mode 自動切換 |
| `text-green-700` 狀態色 | `text-status-success` |
| `bg-amber-50` 警告 | `bg-status-warning/10` |
| `bg-gradient-to-br from-slate-900 to-indigo-900` | 用 brand-navy 與 brand-cta 漸層 |

### 5.2 動效

| ❌ 反模式 | ✅ 正確做法 |
|---|---|
| `hover:scale-110` | `hover:scale-[1.02]` 或乾脆不縮放，改用 `hover:shadow-md` |
| `transition-all duration-1000` | `transition-colors duration-200`（指定屬性 + 用 token） |
| 自製 keyframes spinner | 用 lucide-react 的 `<Loader2 className="animate-spin" />` |

### 5.3 結構

| ❌ 反模式 | ✅ 正確做法 |
|---|---|
| icon-only button 沒 aria-label | 永遠加 `title` + `aria-label` |
| 頁面缺 back 按鈕 | sticky header 一定有 ChevronRight rotate-180 |
| 刪除無確認 | 用 `<ConfirmDialog>` (apps/frontend/src/components/ui/confirm-dialog.tsx) |
| 自製 toggle div | 用 native `<button>` + `aria-pressed` |

---

## 6. Granola 對標借鑑點

PR20 訪談 Q8=Granola，借鑑了什麼、沒借鑑什麼：

| 借鑑 | 為何借 |
|---|---|
| Calm 配色（低彩、中性灰白） | 會議產出資訊密集，UI 別再加噪音 |
| 真實截圖 hero（不堆抽象插畫） | 比 illustration 更有說服力 |
| 單欄 reading layout | 重點資訊不該水平拉伸；行長過寬反而讀不快 |
| 動效克制（200ms 標準） | 反 AI-slop；專業氣質 |
| 結論先行（TL;DR → 細節） | 金字塔原則；BLUF (bottom line up front) |

| 沒借 | 為何不借 |
|---|---|
| Granola 全黑/全白單色 | 我們是企業 B2B，需要 brand 識別；DDG 8 色保留 |
| Granola「無 sidebar」設計 | MeetChi 跨會議導航（dashboard / RAG / templates / settings）需要 sidebar |
| Granola macOS 原生風 | 我們是 web，且要在企業 Windows 環境跑 |

---

## 7. 變更管理

修改本文 + globals.css 的流程：

1. 提案：開 issue 標 `design-system`，描述要改什麼 + 為什麼
2. 對齊：確認與 Q1-Q8 訪談結論一致；不一致需重訪 user
3. 實作：globals.css 改 token + 本文同步更新章節 3
4. Audit：跑 [配色 audit script](../audits/scripts/check-tokens.sh)（如有）確認沒漏網之魚
5. PR：必須含 before/after 截圖（dashboard / detail / RAG 至少 3 張）

---

## 附錄 A：Q1–Q8 訪談 Prompt 紀錄

下列為 PR20 訪談原始 prompt 的內容摘要（Sprint 2a，2026 年 4 月底）。完整對話記錄保留在 conversation transcript（C: claude-projects D--Side-project-MeetChi）。

### Q1 整體調性

```
MeetChi 之前的視覺是「AI 科技未來感」（深紫 + 螢光青）。觀察到三個問題：
  1. 螢光青 #5BFAE6 在大量會議列表上很刺眼
  2. 紫色 #7C3AED 太濃，跟「企業會議工具」氣質不合
  3. 缺乏品牌識別 — 任何 AI SaaS 都長這樣

要往哪個方向走？
  a. 純極簡（Linear / Notion 風）— 灰階為主、單一 accent
  b. 暖科技（Slack / Asana 風）— 紫粉橘混搭
  c. 工業×人文（DDG 奇美承接）— 深藍主軸 + 暖橙暖黃補
  d. 自由發揮 — 我給設計建議由你選
```

→ 使用者選 **c**。

### Q2 配色系統

```
若 c (工業×人文)，色票範圍要多廣？
  a. 雙色（深藍 + 暖橙）極簡
  b. DDG 8 色活力（深藍 + 7 補色）
  c. 自定 5 色（讓我提案）
```

→ 使用者選 **b**。

### Q3 螢光青去留

```
原本的 #5BFAE6 螢光青在新色票要不要保留？
  a. 保留作為「AI 識別」次要強調色
  b. 移除，由 DDG 之一補位（建議 brand-green #06D6A0）
  c. 改色但保留「霓虹感」概念（如 #00E5FF）
```

→ 使用者選 **b**。

### Q4 字體

```
中文字體選擇：
  a. 系統預設（PingFang TC / Microsoft JhengHei）
  b. 思源宋體（襯線、文學氣質）
  c. 思源黑體（無襯線、工業＋人文兼具）
  d. 自訂變體
```

→ 使用者選 **c**。

### Q5 資訊密度

```
頁面密度設定：
  a. 高密度（Bloomberg / 交易終端風）
  b. 低密度（Notion 風，大量留白）
  c. 折衷密度（卡片有適度留白，但不到「奢侈空間」）
```

→ 使用者選 **c**。

### Q6 動效強度

```
動效程度：
  a. 無動效（純色彩切換）
  b. 微動效（200-300ms hover/fade）
  c. 強動效（spring/bounce/parallax）
```

→ 使用者選 **b**。

### Q7 詳情頁 IA

```
會議詳情頁的資訊架構：
  a. 標籤頁切換（摘要 / 逐字稿 / 待辦 各自獨立）
  b. 雙欄左右分（左摘要右逐字稿）
  c. 單欄垂直（顆粒由大到小：TL;DR → 結論 → 細節）
```

→ 使用者選 **c**。觸發 PR23 DetailView 重設計。

### Q8 對標品

```
我先研究 5 個對標品（Granola / Otter / tl;dv / Fireflies / Read AI），列出
他們各自的設計取向、強項、可借用點，再由你選一個或多個融合。
```

→ 使用者選 **Granola**（calm productivity 借鑑點：真實截圖 hero、單欄 reading layout、低彩配色、動效克制）。

---

## 附錄 B：Token 對應實作位置

| 層 | 檔案 |
|---|---|
| Token 定義（CSS 變數） | [apps/frontend/src/app/globals.css](../../apps/frontend/src/app/globals.css) |
| Tailwind config（自動 pick up `--color-*`） | Tailwind v4 zero-config，不需 tailwind.config.ts |
| 字體載入 | [apps/frontend/src/app/layout.tsx](../../apps/frontend/src/app/layout.tsx) `next/font` |
| 主題切換 hook | [apps/frontend/src/hooks/useTheme.ts](../../apps/frontend/src/hooks/useTheme.ts) |
| 主題切換 UI | [apps/frontend/src/components/ThemeToggle.tsx](../../apps/frontend/src/components/ThemeToggle.tsx) |
| ConfirmDialog 標準確認框 | [apps/frontend/src/components/ui/confirm-dialog.tsx](../../apps/frontend/src/components/ui/confirm-dialog.tsx) |
| 卡片標準範例 | [apps/frontend/src/components/MeetingCard.tsx](../../apps/frontend/src/components/MeetingCard.tsx) |
| 單欄 detail 範例 | [apps/frontend/src/components/DetailView.tsx](../../apps/frontend/src/components/DetailView.tsx) |
