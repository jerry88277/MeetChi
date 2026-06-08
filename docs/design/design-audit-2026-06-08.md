# MeetChi 前端設計審計報告

**日期**: 2026-06-08  
**方法**: taste-skill `redesign-skill` 框架（[github.com/leonxlnx/taste-skill](https://github.com/leonxlnx/taste-skill)）  
**審計範圍**: Login、Dashboard、MeetingCard、Sidebar、SettingsView

---

## 審計框架說明

taste-skill 是一套「Anti-Slop」設計準則，用來識別 AI 生成介面的通病並提升到高品質產品等級。  
核心審計維度：排版、色彩/表面、佈局、互動狀態、文案、元件模式、圖示。

---

## 一、排版（Typography）

### T1 — 標題層級壓縮，缺乏 display 級別 ✦ P1

- **現況**: `h1` 使用 `text-2xl font-bold`（24px），與卡片標題 `font-bold` 差距不夠
- **問題**: 整個介面視覺重量均勻，使用者難以快速掃描頁面層級
- **參考**: Linear 的 dashboard header 使用 ~32-36px + letter-spacing -0.02em
- **建議修法**:
  ```tsx
  // DashboardView.tsx — 標題
  <h1 className="text-3xl font-bold tracking-tight text-foreground">我的會議記錄</h1>
  // MeetingCard — 卡片標題
  <h3 className="text-base font-semibold text-foreground ...">  {/* 從 font-bold 改 font-semibold */}
  ```

### T2 — 缺乏 Medium (500) / SemiBold (600) 中間重量 ✦ P1

- **現況**: 幾乎只有 `font-medium`(500)、`font-semibold`(600)、`font-bold`(700) 混用，但按鈕、標籤多為 `font-medium`
- **問題**: 「按鈕文字」和「輔助說明文字」視覺重量相近，層次不清晰
- **建議**: 確立全域規則：
  - 頁面標題 = `font-bold` + `tracking-tight`
  - 卡片標題 = `font-semibold`
  - 主要按鈕 = `font-medium`
  - 說明文字 = `font-normal`
  - Chip/Badge = `font-semibold text-[10px]`（已對，保留）

### T3 — 數字未統一 tabular-nums ✦ P2

- **現況**: MeetingCard 底部計數 chip 有 `tabular-nums`（✅），但日期/時長欄位沒有
- **影響**: 日期列表在卡片間寬度不一致，造成視覺抖動
- **建議**: 在 `globals.css` 加全域 `font-variant-numeric: tabular-nums` 至 `.tabular` utility，或在日期 span 加 `tabular-nums`

---

## 二、色彩與表面（Color & Surfaces）

### C1 — 背景使用純白 #ffffff，surface token 未被主介面採用 ✦ P1

- **現況**: `globals.css` 定義 `--color-surface: #FAFAF8`（微暖），但 `--color-background: #ffffff`（純冷白）。主 dashboard 頁面用的是 `background`
- **問題**: DDG 設計系統的「微暖人文」基調只出現在 Login 頁（`bg-surface`），主介面感覺更冷硬
- **建議**:
  ```css
  /* globals.css */
  --color-background: #FAFAF8;   /* 統一改為 surface 微暖色 */
  --color-card: #ffffff;          /* card 保留純白，形成一層對比 */
  ```

### C2 — hover shadow 不帶色相（generic black shadow） ✦ P1

- **現況**: `MeetingCard` 的 `hover:shadow-lg` 是預設黑色 shadow（`rgba(0,0,0,0.1)`）
- **問題**: taste-skill §Color 指出：純黑 shadow 是最普遍的 AI 介面特徵
- **建議**:
  ```tsx
  // MeetingCard.tsx — 改為帶品牌色相的 shadow
  className="... hover:shadow-[0_4px_24px_-4px_rgba(45,66,139,0.15)] ..."
  //                                                    ^ brand-cta 色調
  ```

### C3 — 多個強調色同時出現在卡片上，造成視覺噪音 ✦ P1

- **現況**: MeetingCard 中模板 chip 用橙/藍紫/coral/azure 多色；底部計數用綠/橙/紅
- **問題**: taste-skill 明確：「Pick one accent. Remove the rest.」一張卡上 5-6 種色相讓眼睛疲勞
- **建議方向**（不是要移除功能，而是降低飽和度）:
  - 模板 chip：統一改為 `bg-foreground/5 text-foreground/60`，只用文字區分
  - 計數 chips：只保留圖示顏色，移除背景色塊
  - 重要狀態（失敗/機密）才用強色

### C4 — Dark mode 未完整驗證色彩對比 ✦ P2

- **現況**: `globals.css` 有 `.dark` 變數，但部分元件硬碼 Tailwind 基礎色（如 `text-slate-600`）而非語義 token
- **建議**: 全面替換 hardcoded 色為語義 token（`text-muted-foreground`、`text-foreground`）

---

## 三、佈局（Layout）

### L1 — transition-all 觸發不必要的 layout recalculation ✦ P0（性能）

- **現況**: `MeetingCard`、`Sidebar` 的按鈕多處使用 `transition-all`
- **問題**: taste-skill §Interactivity 明確：「Animations using top/left/width/height → switch to transform and opacity.」`transition-all` 涵蓋所有 CSS 屬性，包括會觸發 reflow 的屬性
- **建議**:
  ```tsx
  // 改為精確 transition
  className="transition-colors duration-200 ..."
  // 或
  className="transition-[colors,shadow,transform] duration-200 ..."
  ```

### L2 — MeetingCard 卡片高度不一致，但底部沒有 pin CTA ✦ P1

- **現況**: `completed` 卡片高於 `pending`/`processing`（有 TL;DR + chips），加了一個 `h-4` 佔位符試圖補齊
- **問題**: 在 multi-column grid 時卡片高度依然不一，`h-4` 佔位不夠精確
- **建議**: 用 `flex flex-col` + 在 chips 區塊加 `mt-auto` 確保底部永遠貼齊

### L3 — 卡片邊框半徑均勻（xl everywhere） ✦ P2

- **現況**: 幾乎所有 card、button、badge 都是 `rounded-xl`（12px）或 `rounded-lg`
- **taste-skill 指引**: 外層容器用較大圓角、內層元素用較小圓角（concentric radius）
- **建議**: 
  - Page-level card: `rounded-2xl`（16px）
  - 卡片內 chip/badge: `rounded`（4px）或 `rounded-md`（6px）
  - Button: `rounded-xl`（保留現狀）

### L4 — Dashboard header 按鈕群視覺重量過重 ✦ P1

- **現況**: 「重新整理」和「新增會議 ▾」兩個按鈕並排，都是 `bg-card border border-border` + filled primary
- **問題**: 次要操作（重新整理）和主要操作（新增）同等視覺重量
- **建議**: 
  - 「重新整理」降為 icon-only 或 ghost button（`text-muted-foreground hover:text-foreground`）
  - 「新增/上傳」保留 primary 填色

---

## 四、互動與狀態（Interactivity & States）

### I1 — Transition 使用預設 ease，缺乏品牌感 ✦ P1

- **現況**: 所有 transition 使用 Tailwind 預設（`ease-in-out` 或 `ease`）
- **參考**: Granola 和 Linear 的「calm productivity」感來自 `cubic-bezier(.16,1,.3,1)` 的類 spring 曲線
- **建議**: 在 `tailwind.config.ts` 加入:
  ```ts
  transitionTimingFunction: {
    'brand': 'cubic-bezier(0.16, 1, 0.3, 1)',   // 快入慢出 spring
    'brand-out': 'cubic-bezier(0.2, 0, 0, 1)',   // DDG 已定義
  }
  ```
  然後卡片改用 `duration-200 ease-brand`

### I2 — 卡片 active 回饋過小（scale 0.99） ✦ P2

- **現況**: `active:scale-[0.99]` — 縮放量極小（1% 差），難以感知
- **taste-skill 建議**: `active:scale-[0.98]` or `active:translate-y-px` 模擬物理按壓感
- **建議**: `active:scale-[0.98]` + `transition-transform duration-100`

### I3 — 卡片列表無進場動畫 ✦ P2

- **現況**: 會議卡片在載入完成後直接出現（無 stagger）
- **taste-skill §Motion**: 「Elements cascade in with slight delays」
- **建議**: 加入 CSS animation delay，不需引入 Framer Motion：
  ```tsx
  // 在 map 中
  style={{ animationDelay: `${index * 40}ms` }}
  className="animate-in fade-in slide-in-from-bottom-2 duration-300 fill-mode-both"
  ```

### I4 — Empty state 缺少設計 ✦ P1

- **現況**: 無會議時只有簡單文字提示（需確認 DashboardView 的 empty state 品質）
- **taste-skill**: 「An empty dashboard showing nothing is a missed opportunity. Design a composed 'getting started' view.」
- **建議**: Empty state 應包含：說明文字 + 主要 CTA（上傳第一個會議）+ 輔助圖示

---

## 五、文案與微文案（Copy & Microcopy）

### M1 — 按鈕/成功訊息有感嘆號 ✦ P1

- **現況**: 部分 toast 訊息使用「！」結尾（需確認）
- **taste-skill**: 「Exclamation marks in success messages — remove them. Be confident, not loud.」
- **建議**: `會議已刪除` 而非 `會議已刪除！`；`上傳完成` 而非 `上傳成功！`

### M2 — 「地端機密處理」badge 文字過技術性 ✦ P2

- **現況**: badge 用 `Shield` 圖示 + 「地端機密處理」— 對非技術使用者可能不直觀
- **建議**: 改為「資料安全保護」或 tooltip 改為更使用者導向的說明

---

## 六、元件模式（Component Patterns）

### CP1 — 圖示全部使用 Lucide（最普遍的 AI 圖示庫） ✦ P2

- **現況**: 全前端只用 Lucide icons
- **taste-skill §Iconography**: 「Lucide or Feather icons exclusively — use Phosphor, Heroicons instead for differentiation.」
- **評估**: 短期不建議全換（大型重構），但可在關鍵差異化位置（如 sidebar 圖示、empty state）引入 Phosphor Light 變體作為點綴

### CP2 — MeetingCard 是「generic card look」 ✦ P1

- **現況**: `bg-card border border-border rounded-xl` — 標準 shadcn card 外觀
- **taste-skill**: 「Remove the border, OR use only background color, OR use only spacing. Cards should exist only when elevation communicates hierarchy.」
- **建議方向**: 移除 `border border-border`，改用輕微 shadow + 背景對比（`bg-white` 在 `bg-surface` 底色上）：
  ```tsx
  className="bg-card rounded-2xl shadow-sm hover:shadow-[0_4px_24px_-4px_rgba(45,66,139,0.12)] border-l-4 ..."
  // 去掉 border border-border，保留 border-l-4 色邊
  ```

### CP3 — 搜尋框是方形（rounded-lg），可以更具品牌感 ✦ P2

- **現況**: 搜尋框為 `rounded-lg`（8px）
- **建議**: 改為 `rounded-full` pill 型（符合 Granola/Linear 搜尋框慣例），更顯精緻

---

## 七、優先實施順序

依照 taste-skill 建議的最大視覺衝擊順序：

| 優先 | 項目 | 預估工時 |
|------|------|---------|
| **P0** | L1 — 替換 `transition-all` 為精確 transition | 30 分鐘 |
| **P1** | C1 — background 改為 `#FAFAF8` 微暖色 | 5 分鐘 |
| **P1** | C2 — card hover shadow 帶品牌色相 | 15 分鐘 |
| **P1** | T1 — Dashboard h1 放大 + tracking-tight | 10 分鐘 |
| **P1** | CP2 — MeetingCard 移除 border，改用 shadow | 20 分鐘 |
| **P1** | I1 — 加入 brand cubic-bezier to tailwind.config | 10 分鐘 |
| **P1** | L4 — 重新整理按鈕降為 ghost | 10 分鐘 |
| **P1** | I4 — 設計 empty state | 2-3 小時 |
| **P2** | I3 — 卡片列表 stagger 進場 | 30 分鐘 |
| **P2** | L3 — Concentric border-radius | 30 分鐘 |
| **P2** | T3 — 日期 tabular-nums | 10 分鐘 |
| **P2** | CP3 — 搜尋框改 rounded-full | 10 分鐘 |

---

## 八、不建議動的地方（Preserve）

| 設計決策 | 原因 |
|---------|------|
| `bg-brand-navy` sidebar | DDG §1 明確指定品牌深藍側欄，是品牌識別核心 |
| Inter + Noto Sans TC 字型 | 最佳中英文排版組合，改字型風險 > 收益 |
| `border-l-4` 狀態色邊 | 快速識別 meeting 狀態的高效模式，保留 |
| `brand-cta` 單一主色調 | 已符合 taste-skill「one accent」原則 |
| DDG 8 色在 chip 的保留使用 | 可降飽和度，但不全移除（功能性色彩標籤） |
| `text-[10px]` chip 尺寸 | 在中文字符下已是最小可讀尺寸 |

---

## 九、設計方向定位

依 soft-skill 的 vibe archetype 分類，MeetChi 應屬：

> **「Soft Structuralism」** — Silver-grey/warm-white backgrounds, massive bold grotesk typography, airy floating components, soft diffused shadows.

即：Granola 的 calm productivity 路線（DDG 已確認），而非 Linear 的 dark/glass 路線。  
實施上述改善時，決策導向應以「讓介面更輕盈通透、更少邊框噪音、陰影帶品牌溫度」為準。
