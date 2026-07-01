# 模組稽核：模板管理（四角色）

> 日期：2026-06-30
> 範圍：Gallery → 卡片動作（預覽/複製/編輯/刪除）→ Fork 流程 → TemplateEditor → 上傳/重生的模板選用 → 系統模板
> 角色：🟢新手 / 🟡一般 / 🔴專業 / 🧊冷啟動
> 主要檔案：`components/TemplateGallery.tsx`（含內嵌 TemplateEditor）、`components/DetailView.tsx`、`components/DashboardView.tsx`、`app/dashboard/page.tsx`、`lib/api.ts`、`Sidebar.tsx`
> 後端基準：`apps/backend/app/routes/templates.py` 已具 auth/owner 隔離/軟刪除/instruction 500 字上限/usage check（前端僅部分反映）

---

## 0. 架構觀察
- 模板放在 Sidebar「系統」分組（`Sidebar.tsx:49`），非工作區 → 影響摘要結果的核心功能發現性低。
- **三處各自獨立 `getTemplates()`**：Gallery（`TemplateGallery.tsx:47-58`）、Dashboard（`page.tsx:137-140`）、DetailView（`DetailView.tsx:104-108`）→ 無共享 store，新建/複製後其他畫面不更新。
- **後端有能力、前端沒接齊**：owner「我的/共享」概念、is_active 開關、instruction 500 字上限在前端皆未呈現。

---

## 1. 四角色旅程重點
- 🧊冷啟動：在「系統」分組找到模板；預覽只看到段落標題＋LLM 指令片段，**無範例輸出**，仍想不出實際摘要長相。
- 🟢新手：複製模板後**停留在列表、卡片在最尾端**，不知下一步；想自訂卻面對 `output_key`/`output_type`/「LLM 指令」等技術欄位。
- 🟡一般：**上傳時根本無法選模板**（永遠 general），自訂模板只能事後在詳情頁重生時才用到；無「設為預設」。
- 🔴專業：無從零建模板（只能 fork/edit）；編輯器無驗證、無 500 字提示、取消不確認、存檔無回饋；系統模板無法停用，9 個永遠塞滿選單。

---

## 2. 問題清單（六維度；P0/P1/P2 + 角色 + 佐證 + 修法）

### A. 功能正確性
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| T-A1 | **上傳流程無法套用模板**，props 未渲染，永遠用 general | **P0** | 全 | `DashboardView.tsx:57,139-189`；`page.tsx:124,451` | 上傳設定加模板選擇（與上傳模組 U-A2 同源） |
| T-A2 | **三處獨立 getTemplates，新建/複製後 Dashboard/DetailView 不更新** | P1 | 一般/專 | `TemplateGallery.tsx:47-58`、`page.tsx:137-140`、`DetailView.tsx:104-108` | 提取共享 store/context 或建立後廣播刷新 |
| T-A3 | 動態 Tailwind 顏色 class `bg-${tpl.color}/15` 生產建置可能被 purge，圖示底色失效 | P1 | 全 | `TemplateGallery.tsx:213` | 改 safelist 或對應靜態 class map |
| T-A4 | 無「從零建立新模板」入口（createTemplate 僅 fork 用） | P1 | 專/一般 | `TemplateGallery.tsx:79` | 加「+ 新增模板」進空白編輯器 |
| T-A5 | 編輯器不開放 icon/color，fork 後外觀無法調整 | P2 | 一般/專 | `TemplateGallery.tsx:412-438`（DTO 有但 UI 無） | 編輯器補 icon/color 選擇 |
| T-A6 | 搜尋對 tag 大小寫敏感、對名稱/描述不敏感 | P2 | 一般 | `TemplateGallery.tsx:65-67` | tag 比對也 toLowerCase |

### B. 流程可用性
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| T-B1 | Fork 完停留列表、卡片附加尾端、不進編輯器，後續調整斷裂 | P1 | 新/冷 | `TemplateGallery.tsx:88-90` | Fork 後 toast＋詢問「立即編輯？」或捲動定位新卡片 |
| T-B2 | **無「設為我的預設模板」** | P1 | 一般/專 | 全 codebase 無 default 概念；`page.tsx:124` 寫死 general | 加「⭐設為預設」存 user preference，上傳時帶入 |
| T-B3 | 編輯器無儲存中/成功回饋（toast），存完默默回列表 | P1 | 全 | `TemplateGallery.tsx:113-121` | 加 loading＋成功 toast |
| T-B4 | 刪除兩段式，第一框不含使用數，且兩框視覺相近易誤點 | P1 | 一般/專 | `TemplateGallery.tsx:97-112,306-331` | 第一框就顯示使用數，或合併為單一含使用數對話框 |
| T-B5 | 預覽無範例輸出，難想像實際摘要 | P1 | 冷/新 | `TemplateGallery.tsx:294-301` | 加「範例輸出」或用既有會議 dry-run 預覽 |
| T-B6 | 模板藏在 Sidebar「系統」分組，發現性低 | P2 | 冷/新 | `Sidebar.tsx:48-53` | 移到工作區或上傳流程內顯著入口 |

### C. 邊界與錯誤處理
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| T-C1 | **編輯器無前端驗證**（空名稱/空段落/空或重複 output_key 都可送） | P1 | 全 | `TemplateGallery.tsx:397-405` | 送出前驗證並標紅提示 |
| T-C2 | instruction 500 字上限 UI 未呈現（無 maxLength/計數器），送出才吃後端錯 | P1 | 一般/專 | `TemplateGallery.tsx:489-491`（後端有限） | 加字數計數器＋maxLength |
| T-C3 | 取消編輯無 dirty-check/離開確認，直接丟棄修改 | P1 | 全 | `TemplateGallery.tsx:129-130,409` | 有變更時彈「放棄修改？」 |
| T-C4 | fork/save/delete 失敗都套頂層「模板載入失敗」標題，文案誤導 | P2 | 一般/專 | `TemplateGallery.tsx:90,109,119,189-191` | 分開錯誤狀態／用 toast |
| T-C5 | 空狀態不分「搜尋無結果」vs「分類為空」，無引導 CTA | P2 | 冷/新 | `TemplateGallery.tsx:273-280` | 分流文案＋「複製一個開始」CTA |

### D. 一致性
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| T-D1 | Gallery 不濾 is_active，DetailView/下游濾 is_active，清單不一致 | P1 | 一般/專 | `TemplateGallery.tsx:61-69` vs `DetailView.tsx:344,722` | 統一過濾規則 |
| T-D2 | DetailView 桌面自訂下拉 vs mobile 原生 select 兩套 UI | P2 | 一般 | `DetailView.tsx:332-360` vs 717-726 | 抽共用元件 |
| T-D3 | 自訂模板無「我的/自訂」徽章，僅系統模板有徽章，辨識不對稱 | P2 | 一般/新 | `TemplateGallery.tsx:218-220` | 自訂模板加「我的」徽章 |
| T-D4 | 內部 fork vs UI「複製」、output_key/type 英文 vs 其餘中文，語彙混雜 | P2 | 新/冷 | `TemplateGallery.tsx:73,481-485` | 隱藏技術欄位/統一用語 |

### E. 信任與安全感
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| T-E1 | 刪除文案「刪除後可聯繫管理員還原」暗示 soft delete 但無自助還原 | P1 | 一般/專 | `TemplateGallery.tsx:310` | 提供「已刪除/封存」清單可自助還原，或明說「30天內可請 IT 還原」 |
| T-E2 | 第一刪除確認不顯示「已被 N 場會議使用」，使用者不知情下確認 | P1 | 一般/專 | `TemplateGallery.tsx:306-317` | 第一框即帶使用數 |
| T-E3 | 系統模板無法停用/隱藏，清單可控性不足 | P1 | 一般/專 | `TemplateGallery.tsx:249` + 編輯器無 is_active | 提供「隱藏不用的系統模板」（個人偏好層） |
| T-E4 | 把「LLM 指令/output_key/output_type」直接攤給使用者，非技術者易誤改壞模板 | P1 | 新/冷 | `TemplateGallery.tsx:480-490` | 提供「簡易模式」（只填標題＋說明），技術欄位收進進階 |

### F. 非功能面（效能/RWD/A11y）
| # | 問題 | 級 | 角色 | 佐證 | 建議修法 |
|---|------|----|------|------|---------|
| T-F1 | 所有 modal 無 focus-trap、無 Esc 關閉（已有 useEscape 未用） | P1 | a11y | `TemplateGallery.tsx:283-360` | 套 useEscape＋focus trap |
| T-F2 | 刪除鈕純圖示（有 aria-label 但視覺弱） | P2 | 一般/新 | `TemplateGallery.tsx:261-264` | 加文字或更明確圖示 |
| T-F3 | 編輯器 mobile 雙欄（title/output_key）窄螢幕擠壓 | P2 | RWD | `TemplateGallery.tsx:479` | 窄螢幕改單欄 |
| T-F4 | 顏色動態 class 若 purge，連帶影響對比/可辨識 | P2 | a11y | `TemplateGallery.tsx:213` | 同 A3 |
| T-F5 | 預覽指令硬截斷 100 字無展開 | P2 | 專 | `TemplateGallery.tsx:300` | 加「展開」 |
| T-F6 | usage_count 以 `(tpl as any)` 取值，型別繞過 | P2 | 技術債 | `TemplateGallery.tsx:231` | 納入 TemplateDTO 型別正規取值 |

---

## 3. 本模組整合優先級
- **P0（1）**：T-A1 上傳無法套用模板（模板價值在主流程被埋沒）。
- **P1（~15）**：getTemplates 不同步、Tailwind purge、從零建模板、設為預設、Fork 後流程、儲存回饋、刪除使用數/兩段式、範例輸出、編輯器驗證、500字提示、取消確認、is_active 過濾一致、刪除還原語意、系統模板停用、技術欄位簡易模式、modal focus/Esc。
- **P2（~12）**：icon/color、搜尋大小寫、錯誤標題、空狀態分流、雙份下拉、自訂徽章、語彙統一、刪除鈕視覺、RWD 擠壓、預覽展開、型別債。

**最關鍵三項**：T-A1（上傳套不到模板＝功能價值被埋）、T-A2（建立後不同步）、T-E4/B5（技術欄位門檻＋無範例＝非技術者用不起來）。
