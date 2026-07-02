# MeetChi Brand × UX Frontend Optimization Report

> **⚠️ 狀態更新（2026-07-02）** — 已實作項目：
> - ✅ **雙層色彩架構**（§2.3 應修正 #1）：`brand-chimei-*` 官方品牌層已加入 `globals.css`（navy/orange/green/red/yellow/teal），與 `brand-*` 產品互動層並存。
> - ✅ **focus 可達性**（§3.3）：`:focus-visible` 樣式已補回。
> - ✅ **`brand-accent` 死 token 清除**：前後端改用 `brand-violet`（詳見 DDG-CHIMEI.md 修正註 + devlog 2026-07-02）。
> - 文案/空狀態/獎勵時刻（§3.1–3.4）等仍待實作。

## 1. Executive Summary

**Verdict:** MeetChi 已有正確的企業產品骨架與 Soft Structuralism 基調，但目前更像「受 CHIMEI 啟發」而不是「真正承接 CHIMEI 品牌」，最大缺口在於色票不夠忠實、成功路徑回饋不足、以及文案仍偏工具化。

### 3 個最 critical findings
1. **品牌色失真過大**：目前 DDG token 對官方色的偏差最大在綠與橙，已超過「設計延伸」而接近「另起一套產品色」。Evidence: `docs/design/DDG-CHIMEI.md:49-57`, `apps/frontend/src/app/globals.css:18-33`
2. **品牌精神尚未落到互動回饋**：介面能完成任務，但缺少「待人以真」「A Step Up」式的鼓勵、完成感與下一步引導。Evidence: `apps/frontend/src/components/DashboardView.tsx:276-283`, `apps/frontend/src/components/MeetingCard.tsx:164-179`, `apps/frontend/src/components/rag/ChatPanel.tsx:292-296`
3. **文案與真實能力有落差**：搜尋 placeholder、RAG loading 文案、錯誤文案與空狀態文案仍有 generic 或不精確問題，直接影響信任感。Evidence: `apps/frontend/src/components/DashboardView.tsx:76-79,190-196`, `apps/frontend/src/components/rag/ChatPanel.tsx:143,295`, `apps/frontend/src/components/Sidebar.tsx:142-146`

---

## 2. Brand Color Alignment

### 2.1 Official CHIMEI vs DDG Token 對照

| Official | HEX | DDG Token | DDG HEX | Match? | Gap |
|---|---:|---|---:|---|---|
| CHIMEI 深藍 | `#001f63` | `brand-navy` | `#041E42` | **Partial** | 偏更深、更灰，品牌辨識還在，但失去官方藍的明亮與銳度 |
| 暖橙 | `#e68b11` | `brand-orange` | `#FF6B35` | **No** | 色相明顯轉向偏紅橘，從「暖橙」變成較 SaaS 化的 energetic orange |
| 青綠 | `#33b371` | `brand-green` | `#06D6A0` | **No** | 明度與飽和度都偏高，已從品牌青綠轉為 mint / neon-like accent |
| 莓紅 | `#d93640` | `brand-coral` | `#C5283D` | **Near** | 仍在同色域，略深略暗，屬可接受延伸 |

### 2.2 Faithfulness 評估

**結論：目前 DDG palette 是「品牌啟發版」，不是「品牌忠實版」。**

- **最大 divergence：`brand-green`**。它最不像官方 CHIMEI 青綠，會把品牌感往一般 AI 產品常見的清亮 mint 推走。
- **第二大 divergence：`brand-orange`**。官方暖橙較沉穩、成熟；現行 `#FF6B35` 更像高活力行銷橘。
- **`brand-navy` 有品牌根基，但不夠準**。目前更像保守企業深藍，而不是 CHIMEI logo 的官方深藍。
- **`brand-coral` 最接近，可視為可接受延伸。**

### 2.3 應修正 vs 可保留

#### 應修正
1. **把官方色與產品延伸色分層**
   - 建議新增一層 `brand-chimei-*` 核心 token：
     - `brand-chimei-navy: #001f63`
     - `brand-chimei-orange: #e68b11`
     - `brand-chimei-green: #33b371`
     - `brand-chimei-red: #d93640`
   - 用於 logo、品牌識別區、核心圖像、品牌說明區。

2. **重新命名目前偏移較大的延伸色**
   - 現行 `#FF6B35` 不應繼續叫 `brand-orange`，建議改為 `accent-energy` 或 `accent-action`
   - 現行 `#06D6A0` 不應繼續叫 `brand-green`，建議改為 `accent-mint` 或 `accent-fresh`

3. **把 `brand-navy` 校正回官方藍**
   - 若 MeetChi 要代表 CHIMEI 企業內部產品，`brand-navy` 應直接回到 `#001f63`
   - 目前 `brand-cta: #2D428B` 可保留作為互動藍，不必取代官方藍

#### 可保留
1. **`brand-cta: #2D428B` 可保留**
   - 它適合作為產品互動色，並不一定要等於 logo 色
   - 這是「品牌 accuracy」與「互動 usability」可共存的典型案例

2. **`brand-coral` 可微調，不必強制重做**
   - 已接近官方莓紅，非當前最大風險

### 2.4 建議原則

**最好的做法不是把所有 UI 全改回 logo 色，而是建立「官方核心色 + 產品延伸色」雙層結構。**

這樣既能符合 CHIMEI 品牌準確性，也能保留 MeetChi 作為數位產品需要的可用性與層級控制。這同時符合：
- 品牌手冊的「一致性創造認知度與信賴感」
- design-advisor 的 **Consistency + Expectations**
- taste-skill 的 **Color Consistency Lock**

---

## 3. Brand Philosophy → UX Gaps

### 3.1 待人以真（Authenticity）

| Problem | Evidence | Fix | Why |
|---|---|---|---|
| 搜尋承諾大於實際能力 | `DashboardView.tsx:76-79,194-195` 文案寫「搜尋會議標題、關鍵字或參與者」，實作只搜 `title` 與 `summary` | 短期先改 placeholder 為真實能力，例如「搜尋會議標題或摘要重點」；中期再擴充搜尋欄位 | 真實感不是語氣，而是「說到做到」 |
| RAG loading 用語不真實 | `ChatPanel.tsx:295` 使用「正在搜尋文獻並生成回答...」 | 改成「正在整理相關會議內容並生成回答...」 | MeetChi 查的是會議，不是文獻；精準命名就是 authenticity |
| 空狀態過於 generic | `DashboardView.tsx:276-283` 只有圖示與一句話 | 補上 CTA、流程說明、範例結果 | 企業工具空狀態應像 onboarding，而不是佈告欄 |
| 介面仍偏模板化而非個人化 | `Sidebar.tsx:117-127` 有 user 資訊，但主視圖沒有任何針對使用者工作情境的迎接語 | 可在 dashboard header 次標加入「今天要先整理哪一場會議？」或依時間顯示簡短 welcome | Genuine 不等於熱情口號，而是讓使用者感覺「這是替我工作的工具」 |

**判斷：** MeetChi 目前沒有明顯 fake product UI，但有幾個「像產品模板複製貼上」的訊號，尤其是 generic empty state、過度泛用的登入文案、以及與實際功能不一致的搜尋承諾。

### 3.2 處之以善（Goodness / Benevolence）

| Problem | Evidence | Fix | Why |
|---|---|---|---|
| 系統失敗時對使用者幫助不足 | `ChatPanel.tsx:139-144` 只回 generic error；`ChatPanel.tsx:78-80` 歷史失敗只寫 console | 在 query history 與 chat composer 附近加 inline error + retry；標示可能原因 | Goodness 是「我幫你走完下一步」，不是只告知失敗 |
| 會議失敗狀態仍偏冷 | `MeetingCard.tsx:175-179` 只說點擊查看詳情並重試 | 改成可操作指引，例如「這次整理沒有完成，打開詳情即可查看原因並重新產生」 | 讓使用者知道系統站在他這邊 |
| 空狀態沒有把人推向成功 | `DashboardView.tsx:276-283`、既有 audit `design-advisor-audit-2026-06-08.md:37-41` | 提供「上傳第一場會議」主 CTA + 30 秒價值說明 + 可接受格式提示 | 企業使用者不需要被教育太多，但需要被順手帶進成功路徑 |
| 上傳流程雖已收斂，但尚未形成完整善意回饋 | `DashboardView.tsx:127-164` 已拆主次 CTA，是正向進展 | 上傳完成後補「接下來會發生什麼」與完成後的 reward banner | Benevolence 不只在避免痛苦，也在減少不確定性 |

### 3.3 形之以美（Beauty / Aesthetic）

| Problem | Evidence | Fix | Why |
|---|---|---|---|
| 卡片仍有「功能已齊」感，少了品牌美感的細節層 | `MeetingCard.tsx:120-124,128-203` | 降低多色 chip 競爭，讓強調色只出現在真正重要處；導入粒子 motif 的微紋理 | CHIMEI 的美不是裝飾多，而是有節制的秩序感 |
| 全域 focus 樣式被過度移除 | `globals.css:231-237` | 為 `button`, `a`, clickable card 補 `focus-visible` | 美感不應以犧牲可達性為代價，這也是 enterprise quality |
| 品牌特徵仍停留在色塊，而非結構與細節 | `Sidebar.tsx:55-66`, `DashboardView.tsx:102-166` | 在 section label、empty state、loading 以低對比粒子語彙加入品牌深度 | 「形之以美」要從結構、節奏、細節一起成立 |

**判斷：** 現況已比一般 AI SaaS 更穩，但仍未到「形之以美」的品牌標準。它目前是乾淨的，還不算真正有美感辨識度。

### 3.4 Xingfu / A Step Up

| Problem | Evidence | Fix | Why |
|---|---|---|---|
| 主要動作有完成任務，但缺少上升感 | `DashboardView.tsx:143-163` 主 CTA 已明確；完成後只剩一般成功訊息 `DashboardView.tsx:177-183` | 把成功文案改成成果導向，例如「摘要已完成，可直接帶著決策與待辦往下走」 | 「A Step Up」不是按鈕本身，而是讓人感到工作被推進了 |
| 會議摘要完成缺少獎勵時刻 | `MeetingCard.tsx:182-203` 只有數字 chip，無成就感語言 | 新增 completion ribbon / toast，例如「本場已整理出 3 項決策、2 項待辦」 | 讓完成感可見，提升持續使用意願 |
| Detail 頁缺少「做完這份摘要後下一步」提示 | `DetailView.tsx:49-62` 架構正確，但前 100 行可見重點仍聚焦操作與載入，不見成果導向 CTA | 在 TL;DR 下方增加「下一步建議」或「分享 / 匯出摘要」的輕量引導 | 讓會議摘要不是終點，而是工作推進器 |

### 3.5 三軸平衡：工業 × 人文 × 永續

**目前主導軸：工業。**

- 優點：結構清楚、資訊有層次、卡片與 sidebar 規則穩定
- 證據：`DDG-CHIMEI.md:16-19`, `DetailView.tsx:49-62`, `MeetingCard.tsx:120-203`

**次要存在：人文。**

- 來源：暖白背景、適度圓角、資料安全保護 badge、中文字體策略
- 但仍不足：copy 還不夠體貼與真誠，完成時刻不夠有溫度

**最缺少：永續。**

- 目前幾乎只存在於顏色宣言中，尚未變成可感知的體驗
- UI 缺乏「減少重工、沉澱知識、讓下一次更省力」的可視化設計語言

### 3.6 三軸平衡的具體修正方向

1. **工業保留**
   - 保留單欄 detail IA、穩定的資訊層級、直接的上傳入口
2. **補強人文**
   - 全面升級 empty state、error state、completion state 文案
   - 用使用者任務語言取代系統語言
3. **補強永續**
   - 把「跨會議沉澱」「重複議題累積」設計成可感知的進展
   - 使用低對比粒子 motif 表達材料流動與知識沉澱，而不是額外插畫

---

## 4. Material Motif Opportunity

CHIMEI 輔助圖案來自 material particles（cylinder / cube / sphere）。MeetChi 不適合把它做成大面積裝飾，但很適合做成**低對比、結構化、功能型的品牌紋理**。

### 4.1 最適合落點

| 場景 | 建議形式 | 實作方式 | 為何適合 |
|---|---|---|---|
| Dashboard 空狀態 | 3 個低對比粒子輪廓，沿對角線疏排 | `bg-brand-navy/[0.03]`, `bg-brand-green/[0.04]`, `border-brand-orange/[0.08]` 的 SVG / CSS background | 空狀態需要品牌深度，但不能搶過 CTA |
| Upload / Processing loading | 以 sphere → cube → cylinder 的微動態序列取代 generic loader 文案旁點綴 | 僅做 opacity + translateY 2px，200-300ms，無 bounce | 對應「原始音訊被整理成結構化輸出」 |
| Detail section divider | 在 section label 左側放極小粒子 trio glyph | 12-16px 單色 icon，使用 `text-muted-foreground/40` | 提升識別，不增加視覺噪音 |
| Onboarding / Empty query in RAG | 粒子聚合成「資料被彙整」的靜態圖形 | 卡片內右下角或背景角落，透明度極低 | 最能對應「分散會議 → 聚合知識」 |
| Login 次視覺 | logo card 後方可加極淡粒子網格 | 僅在卡片陰影區域內出現，不鋪滿畫面 | 讓 CHIMEI 品牌從符號延伸到材質語言 |

### 4.2 不建議使用的位置

1. **不要放在每張 MeetingCard 背景**
   - 會造成列表重複與噪音，違反 taste-skill 對 identical layout repeating 的警戒
2. **不要做大型裝飾性 hero pattern**
   - MeetChi 是 enterprise internal tool，不是品牌行銷頁
3. **不要做高對比幾何插畫**
   - 這會破壞 Soft Structuralism 的輕盈感

### 4.3 最推薦的第一步

**先從 Dashboard empty state + RAG empty/history 狀態導入。**

這兩個位置最能帶出品牌感，又不會干擾高頻工作區。

---

## 5. UI Copy Audit

以下文案優化同時對齊：
- **激勵的 + 有遠大抱負的**
- **待人以真**
- 不浮誇、不好為人師、不像 consumer SaaS

| Location | Current copy | Improved copy | Why |
|---|---|---|---|
| `login/page.tsx:89-91` | 登入您的帳戶 | 使用奇美帳戶開始今天的會議工作 | 從 generic auth 轉成工作情境，較真實也更有方向 |
| `login/page.tsx:84` | AI 會議助理 | 把每場討論整理成下一步 | 比功能名詞更能對應品牌 slogan「A Step Up」 |
| `DashboardView.tsx:114` | 管理並搜尋所有的會議內容 | 把分散的會議內容整理成可追蹤的進展 | 從工具描述轉成成果描述 |
| `DashboardView.tsx:194` | 搜尋會議標題、關鍵字或參與者... | 搜尋會議標題或摘要重點 | 與目前實際能力一致，避免信任落差 |
| `DashboardView.tsx:281` | 還沒有會議記錄，點擊「新增會議記錄」開始第一場會議 | 上傳第一場會議，30 秒內掌握重點與下一步 | 更具行動感，也修正按鈕名稱已變為上傳音檔 |
| `Sidebar.tsx:145` | 系統運作正常 | 可正常上傳、摘要與查詢 | 從系統視角改為使用者可感知的價值 |
| `Sidebar.tsx:145` | 系統暫時無法連線 | 目前無法連線，請稍後再試；若持續失敗可回報問題 | 更善意，也給下一步 |
| `MeetingCard.tsx:166-167` | 音檔已上傳，等待 AI 開始處理… | 音檔已收到，系統正準備整理本場重點 | 較真誠且少一點機器語氣 |
| `MeetingCard.tsx:170-173` | AI 正在分析會議內容… | 正在整理這場會議的決策、待辦與風險 | 讓等待更具體，建立預期 |
| `MeetingCard.tsx:176-179` | 處理失敗，點擊查看詳情並重試 | 這次整理沒有完成，打開詳情即可查看原因並重新產生 | 更像站在使用者這邊 |
| `ChatPanel.tsx:295` | 正在搜尋文獻並生成回答... | 正在整理相關會議內容並生成回答... | 修正語義錯誤，提升 authenticity |
| `ChatPanel.tsx:143` | 抱歉，發生異常錯誤，無法取得回答。 | 這次查詢沒有順利完成，請稍後再試；若持續失敗可回報問題。 | 有同理心，也提供下一步 |

### Copy tone 補充原則

1. **多寫成果，少寫系統**
   - 寫「整理出下一步」勝過「開始分析」
2. **多寫幫助，少寫指令**
   - 寫「可回報問題」勝過「請聯絡管理員」
3. **避免過度擬人**
   - MeetChi 可溫暖，但不需要像聊天機器人陪伴式人格
4. **避免空泛激勵**
   - 不要寫「讓工作更美好」「提升效率革命」這類無證據口號

---

## 6. Prioritized Optimization Table

| ID | Finding | Evidence | Fix | Priority | Effort | Framework |
|---|---|---|---|---|---|---|
| **BRD-1** | `brand-navy`, `brand-orange`, `brand-green` 與 CHIMEI 官方色偏差過大 | `DDG-CHIMEI.md:49-57`, `globals.css:18-33` | 建立 `brand-chimei-*` 核心 token，並把現行偏移色改為 product accent 命名 | **P0** | M | 品牌手冊、一致性創造信賴感、Color Consistency Lock |
| **BRD-2** | 品牌層與產品互動層未分離，導致「品牌準確性」與「可用性」互相牽制 | `globals.css:18-55` | 採雙層色系：官方色做品牌識別，`brand-cta` 等做產品互動色 | **P0** | M | System Thinking、DDG guideline |
| **BRD-3** | 文案仍偏工具化，尚未承接「激勵的 + 有遠大抱負的」語氣 | `login/page.tsx:83-90`, `DashboardView.tsx:114,281`, `ChatPanel.tsx:295` | 依本報告 copy audit 全面調整關鍵文案 | **P1** | S | 品牌溝通規範、Idea First |
| **BRD-4** | 「本地處理 / 安全 / 可信」雖有訊號，但未成為完整品牌敘事 | `DashboardView.tsx:107-112`, `Sidebar.tsx:140-146` | 將安全說明擴展到上傳後、失敗時、空狀態，讓 trust 成為旅程的一部分 | **P1** | S | 待人以真、處之以善、Real Context |
| **UX-1** | 搜尋欄 promise 與實作不一致 | `DashboardView.tsx:76-79,194-195` | 先改 placeholder，後續若要保留原文案再補 participants / keywords 搜尋 | **P0** | S | Authenticity、Accountability |
| **UX-2** | Dashboard 空狀態沒有 onboarding 力度 | `DashboardView.tsx:276-283`, `design-advisor-audit-2026-06-08.md:37-41` | 補主 CTA、支援格式、30 秒價值說明、粒子 motif 背景 | **P1** | M | Audience + JTBD、Emotion/Friction |
| **UX-3** | RAG failure 與 history failure 沒回到 UI | `ChatPanel.tsx:72-80,139-144` | 加 inline error、retry、錯誤來源說明 | **P1** | M | 處之以善、System Status Visibility |
| **UX-4** | 完成摘要後缺少「A Step Up」成就感與下一步引導 | `MeetingCard.tsx:182-203`, `DashboardView.tsx:177-183` | 完成 toast 改成果導向；MeetingCard / DetailView 加上完成摘要摘要句 | **P1** | M | Xingfu、Idea First, Emotion/Friction |
| **UX-5** | 主視圖缺少人性化 welcome 與情境化引導 | `Sidebar.tsx:117-127`, `DashboardView.tsx:105-115` | 在 dashboard 次標加入簡短、真誠的工作導向 greeting | **P2** | S | Humanist axis、Real Context |
| **VIS-1** | 品牌輔助圖形尚未進入產品，導致品牌深度不足 | 全檔未見 particle motif | 先在 empty state、loading、section divider 導入低對比 particle motif | **P1** | M | CHIMEI auxiliary pattern、Soft Structuralism |
| **VIS-2** | MeetingCard 多色 chip 競爭，削弱結構美感 | `MeetingCard.tsx:36-42,184-202`, `design-audit-2026-06-08.md:74-81` | 降低非關鍵 chip 飽和度，僅保留 icon 或文字色，讓重要狀態才用強色 | **P1** | S | Hierarchy / Contrast / Whitespace、Pre-flight Color Consistency |
| **VIS-3** | focus-visible 不完整，影響 enterprise quality | `globals.css:231-237`, `MeetingCard.tsx:118-126` | 為 button、link、card 補回可見 focus ring；將 card 語意化 | **P0** | M | Accountability、Button Contrast |
| **VIS-4** | 設計系統有 drift 風險，`tailwind.config.ts` 與現行 token 模型並存 | `tailwind.config.ts:21-79`, `DDG-CHIMEI.md:357-358` | 明確標示此檔是否已廢棄；若仍保留則同步到現行 token 命名 | **P2** | S | Consistency + Expectations、DDG single source of truth |
| **VIS-5** | Login 視覺仍偏 OAuth provider UI，而非 CHIMEI 內部產品入口 | `login/page.tsx:100-156` | 強化 CHIMEI account 的主敘事，弱化 provider logo 的視覺主導 | **P2** | M | Audience + JTBD、Hero Discipline |

---

## 7. What NOT to change

以下元素目前方向正確，應保留並在此基礎上升級，不要推倒重來。

1. **`#FAFAF8` 的暖白底與白卡片對比**
   - 已符合 Soft Structuralism，也比冷灰更貼近 CHIMEI 的人文與永續感
   - Evidence: `globals.css:47-53`

2. **深藍 sidebar 作為品牌錨點**
   - 是目前最穩定的品牌辨識來源
   - Evidence: `Sidebar.tsx:43-45,55-66`

3. **DetailView 的單欄垂直 IA**
   - TL;DR → 決策/待辦/風險 → 完整摘要 → 引言 → 逐字稿 的順序很成熟
   - Evidence: `DetailView.tsx:49-62`, `DDG-CHIMEI.md:36-37`

4. **主 CTA 直接做「上傳音檔」**
   - 這比舊式 overloaded dropdown 更符合企業任務流
   - Evidence: `DashboardView.tsx:127-164`

5. **克制動效與帶色相陰影的方向**
   - 已比典型 AI UI 更成熟，不要改成浮誇 motion
   - Evidence: `globals.css:82-95`, `MeetingCard.tsx:121-124`

6. **Inter + Noto Sans TC 的字體組合**
   - 這是中英混排與企業環境的正確方案，不應再頻繁更動
   - Evidence: `globals.css:63-80`, `DDG-CHIMEI.md:95-108`

7. **資料安全保護的訊號**
   - 概念值得保留，只需把敘事做完整
   - Evidence: `DashboardView.tsx:107-112`

---

## 8. Quick Win Implementation Guide

以下 3 項都屬於 **< 30 分鐘**、高影響、低風險的優先改善。

### Quick Win 1：修正文案與真實能力對齊
- **改哪裡**：`DashboardView.tsx`, `MeetingCard.tsx`, `Sidebar.tsx`, `ChatPanel.tsx`, `login/page.tsx`
- **改什麼**：直接套用本報告第 5 節的 copy replacement
- **預估時間**：20-30 分鐘
- **影響**：立即提升 authenticity、善意感與品牌語氣一致性

### Quick Win 2：校正核心品牌色命名
- **改哪裡**：`globals.css`, `docs/design/DDG-CHIMEI.md`
- **改什麼**：新增 `brand-chimei-*` token，將現行偏移色改名為 accent，而不是繼續冒充官方品牌色
- **預估時間**：20-30 分鐘
- **影響**：立刻把「品牌準確性」與「產品延伸」分清楚，後續改版風險大幅下降

### Quick Win 3：升級 Dashboard 空狀態
- **改哪裡**：`DashboardView.tsx`
- **改什麼**：加入主 CTA、支援格式、30 秒價值說明，並放入極淡粒子 motif 背景
- **預估時間**：20-30 分鐘（先做靜態版）
- **影響**：同時補足 onboarding、品牌感與「A Step Up」的第一印象

---

## Final Recommendation

**MeetChi 下一階段不需要大改架構，而是要把「品牌準確性、真實文案、完成感回饋」三件事收斂。**

一旦做到這一步，MeetChi 就會從「好用的內部 AI 工具」升級成「真正代表 CHIMEI 的會議工作介面」。
