---
description: Web前端開發最佳實踐與設計指南 (基於 skills.sh)
---

# Web Frontend Development Skill

此 Skill 提供 MeetChi 專案的 Web 前端開發指南，整合自 [skills.sh](https://skills.sh) 的頂尖技能。

## 📦 安裝來源

本 Skill 參考以下 skills.sh 技能：

```bash
# Anthropics Frontend Design
npx skills add https://github.com/anthropics/skills --skill frontend-design

# Vercel Web Design Guidelines  
npx skills add https://github.com/vercel-labs/agent-skills --skill web-design-guidelines

# React Best Practices
npx skills add https://github.com/vercel-labs/agent-skills --skill vercel-react-best-practices
```

---

## 🎨 設計思維 (Design Thinking)

在編寫代碼之前，先理解上下文並確定美學方向：

### 1. 理解目的
- 這個界面解決什麼問題？
- 誰是目標用戶？
- 有哪些技術限制？

### 2. 選擇風格方向
選擇一個獨特的美學風格（避免通用 AI 風格）：
- **極簡主義** - 精準、留白、細節
- **未來感** - 漸層、玻璃態、動態
- **雜誌風** - 大膽排版、網格、黑白
- **有機自然** - 柔和曲線、自然色彩
- **奢華精緻** - 金色點綴、serif 字體
- **復古懷舊** - 像素風、霓虹、VHS 效果

### 3. 差異化
**問自己**：這個設計有什麼讓人難忘的地方？

---

## 🚫 避免的設計陷阱

**永遠不要使用**：
- 過度使用的字體：Inter, Roboto, Arial, 系統字體
- 陳腔濫調的配色：紫色漸層配白色背景
- 可預測的佈局和組件模式
- 缺乏上下文特色的餅乾切割設計

---

## ✅ 前端美學指南

### Typography (字體)
```css
/* ✅ 好的做法 - 選擇有特色的字體 */
font-family: 'Space Grotesk', 'Noto Sans TC', sans-serif;

/* ❌ 避免 - 通用字體 */
font-family: Arial, sans-serif;
```

### Color & Theme (色彩)
```css
:root {
  /* 使用 CSS 變數保持一致性 */
  --color-primary: #6366f1;    /* Indigo */
  --color-accent: #f59e0b;     /* Amber */
  --color-surface: #f8fafc;    /* Slate-50 */
  --color-text: #0f172a;       /* Slate-900 */
}
```

### Motion (動態效果)
```css
/* 頁面載入時的交錯動畫 */
.card {
  opacity: 0;
  transform: translateY(20px);
  animation: fadeInUp 0.5s ease forwards;
}

.card:nth-child(1) { animation-delay: 0.1s; }
.card:nth-child(2) { animation-delay: 0.2s; }
.card:nth-child(3) { animation-delay: 0.3s; }

@keyframes fadeInUp {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

### Backgrounds & Effects (背景效果)
```css
/* 玻璃態效果 (Glassmorphism) */
.glass-card {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 16px;
}

/* 漸層背景 */
.gradient-bg {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
```

---

## 🛠️ MeetChi 專案技術棧

### 框架與工具
| 工具 | 版本 | 用途 |
|------|------|------|
| Next.js | 14+ | React 框架 |
| TypeScript | 5+ | 類型安全 |
| TailwindCSS | 3+ | 樣式框架 |
| Lucide React | latest | 圖標庫 |

### 專案結構
```
apps/frontend/
├── src/
│   ├── app/           # Next.js App Router
│   │   ├── page.tsx        # 首頁 (即時字幕)
│   │   ├── dashboard/      # Web Dashboard
│   │   │   └── page.tsx
│   │   └── components/     # 共用元件
│   ├── lib/           # 工具函數
│   └── styles/        # 全域樣式
└── public/            # 靜態資源
```

---

## 📋 開發流程

### 1. 啟動開發服務器
```bash
cd apps/frontend
npm install
npm run dev
```

### 2. 頁面路由
| 路徑 | 功能 |
|------|------|
| `/` | 即時字幕 Overlay |
| `/dashboard` | 會議管理儀表板 |
| `/settings` | 系統設定 |

### 3. API 串接
```typescript
const API_BASE_URL = "http://127.0.0.1:8000/api/v1";

// 獲取會議列表
const response = await fetch(`${API_BASE_URL}/meetings`);
const meetings = await response.json();
```

---

## 🔗 參考資源

- [skills.sh - Agent Skills Directory](https://skills.sh)
- [Vercel Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines)
- [Anthropics Skills](https://github.com/anthropics/skills)
- [TailwindCSS Docs](https://tailwindcss.com/docs)
