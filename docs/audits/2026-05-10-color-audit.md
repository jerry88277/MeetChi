# Frontend Color/DDG Conformity Audit — 2026-05-10

> **Scope**：全前端配色是否符合 DDG 奇美設計系統（[DDG-CHIMEI.md](../design/DDG-CHIMEI.md)）
> **方法**：grep `bg-[#`、`text-[#`、Tailwind 預設色 (`bg-(red|blue|green|yellow|gray|slate|zinc)-*`)、`bg-white`、`text-black`、深淺色矛盾組合
> **重點**：使用者明確反映「有些頁面存在深淺色矛盾不一」

---

## Executive Summary

- **5 個重災區**：ChatPanel / SettingsModal / dashboard/page.tsx / login/page.tsx / RAG suite (Drawer/ReferencePanel/Sidebar)
- **70+ 處違規**：P0=23 / P1=30+ / P2=20+
- **根因**：codebase 並存三套配色寫法（DDG token / Tailwind defaults / raw hex）。後期 component (DetailView / Sidebar / DashboardView core) 對；landing / login / settings / RAG suite 是 token 系統建立前寫的，沒回頭重構。

---

## DDG Canonical Tokens（從 globals.css 抽出）

### 品牌色（8 色）
- `brand-navy` `#041E42` — sidebar 背景
- `brand-cta` `#2D428B` — 主 CTA 深藍
- `brand-orange` `#FF6B35` — 待辦/能量
- `brand-green` `#06D6A0` — 永續/成功
- `brand-forest` `#1E5128` — 深綠/材料
- `brand-amber` `#F2C14E` — 暖黃/講者
- `brand-violet` `#4D5CB7` — 模板/AI
- `brand-coral` `#C5283D` — 重要/警示
- `brand-azure` `#4A90E2` — 流動/資訊

### 狀態色
- `status-success` `#48B070`
- `status-warning` `#E4831A`
- `status-error` `#D2343D`

### 語意色（雙模式自動切）
- `background` / `foreground` / `surface` / `card` / `muted` / `muted-foreground` / `border` / `ring`

完整規格見 [DDG-CHIMEI.md §3](../design/DDG-CHIMEI.md#3-token-規格)。

---

## P0 — Hardcoded 顏色（繞過設計系統）

| File:line | Offending code | Should be | Issue |
|---|---|---|---|
| `app/dashboard/page.tsx:343` | `bg-[#0052cc]` + `hover:bg-[#0040a2]` | `bg-brand-cta hover:bg-brand-cta/90` | 任意 hex 不在 DDG palette |
| `components/SettingsModal.tsx:25-66` | `bg-white`, `text-gray-800`, `text-gray-500`, `bg-gray-900`, `hover:bg-black` | `bg-card`, `text-foreground`, `text-muted-foreground` | 8+ 行 gray/white；整個 modal 偏離 palette |
| `app/page.tsx:16` | `bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-900` | brand-navy → brand-cta 漸層 | landing 用 slate/indigo 非 DDG |
| `app/login/page.tsx:95` | `bg-slate-900`, `bg-white`, `text-slate-900`, `hover:bg-slate-100` | `bg-background`, `bg-card`, `text-foreground` | login 全套非 DDG |
| `components/DashboardView.tsx:73` | `bg-green-50 text-green-700 border-green-200` + `dark:bg-green-900/30 dark:text-green-400` | `bg-status-success/10 text-status-success` | 綠色 badge 用 Tailwind 預設 |
| `app/dashboard/page.tsx:416` | `bg-amber-50 text-amber-700/70 bg-amber-100 bg-amber-600` | `bg-status-warning/10 text-status-warning` | crash recovery UI 用原色 amber |
| `components/rag/RagSidebar.tsx:14` | `bg-brand-navy dark:bg-slate-950` | `bg-brand-navy`（加 `[data-theme="dark"]` 規則） | dark 用 slate 不是 DDG |
| `components/rag/ChatPanel.tsx:108-185`（多處） | `bg-surface dark:bg-slate-950`, `bg-white dark:bg-slate-900`, `bg-slate-50 dark:bg-slate-950/50`, `bg-slate-100 dark:bg-slate-800` | 直接用 semantic token，省略 dark: 覆寫 | 8+ slate hardcode |
| `components/rag/RagDrawer.tsx:54` | `bg-white dark:bg-slate-950` | `bg-card`（已內建 dark 切換） | 不需自己 dark: 覆寫 |
| `components/rag/ReferencePanel.tsx:21-22, 51-52` | `bg-white dark:bg-slate-900`, `bg-white/90 dark:bg-slate-900/90`, `text-brand-navy dark:text-white` | `bg-card`, `bg-card/90`, `text-foreground` | 4 處 white/slate |
| `components/RecordingView.tsx:151,154,270,276` | `hover:bg-slate-100`, `text-green-50/700`, `bg-green-50`, `border-green-200` | DDG status/brand token | 綠色 recorder badge 用 Tailwind 預設 |

---

## P0 — Light/Dark 模式矛盾（用戶明確反應）

| File:line | Issue | Details |
|---|---|---|
| `DashboardView.tsx:73` | badge 用 `bg-green-50` 但 `dark:bg-green-900/30` | light 是 hardcoded 綠，dark 自製覆寫；應該 `bg-status-success/10` 一行就好（dark 自動切） |
| `ChatPanel.tsx:108-185` | 8+ 處 `bg-white` + `dark:bg-slate-*` | light 寫死白、dark 寫死 slate；都應 `bg-card` token |
| `RagDrawer.tsx:54,77,86` | `bg-white dark:bg-slate-950` + `dark:hover:bg-slate-800` | drawer 背景違規；hover 也是 |
| `RecordingView.tsx:151,154` | `hover:bg-slate-100`（only light）+ green-50/700 hardcoded | hover 沒 `dark:` 變體；綠色繞過 DDG |
| `ReferencePanel.tsx:22` | `bg-white/90 dark:bg-slate-900/90` | hardcoded opaque；應 `bg-card/90` |
| `RagSidebar.tsx:14` | `bg-brand-navy dark:bg-slate-950` | sidebar dark 覆寫 slate；應該 (1) globals.css 給 brand-navy 加 dark variant，或 (2) 改用 semantic surface |

---

## P1 — Status 色誤用

| File:line | Offending | Should be | 影響 |
|---|---|---|---|
| 多處 dashboard | `bg-amber-*` 警告態 | `bg-status-warning` (#E4831A) | amber ≠ #E4831A |
| Sidebar badge | `bg-green-50 text-green-700` | `bg-status-success/10 text-status-success` | 狀態色語意割裂 |

---

## P1 — 品牌色稀釋

| File | 違規數 | 主要錯誤 |
|---|---|---|
| `SettingsModal.tsx` | 8 | gray/white/black 取代品牌 palette |
| `app/page.tsx` (landing) | 12+ | slate-900, indigo-900, white 取代 brand-navy + brand-cta |
| `app/login/page.tsx` | 6+ | slate-900, white, slate-100 取代 brand-navy, brand-cta |
| `ChatPanel.tsx` + RAG suite | 20+ | slate-50/800/900/950 取代 surface/card/muted |
| `RagDrawer.tsx`, `ReferencePanel.tsx` | 5+ | white + slate 覆寫 |

---

## Cross-Cutting Findings

### 違規數排名（前 5）

1. **`components/rag/ChatPanel.tsx`** — 15+ slate/white hardcode；8 dark: 矛盾
2. **`app/components/SettingsModal.tsx`** — 8 gray/white；整個 modal 離 palette
3. **`app/dashboard/page.tsx`** — 6（FAB blue / 復原 UI amber / gradient）
4. **`app/login/page.tsx`** — 6（slate-900, white, indigo-900 漸層）
5. **`components/rag/ReferencePanel.tsx`** — 5（white, slate 覆寫）

### 最被誤用的 token

- `bg-white` 沒用 token：12+ 處 → `bg-card`
- `dark:bg-slate-*` hardcode：18+ 處 → 用 semantic dark 覆寫
- Tailwind 狀態預設 (`bg-green-*` / `bg-amber-*` / `text-red-*`)：10+ 處 → DDG status-*
- slate 系列：25+ 處 → semantic token

### 根因分析

Codebase 同時並存三種配色寫法：

1. **DDG semantic token**（正確）：`bg-card`、`text-foreground`、`status-success`、`brand-cta`
2. **Tailwind 預設**（錯誤）：`bg-white`、`text-green-700`、`bg-slate-900`
3. **Raw hex**（錯誤）：`#0052cc`、`#0040a2`

Landing / login / settings / RAG suite 是 token 系統建立前寫的，沒回頭重構。後期 component (DetailView / Sidebar / DashboardView core) 都對。

---

## Recommended Follow-Up PRs（按 ROI 排序）

### P0 — 立刻（視覺一致性 + dark mode）

1. **RAG suite dark: 覆寫整批清理** — ChatPanel / RagDrawer / ReferencePanel / RagSidebar
   - 20+ 處 `dark:bg-slate-*` → 改用 semantic token，靠 `[data-theme="dark"]` 自動切
   - 同時解 user 反映的「跨會議知識庫頁面風格不一」
2. **DashboardView 安全 badge** (line 73)
   - `bg-green-50 text-green-700 dark:...` → `bg-status-success/10 text-status-success`
3. **Crash recovery UI 配色** (dashboard/page.tsx:416–438)
   - amber hardcode → `bg-status-warning` 或 `bg-brand-orange`
   - 補 dark: 變體

### P1 — 高 ROI（品牌一致）

4. **SettingsModal 整體重做**
   - 全部 `bg-white`/`text-gray-*`/`bg-gray-900` → DDG token
5. **Landing + Login 重做**
   - slate-900/indigo-900 漸層 → brand-navy + brand-cta
   - 白色 box → semantic surface/card

### P2 — 跟進（清理）

6. **globals.css 補 brand 色 dark variant**（如需要）
   - 現只有 semantic token 有 `[data-theme="dark"]`
   - 評估 brand-navy 是否該有 dark 變體，或永遠 solid
7. **Alias 淘汰**：`brand-accent` → `brand-violet`、`brand-highlight` → `brand-green`

---

## 實作備忘

- **Token 應用**：結構化 layout 永遠優先 semantic token (`bg-card`/`text-foreground`/`border-border`)；brand 色只用於 accent/CTA。
- **Dark mode**：用 globals.css 的 `[data-theme="dark"]` 系統，**不**在 component 加 `dark:` modifier + hardcode。
- **RAG 子系統**：ChatPanel/RagDrawer/ReferencePanel/RagSidebar 平行開發，建議**一個 PR 統一 cleanup**。
