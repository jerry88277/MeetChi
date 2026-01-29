# **MeetChi 專案技術架構與實作詳解報告：基於 AdminLTE 與生成式 AI 介面之深度整合**

## **1\. 執行摘要與專案願景**

本報告旨在為「MeetChi」專案提供一份詳盡的技術架構與功能模組設計規範。專案的核心商業需求是構建一個企業級的 AI 對話介面，其前端互動體驗需達到 ChatGPT 或 Google Gemini 的市場標準，同時在系統架構上需沿用 AdminLTE 的成熟管理後台概念，特別是其模組化的佈局與登入驗證機制。

透過 **第一性原理 (First Principles Thinking)** 的解構，我們將對話式 AI 的本質還原為「資料流的即時渲染」與「上下文狀態的持續管理」，這與傳統 AdminLTE 擅長的「靜態資源管理」與「層級化導航」存在設計典範上的衝突。本報告將詳細闡述如何化解此衝突，利用 **MECE (Mutually Exclusive, Collectively Exhaustive)** 原則將系統功能劃分為互不重疊且涵蓋整體的獨立模組。

在技術實作層面，本方案不僅是 UI 的模仿，更將深度整合 **ChatGPT-Next-Web (NextChat)** 的輕量化客戶端架構優勢，以及 **Lobe Chat** 的「超級個體」設定哲學，並將其嵌入 **AdminLTE v4 (Bootstrap 5\)** 的響應式框架中。最終目標是交付一個既具備企業管理後台的穩定性，又擁有頂級 C 端 AI 產品流暢度的混合型應用。

## ---

**2\. 第一性原理與 MECE 架構分析**

在進入程式碼層面的設計之前，必須先從物理與邏輯的底層理解 MeetChi 的構成。

### **2.1 第一性原理：解構 AdminLTE 與 AI 介面的本質衝突**

AdminLTE 的核心設計哲學是「儀表板 (Dashboard)」，其第一性原理是 **「資訊密度的層級化展示」**。它預設使用者需要透過左側樹狀選單 (Treeview) 進入深層頁面，主內容區域 (Content Wrapper) 通常是為了展示表格 (DataTables) 或圖表 (Charts)，其滾動機制是基於整個瀏覽器視窗 (Body Scroll) 1。

相反地，ChatGPT 或 Gemini 的核心設計哲學是 **「基於流的對話 (Stream-based Conversation)」**。其第一性原理是 **「輸入與輸出的線性流動」**。

1. **視窗邏輯**：AI 介面要求「視窗鎖定 (Viewport Constraint)」，即外部框架不滾動，只有中間的對話容器滾動。  
2. **導航邏輯**：側邊欄不再是功能導航，而是「時間軸 (Timeline)」的回溯。  
3. **互動焦點**：傳統 AdminLTE 的焦點在於「瀏覽」，而 AI 介面的焦點在於底部的「輸入框」。

解決方案的核心洞察：  
我們不能直接使用 AdminLTE 的預設佈局。我們必須保留 AdminLTE 的 「骨架 (Shell)」（如 Header, Sidebar Container, Auth Logic），但重構其 「肌肉 (Body)」。具體而言，我們需要將 AdminLTE 的 .content-wrapper 從「被動內容容器」改造為「主動式 Flexbox 應用容器」，以支援全高 (100vh) 的對話流佈局。

### **2.2 MECE 功能模組拆解**

運用 MECE 原則，我們將 MeetChi 系統拆解為四個獨立且窮盡的子系統，確保設計無遺漏且無冗餘：

| 模組領域 (Domain) | 功能組件 (Component) | 核心職責 (Core Responsibility) | 參考開源概念 (Source Inspiration) |
| :---- | :---- | :---- | :---- |
| **基礎設施 (Infrastructure)** | **身份驗證模組 (Auth)** | 處理登入、註冊、OAuth 串接、JWT 權限控管、Session 持久化。 | AdminLTE Login Page v2 3 |
| **導航拓樸 (Topology)** | **佈局引擎 (Layout)** | 管理響應式側邊欄、歷史紀錄列表渲染、底部固定設定入口、RWD 行為。 | AdminLTE Sidebar, Flexbox Utilities 5 |
| **核心互動 (Interaction)** | **對話引擎 (Chat)** | 處理串流 (Streaming) 回應、Markdown 渲染、代碼高亮、輸入框自動伸縮。 | ChatGPT-Next-Web, Lobe Chat 7 |
| **組態管理 (Configuration)** | **設定與狀態 (State)** | 模型參數調整 (Temp/Top-P)、系統 Prompt 設定、介面主題切換、本地存儲同步。 | Lobe Chat Settings, AdminLTE Dark Mode 9 |

## ---

**3\. 基礎設施層：AdminLTE 核心登入模組設計**

客戶明確需求是搭配 AdminLTE 的核心概念建立登入模組。這不僅是 UI 的套用，更是安全架構的基石。

### **3.1 UI 設計與 AdminLTE 整合**

AdminLTE 提供了經典的 login-box 與 card 結構，這非常適合企業級應用。為了符合 AI 產品的現代感，我們將對 AdminLTE v4 的標準登入頁進行「微整形」。

* **佈局策略**：採用 **置中卡片式設計 (Centered Card)**。利用 AdminLTE 的 .login-page class，該 class 內建了 Flexbox 屬性，能確保登入框在任何螢幕尺寸下皆垂直水平置中 3。  
* **視覺優化**：  
  * **背景處理**：標準 AdminLTE 為灰色背景。建議參考 Lobe Chat 的風格，引入 CSS 漸層或動態粒子背景 (Particle.js)，以傳達「智慧」與「運算」的意象 8。  
  * **卡片質感**：使用 .card-outline 與 .card-primary，保留 AdminLTE 的品牌色條，但加入輕微的 box-shadow 與圓角 (Rounded Corners) 調整，使其更接近 SaaS 產品的風格。

### **3.2 登入模組實作細節**

根據 AdminLTE v4 的 DOM 結構，我們構建如下的 HTML 規範：

HTML

\<body class\="login-page bg-body-secondary"\>  
  \<div class\="login-box"\>  
    \<div class\="login-logo"\>  
      \<a href\="../../index2.html"\>\<b\>Meet\</b\>Chi\</a\>  
    \</div\>  
    \<div class\="card card-outline card-primary shadow-lg"\>  
      \<div class\="card-body login-card-body"\>  
        \<p class\="login-box-msg"\>Sign in to start your AI session\</p\>

        \<form action\="/api/auth/login" method\="post"\>  
          \<div class\="input-group mb-3"\>  
            \<input type\="email" class\="form-control" placeholder\="Email"\>  
            \<div class\="input-group-text"\>  
              \<span class\="bi bi-envelope"\>\</span\>  
            \</div\>  
          \</div\>  
          \<div class\="input-group mb-3"\>  
            \<input type\="password" class\="form-control" placeholder\="Password"\>  
            \<div class\="input-group-text"\>  
              \<span class\="bi bi-lock-fill"\>\</span\>  
            \</div\>  
          \</div\>  
          \<div class\="row"\>  
            \<div class\="col-8"\>  
              \<div class\="form-check"\>  
                \<input class\="form-check-input" type\="checkbox" id\="remember"\>  
                \<label class\="form-check-label" for\="remember"\>Remember Me\</label\>  
              \</div\>  
            \</div\>  
            \<div class\="col-4"\>  
              \<button type\="submit" class\="btn btn-primary btn-block"\>Sign In\</button\>  
            \</div\>  
          \</div\>  
        \</form\>

        \<div class\="social-auth-links text-center mt-2 mb-3"\>  
          \<a href\="\#" class\="btn btn-block btn-danger"\>  
            \<i class\="bi bi-google me-2"\>\</i\> Sign in using Google  
          \</a\>  
        \</div\>  
      \</div\>  
    \</div\>  
  \</div\>  
\</body\>

參考來源：3

### **3.3 安全性與狀態管理 (State Management)**

* **JWT 機制**：參考現代 SPA (Single Page Application) 的標準，登入成功後後端應回傳 **JWT (JSON Web Token)**。前端需將此 Token 存儲於 localStorage 或 HttpOnly Cookie 中。  
* **路由守衛 (Route Guard)**：在 AdminLTE 的主佈局加載前，必須先檢查 Token 的有效性。若無效，則強制重導向回上述的 Login Page。這符合 AdminLTE 透過 JavaScript 控制 DOM 渲染的邏輯 12。

## ---

**4\. 導航拓樸層：仿 AI 介面的側邊欄重構**

這是 MeetChi 與傳統 AdminLTE 差異最大的部分。客戶需求明確指出：**「左側面版顯示過往歷史對話紀錄，左下方顯示齒輪圖示作為設定」**。

### **4.1 側邊欄結構的物理改造**

標準 AdminLTE 的側邊欄 (.main-sidebar) 設計用於容納長列表的樹狀菜單 (nav-treeview)，其預設行為是內容過長時整體滾動。若直接將「設定按鈕」放在 HTML 的底部，當對話紀錄變多時，設定按鈕會被推擠到視窗之外，使用者必須滾動到底部才能看到設定，這違反了 AI 介面（設定按鈕應常駐左下角）的 UX 標準。

解決方案：Flexbox 垂直佈局 (The Flexbox Vertical Layout)  
我們必須利用 Bootstrap 5 的 Utility Classes 來重寫側邊欄的內部佈局。

1. **容器 (Wrapper)**：將側邊欄內部容器設定為 Flex Column 模式 (d-flex flex-column)，並強制高度為 100% (h-100)。  
2. **歷史紀錄區 (History Area)**：設定為 flex-grow-1 與 overflow-y-auto。這會讓此區域佔據剩餘的所有空間，且只有此區域內部會發生滾動。  
3. **底部固定區 (Footer Area)**：設定為 mt-auto (Margin Top Auto)。在 Flexbox 邏輯中，這會強制將此元素推至容器的最底部，無論上方內容多少，它都將「釘」在視窗左下角 6。

### **4.2 實作代碼規範**

HTML

\<aside class\="app-sidebar bg-body-secondary shadow" data-bs-theme\="dark"\>  
  \<div class\="sidebar-brand"\>  
    \<a href\="./index.html" class\="brand-link"\>  
      \<img src\="assets/img/logo.png" alt\="MeetChi Logo" class\="brand-image opacity-75 shadow"\>  
      \<span class\="brand-text fw-light"\>MeetChi\</span\>  
    \</a\>  
  \</div\>

  \<div class\="sidebar-wrapper d-flex flex-column" style\="height: calc(100vh \- 57px);"\>  
      
    \<div class\="p-3"\>  
      \<button class\="btn btn-outline-light w-100 text-start d-flex align-items-center"\>  
        \<i class\="bi bi-plus-lg me-2"\>\</i\> New Chat  
      \</button\>  
    \</div\>

    \<div class\="sidebar-menu flex-grow-1 overflow-auto px-2"\>  
      \<ul class\="nav nav-pills nav-sidebar flex-column"\>  
        \<li class\="nav-header text-uppercase text-secondary fs-7"\>Today\</li\>  
        \<li class\="nav-item"\>  
          \<a href\="\#" class\="nav-link"\>  
            \<i class\="nav-icon bi bi-chat-left-text"\>\</i\>  
            \<p\>Project Analysis...\</p\>  
          \</a\>  
        \</li\>  
        \<li class\="nav-item"\>  
          \<a href\="\#" class\="nav-link"\>  
            \<i class\="nav-icon bi bi-chat-left-text"\>\</i\>  
            \<p\>Python Script Help\</p\>  
          \</a\>  
        \</li\>  
      \</ul\>  
    \</div\>

    \<div class\="sidebar-footer mt-auto border-top border-secondary p-3"\>  
      \<a href\="\#" data-bs-toggle\="offcanvas" data-bs-target\="\#settingsOffcanvas" class\="d-flex align-items-center text-decoration-none text-light"\>  
        \<div class\="d-flex align-items-center justify-content-center bg-dark rounded-circle" style\="width:32px; height:32px;"\>  
           \<i class\="bi bi-gear-fill"\>\</i\>  
        \</div\>  
        \<span class\="ms-2"\>Settings\</span\>  
      \</a\>  
      \<div class\="user-panel mt-3 d-flex align-items-center"\>  
        \<div class\="image"\>  
          \<img src\="assets/img/user.jpg" class\="img-circle elevation-2" alt\="User Image"\>  
        \</div\>  
        \<div class\="info ms-2"\>  
          \<a href\="\#" class\="d-block text-white"\>Jerry Chen\</a\>  
        \</div\>  
      \</div\>  
    \</div\>

  \</div\>  
\</aside\>

參考來源：5

### **4.3 歷史紀錄的整合策略**

參考 **ChatGPT-Next-Web** 的優點，我們不應只單純顯示列表。

* **標題生成**：當使用者開啟新對話時，系統應自動調用 LLM 為該對話生成一個 4-6 字的簡短標題，而非顯示 "New Chat" 或第一句話。  
* **分組顯示**：依照時間維度（Today, Yesterday, Previous 7 Days）對歷史紀錄進行分組渲染，這需要前端在接收到後端 JSON 資料後進行日期處理 7。

## ---

**5\. 核心互動層：對話介面 (Chat Interface)**

此模組是使用者的主要工作區。AdminLTE 雖然提供了 Direct Chat 元件，但其功能過於基礎（僅支援純文字與圖片）。我們需要整合 Lobe Chat 與 NextChat 的渲染邏輯。

### **5.1 佈局重構：全高視窗 (Full-Height Viewport)**

傳統 AdminLTE 的 .content-wrapper 會隨內容長度延伸。在 AI 介面中，我們需要鎖定視窗高度。

* **CSS 設定**：.app-main 需設定為 height: 100vh; overflow: hidden; display: flex; flex-direction: column;。  
* **對話流區域**：設定為 flex: 1; overflow-y: auto;。這裡必須引入 **OverlayScrollbars** 插件，這是 AdminLTE 原生支援的，能提供美觀且不佔用佈局寬度的滾動條，確保介面精緻度 16。

### **5.2 訊息渲染與 Markdown 支援**

AdminLTE 的 .direct-chat-msg 結構可以保留，但內容層 (.direct-chat-text) 必須升級。

* **Markdown 解析**：引入 marked.js 或 react-markdown。AI 的回應通常包含標題、列表、粗體等 Markdown 語法，必須在前端即時編譯為 HTML。  
* **代碼高亮 (Syntax Highlighting)**：參考 NextChat，對話中常包含程式碼。必須整合 Prism.js 或 Highlight.js。當 Markdown 解析器偵測到代碼區塊 (Code Block) 時，自動套用高亮樣式，並在右上角添加「Copy」按鈕 7。

### **5.3 串流回應 (Streaming Response) 機制**

為了達到 ChatGPT 的「打字機效果」，前端必須支援串流讀取。

* **技術選型**：使用標準 fetch API 配合 ReadableStream。  
* **實作邏輯**：  
  1. 使用者送出訊息，前端立即在對話流中插入一個「使用者氣泡」。  
  2. 同時插入一個帶有「游標閃爍動畫 (Blinking Cursor)」的空白「AI 氣泡」19。  
  3. 建立 fetch 連線，開啟 response.body.getReader()。  
  4. 進入 while(true) 迴圈讀取 chunk。  
  5. 使用 TextDecoder 解碼並將文字 **增量追加 (Append)** 到 AI 氣泡的 DOM 中。  
  6. 每次追加後，觸發 scrollToBottom() 函式，確保視窗自動滾動到最新內容 21。

### **5.4 輸入框區域設計**

底部輸入框需參考 Lobe Chat 的多功能設計：

* **自動長高**：使用 textarea 並搭配 JS (如 autosize 腳本)，隨內容行數增加高度，最高限制為 5-6 行。  
* **功能鍵整合**：在輸入框左側放置「附件/上傳」按鈕，右側放置「發送」按鈕。  
* **Prompt Masks (面具)**：參考 NextChat，在輸入框上方可選「角色面具」（如：翻譯官、程式專家），這可透過 AdminLTE 的 dropup 選單實作 15。

## ---

**6\. 組態管理層：設定模組與 Lobe Chat 概念整合**

客戶要求「左下方顯示齒輪圖示作為設定」。這不僅是一個按鈕，而是通往「超級個體 (Super Individual)」設定的入口。

### **6.1 Offcanvas (側邊滑出面板) 互動模式**

AdminLTE v4 支援 Bootstrap 5 的 **Offcanvas** 元件。相比於彈出視窗 (Modal)，Offcanvas 從螢幕右側滑出的體驗更符合現代應用，且允許使用者在調整設定的同時預覽對話區的變化（例如切換主題色）23。

### **6.2 設定功能規劃 (參考 Lobe Chat)**

我們將設定面板的內容模組化，分為以下區塊：

1. **模型設定 (Model Settings)**：  
   * **模型選擇**：下拉選單 (GPT-4, Claude 3.5, Gemini Pro)。  
   * **隨機性 (Temperature)**：使用 AdminLTE 的 .custom-range 滑桿，範圍 0-2 1。  
   * **上下文長度 (Context Window)**：滑桿控制，對應 NextChat 的 token 壓縮策略。  
2. **外觀設定 (Appearance)**：  
   * **主題切換**：AdminLTE v4 內建 Dark Mode。透過 JS 切換 html 標籤的 data-bs-theme="dark" 屬性即可實現 10。  
   * **字體大小**：調整對話文字的基礎 rem 值。  
3. **資料管理 (Data)**：  
   * **匯出紀錄**：提供 JSON/Markdown 格式匯出。  
   * **清除所有對話**：危險操作區。

### **6.3 開源優點整合策略**

* **整合 NextChat 的「輕量化」**：預設將對話紀錄存於瀏覽器的 IndexedDB (透過 Dexie.js 封裝)，實現無後端或弱後端的快速啟動體驗。只有在使用者選擇「雲端同步」時才將資料推送到伺服器 7。  
* **整合 Lobe Chat 的「插件生態」**：在設定中預留「插件 (Plugins)」頁籤。雖然初期可能不實作完整插件市場，但可預留架構讓 System Prompt 動態掛載「聯網搜尋」或「畫圖」的指令 8。

## ---

**7\. 技術整合總結與實作路徑**

### **7.1 技術棧清單**

* **核心框架**：AdminLTE v4 (Bootstrap 5.3 \+ Popper.js)  
* **CSS 預處理**：SASS/SCSS (用於覆蓋 AdminLTE 變數，調整主色調為 AI 常見的紫色/青色漸層)。  
* **圖示庫**：Bootstrap Icons (bi) 或 FontAwesome (AdminLTE 預設)。  
* **邏輯層**：Vanilla JS (ES6+) 或輕量級框架 (Vue 3 / React) 嵌入 AdminLTE 頁面。  
* **Markdown 引擎**：marked.js \+ highlight.js。  
* **滾動條**：OverlayScrollbars (AdminLTE 依賴)。

### **7.2 實作步驟建議**

1. **環境建置**：下載 AdminLTE v4 原始碼，配置 Node.js/NPM 環境以編譯 SCSS。  
2. **登入頁開發**：實作 3.2 節的置中卡片佈局，完成 JWT 存儲邏輯。  
3. **佈局重構**：  
   * 移除 AdminLTE 預設的 content-wrapper 滾動行為。  
   * 實作 4.2 節的 Flexbox 側邊欄，確保齒輪圖示釘在底部。  
4. **對話引擎開發**：  
   * 建立串流 Fetch 函式。  
   * 整合 Markdown 渲染樣式，確保氣泡內的表格與代碼區塊顯示正常。  
5. **設定模組整合**：實作 Offcanvas 面板，並綁定 Dark Mode 切換功能。

### **7.3 結論**

MeetChi 專案並非單純的「套版」，而是一次基於 AdminLTE 強大骨架的「器官移植」工程。透過將 AdminLTE 的穩定佈局 (Layout) 與 ChatGPT-Next-Web 的動態資料流 (Data Flow) 以及 Lobe Chat 的設定深度 (Configuration Depth) 相結合，我們將能交付一個既符合企業管理規範，又具備頂級 AI 操作體驗的現代化平台。此架構不僅滿足了客戶對於歷史紀錄與設定入口的具體需求，更為未來的插件擴充與多模型切換預留了彈性空間。

---

**表格 1：MeetChi 與傳統 AdminLTE 及競品功能對比**

| 功能維度 | 傳統 AdminLTE | ChatGPT-Next-Web | MeetChi (本方案) |
| :---- | :---- | :---- | :---- |
| **導航模式** | 多層級樹狀菜單 | 左側線性列表 | **左側線性列表 \+ 底部固定功能區** |
| **視窗滾動** | 瀏覽器整體滾動 (Body Scroll) | 內部容器滾動 (Div Scroll) | **全高鎖定 \+ 內部 OverlayScrollbars** |
| **資料載入** | AJAX 全頁/表格刷新 | 串流 (Streaming) 增量渲染 | **Fetch Streams \+ Markdown 即時解析** |
| **設定入口** | 頂部 Navbar 下拉選單 | 獨立設定頁面/Modal | **側邊欄底部固定 (參照 Gemini/Lobe)** |
| **視覺風格** | 扁平化、資訊密集 | 極簡、留白 | **AdminLTE 結構 \+ AI 漸層美學** |

此設計文件已涵蓋從底層原理到代碼實作的所有關鍵環節，可直接交付開發團隊進行 Sprint 規劃。

#### **引用的著作**

1. Layout | AdminLTE v3 Documentation, 檢索日期：1月 17, 2026， [https://adminlte.io/docs/3.1/layout.html](https://adminlte.io/docs/3.1/layout.html)  
2. Layout | AdminLTE 3 Documentation, 檢索日期：1月 17, 2026， [https://adminlte.io/docs/3.0/layout.html](https://adminlte.io/docs/3.0/layout.html)  
3. AdminLTE 4 | Login Page, 檢索日期：1月 17, 2026， [https://adminlte.io/themes/v4/examples/login.html](https://adminlte.io/themes/v4/examples/login.html)  
4. login.html \- kenhyuwa/modern-adminlte \- GitHub, 檢索日期：1月 17, 2026， [https://github.com/kenhyuwa/modern-adminlte/blob/master/login.html](https://github.com/kenhyuwa/modern-adminlte/blob/master/login.html)  
5. Main Sidebar Component | AdminLTE 4, 檢索日期：1月 17, 2026， [https://adminlte.io/themes/v4/docs/components/main-sidebar.html](https://adminlte.io/themes/v4/docs/components/main-sidebar.html)  
6. AdminLTE 4 | General UI Elements, 檢索日期：1月 17, 2026， [https://adminlte.io/themes/v4/UI/general.html](https://adminlte.io/themes/v4/UI/general.html)  
7. Introduction to ChatGPT Next Web (NextChat) \- DataCamp, 檢索日期：1月 17, 2026， [https://www.datacamp.com/tutorial/introduction-to-chatgpt-next-web-nextchat](https://www.datacamp.com/tutorial/introduction-to-chatgpt-next-web-nextchat)  
8. LobeChat: A Deep Dive into the Ultimate AI Productivity Hub, 檢索日期：1月 17, 2026， [https://skywork.ai/skypage/en/LobeChat-A-Deep-Dive-into-the-Ultimate-AI-Productivity-Hub/1976182835206221824](https://skywork.ai/skypage/en/LobeChat-A-Deep-Dive-into-the-Ultimate-AI-Productivity-Hub/1976182835206221824)  
9. LobeChat Feature Development Complete Guide \- LobeHub, 檢索日期：1月 17, 2026， [https://lobehub.com/docs/development/basic/feature-development](https://lobehub.com/docs/development/basic/feature-development)  
10. Color Mode | AdminLTE 4, 檢索日期：1月 17, 2026， [https://adminlte.io/themes/v4/docs/color-mode.html](https://adminlte.io/themes/v4/docs/color-mode.html)  
11. admin-lte \- UNPKG, 檢索日期：1月 17, 2026， [https://app.unpkg.com/admin-lte@3.1.0/files/pages/examples/login.html](https://app.unpkg.com/admin-lte@3.1.0/files/pages/examples/login.html)  
12. Introduction | AdminLTE 4, 檢索日期：1月 17, 2026， [https://adminlte.io/themes/v4/docs/introduction.html](https://adminlte.io/themes/v4/docs/introduction.html)  
13. Fixed Footer \- AdminLTE 4, 檢索日期：1月 17, 2026， [https://adminlte.io/themes/v4/layout/fixed-footer.html](https://adminlte.io/themes/v4/layout/fixed-footer.html)  
14. Add fixed footer to bottom of the sidebar \- Okler Themes, 檢索日期：1月 17, 2026， [https://www.okler.net/forums/topic/add-fixed-footer-to-bottom-of-the-sidebar/](https://www.okler.net/forums/topic/add-fixed-footer-to-bottom-of-the-sidebar/)  
15. ChatGPTNextWeb/NextChat: Light and Fast AI Assistant ... \- GitHub, 檢索日期：1月 17, 2026， [https://github.com/ChatGPTNextWeb/NextChat](https://github.com/ChatGPTNextWeb/NextChat)  
16. \[BUG\] Login pages have JavaScript errors due to no sidebar · Issue \#5011 · ColorlibHQ/AdminLTE \- GitHub, 檢索日期：1月 17, 2026， [https://github.com/ColorlibHQ/AdminLTE/issues/5011](https://github.com/ColorlibHQ/AdminLTE/issues/5011)  
17. overlayscrollbars \- NPM, 檢索日期：1月 17, 2026， [https://www.npmjs.com/package/overlayscrollbars](https://www.npmjs.com/package/overlayscrollbars)  
18. awesome-ml/llm-tools.md at master \- GitHub, 檢索日期：1月 17, 2026， [https://github.com/underlines/awesome-ml/blob/master/llm-tools.md](https://github.com/underlines/awesome-ml/blob/master/llm-tools.md)  
19. CSS Text Animations: 40 Creative Examples to Try \- Prismic, 檢索日期：1月 17, 2026， [https://prismic.io/blog/css-text-animations](https://prismic.io/blog/css-text-animations)  
20. Typewriter Effect \- CSS-Tricks, 檢索日期：1月 17, 2026， [https://css-tricks.com/snippets/css/typewriter-effect/](https://css-tricks.com/snippets/css/typewriter-effect/)  
21. Using readable streams \- Web APIs | MDN, 檢索日期：1月 17, 2026， [https://developer.mozilla.org/en-US/docs/Web/API/Streams\_API/Using\_readable\_streams](https://developer.mozilla.org/en-US/docs/Web/API/Streams_API/Using_readable_streams)  
22. Flask Streaming Langchain Example \- GitHub Gist, 檢索日期：1月 17, 2026， [https://gist.github.com/python273/563177b3ad5b9f74c0f8f3299ec13850](https://gist.github.com/python273/563177b3ad5b9f74c0f8f3299ec13850)  
23. Offcanvas · Bootstrap v5.0, 檢索日期：1月 17, 2026， [https://getbootstrap.com/docs/5.0/components/offcanvas/](https://getbootstrap.com/docs/5.0/components/offcanvas/)  
24. Creating Offcanvas Sidebar with Bootstrap 5 \- Wappler Documentation, 檢索日期：1月 17, 2026， [https://docs.wappler.io/t/creating-offcanvas-sidebar-with-bootstrap-5/31927](https://docs.wappler.io/t/creating-offcanvas-sidebar-with-bootstrap-5/31927)