# MeetChi 開發規劃：逐字稿保真清理（L1）＋ 摘要深度萃取（L4）

> 狀態：**5 題已拍板（2026-07-10，見 §9）**，待實作 ｜ 範圍：**只做**（A）逐字稿保真清理 deletion-only、（B）真實內容深度萃取、（D）L2 講者整合仲裁（Q3 納入）。**不做**網路查證。
> 依據：能力抽取兩份 + 對抗式批判一份 + 現有 code 事實（main c138219+）。本文已把批判的 conflicts / gaps / ordering / missing_tests / residual_risks 全部內化為工程項或紅線。
> 出處：整合自 [`meetchi-deep-report-upgrade.md`](./meetchi-deep-report-upgrade.md)（L1-L5）與 [`meetchi-query-insight-architecture.md`](./meetchi-query-insight-architecture.md)（L6）中「保真清理 + 摘要優化」相關工程；本文聚焦「工程怎麼做」，System Prompt 全文見前兩份文件。
> ⚠️ 行號校正：本文所有 `file:line` 僅供參考，**一律以符號（函式/類別名）定位**——產生本文的分析曾讀到過時副本而誤植行號（P0 已列為強制重定位項）。

---

## 1. 目標與範圍

### 1.1 兩個能力

| 能力 | 一句話目標 | 產物 | 消費者 |
|---|---|---|---|
| **A. 保真清理（L1）** | 在 ASR raw 與下游萃取之間插入 **deletion-only** 清理：刪口語噪音（填充音/口吃/放棄殘句/冗餘接續詞）但語意指紋不變（保留否定/量詞/hedge/語氣/專名/數字） | segment 衍生欄 `text_clean`（raw 不可變） | L2 講者整合、L3 主題切段、L4 摘要、L6 檢索 embedding |
| **B. 摘要深度萃取（L4）** | 把「20-30 字空洞 bullet（長度契約）」升級為「per-topic 100-250 字 thesis-paragraph（資訊契約），完整保留數字/人名/案例/類比，key_quotes 逐字可驗證」 | 富欄位 Chapter：`essence` + `speaker_content{point,elaboration}` + `key_quotes` + `asr_flags` | 詳細頁 L5、查詢綜合 L6 |

### 1.2 明確不做

- **不做網路查證**（no fact-checking against web）。
- L1 **不改字、不修錯字**（那是既有 `correct_segments_glossary_llm` 的職責）。
- L1 **不碰即時字幕/翻譯路徑**——`polish_text` 的即時消費者（`main.py`、`routes/websocket.py`）**維持不動**（見 §2.3 範圍界定，這是批判 conflict #2 的解法）。

### 1.3 一條主軸（貫穿全文的因果鏈）

```
raw(不可變)
  → [glossary 修已知專名錯字]  ── 產生 base 文本
     → [L1 保真清理 deletion-only] ── clean ⊆ base（子序列）
        → text_clean（護欄 fallback 時 = base）
           → L2 講者整合 / L3 主題切段
              → L4 深度萃取（吃 text_clean）
                 → key_quotes ⊆ text_clean（連續子字串）
                    → L5 詳細頁 / L6 檢索（embedding 吃 text_clean）
```

---

## 2. 第一性原理根因

### 2.1 保真清理為何現況做不到

現行 pipeline **無**保真清理步驟。唯一潤飾入口 `polish_text`（以符號定位；current main 約 `llm_utils.py:785`，行號僅供參考）寫的是「潤色更通順」+ `temperature=0.3` + 綁翻譯——這把 autoregressive 模型推向**重寫**而非**刪除**：抹平語氣、調語序、換同義詞、甚至幻覺。三個結構性根因：

1. **契約錯誤**：`polish_text` 目標是「通順」，保真清理目標是「刪噪音但語意指紋不變」，是**相反的最佳化方向**，不能沿用。
2. **schema 保證不了保真**：Gemini FSM validator 只能約束型別/結構，**無法表達「輸出必須是輸入去標點後的子序列」這種跨欄位語意不變式**（與「巢狀 maxItems 會 400、list 上限只能 Python 事後截尾」同一結構性教訓）→ 保真最終防線只能是 Python 後處理。
3. **資料模型缺分離**：segment 目前無「不可變 raw + 衍生 text_clean」分離，清理結果無處安放而不破壞原文。

### 2.2 摘要深度萃取為何現況做不到

現況優化的是**長度契約**而非**資訊契約**，三根因疊加：

1. **契約錯誤**：`SUMMARY_V2_REQUIREMENTS`（`template_engine.py:329`）與 `long_meeting_addendum`（尤其 `:417`「寧可少列重點…精簡優先」）**全是字數/條數約束，沒有一條要求輸出攜帶具體實體** → 模型可 100% 遵守長度卻 0 specifics。
2. **入模前丟資訊**：uniform sampling `lines[::step]`（`llm_utils.py:494`、`multi_pass_summary.py:94,176`）對「嗯對對對」與「預算 500 萬」給**相同保留機率** → specifics 在 prompt 之前就被隨機丟掉，任何 prompt 救不回；`topic_text[:15000]` 硬截（`multi_pass_summary.py:181`）對**最長最重要的 mega-topic 砍最兇**。
3. **無機械保真防線**：`key_quotes` 宣稱「逐字」但無 Python 子字串驗證；`speak_time_pct` 是必填 float（`llm_utils.py:152`）**強迫模型幻覺估算**；`_truncate_summary_lists`（`:397`）用 `val[:cap]` **頭部截尾**砍掉後段高密度單元；Pass2 merge 只餵 `bullets[:5]`（`multi_pass_summary.py:281`）截斷稀釋內容，specifics 在合併層二次流失。

### 2.3 範圍界定（解 conflict #2：objective 自相矛盾）

- L1 **只在批次轉錄 pipeline** 插入（ASR raw segments 之後、`_link_speakers_across_chunks` 之前）。
- `polish_text` 函式**保留不動**，其即時字幕/翻譯消費者不受影響。
- 「取代 polish_text」的正確語意是：**下游 L2/L3/L4 的輸入來源從 raw 改為 text_clean**，而非刪除 `polish_text`。文件與 PR 描述必須用此措辭，避免打斷即時路徑。

---

## 3. 解法總覽（MECE）

### 3.1 能力分解

```
A. 保真清理 L1
├─ A1 EditList schema（取代 PolishResult 作為清理輸出，扁平無巢狀 maxItems）
├─ A2 clean_transcript_fidelity()（Prompt A, temperature=0, deletion-only, 逐段獨立）
├─ A3 verify_edit() 四道 Python 護欄（子序列 / 不可刪 token / 長度下界 / id⊆輸入）
├─ A4 資料模型：segment.text_clean（nullable，raw 不可變）+ alembic
├─ A5 pipeline 整合點（ASR 後、講者/主題切段前）+ 下游改吃 text_clean
├─ A6 glossary 順序界定（raw→glossary→L1→text_clean；驗證參照 = glossary 修正後文本）
└─ A7 冪等卡榫（存已驗證實際輸出，非只存 hash）+ cleaning-coverage 指標

B. 摘要深度萃取 L4
├─ B1 Pass1 → Prompt B 深度萃取（essence + speaker_content + key_quotes + asr_flags）
├─ B2 移除 topic_text[:15000] 硬截 + uniform 抽樣，給足 per-topic 預算
├─ B3 needs_split 真正遞迴切 mega-topic（設深度/主題數上限）
├─ B4 Pass2 → Prompt C（merge 帶 essence + key_quotes 全文，非 bullets[:5]）
├─ B5 單次路徑資訊契約改寫（抗空洞 + 禁用套話黑名單）
├─ B6 entity-preserving 抽樣取代 uniform（單次路徑保底，作用在 text_clean 之上）
├─ B7 speak_time_pct → Optional，移出 LLM，Python 從 diarization 時長回填
├─ B8 key_quotes 子字串驗證護欄（對 text_clean 驗證）
├─ B9 _truncate_summary_lists 改「排序後截尾」（保 specifics）
├─ B10 specificity_density 指標 + 軟閘門 + anchor_hit_rate eval
└─ B11 Chapter schema 新增 SpeakerContent / asr_flags（扁平，不加巢狀 maxItems）

C. 共用地基（批判補齊，兩能力共享）
├─ C1 共用正規化 util（去標點/全半形/CJK/中文數字）供 A3 與 B8 消費同一份
├─ C2 golden fixture + eval 指標（anchor_hit_rate / specificity_density / cleaning-coverage）
├─ C3 segment id 穩定性契約（ASR→L1→L2→L3 join 不斷）
├─ C4 asr_flags 跨層契約（生產端 L1/L4 + 消費端前端 + 與 glossary 去重）
├─ C5 RAG/embedding 欄位切換 + 歷史策略（Q4 定案：以舊會議**音檔重跑**新 pipeline，產生新版產物供新舊 A/B）
└─ C6 每會議成本/呼叫數（Q5 定案：上界**先寬**，先實測單一長會議呼叫數再定）

D. 講者整合仲裁 L2（Q3 定案：本次納入）
├─ D1 融合聲學 cosine（`_link_speakers_across_chunks`, 門檻 0.65）與 LLM `infer_speaker_roles` 成單一 canonical speaker map；仲裁規則：衝突以聲學為主、over-merge≫over-split（預設不合併），門檻先量測 cosine 分布或用 30s overlap 錨點校準（不憑空定）
├─ D2 speaker_content 內容歸屬吃 canonical map（B1 依賴）
└─ D3 speak_time_pct Python 依 canonical map 由 diarization 時長聚合回填（B7 依賴，**產生真實值、不再一律 None**）
```

### 3.2 對照表

| 維度 | A 保真清理 L1 | B 摘要深度萃取 L4 |
|---|---|---|
| 最佳化方向 | **刪**（deletion-only，寧留勿刪） | **展開**（thesis-paragraph，攜帶 specific） |
| LLM 溫度 | `temperature=0` | `temperature=0.2` |
| Gemini schema | `EditList`（新增，扁平） | `Chapter`+`SpeakerContent`（改動，扁平） |
| FSM 風險 | 低（無巢狀 maxItems） | Pass1 無 schema→零風險；單次路徑改 Chapter 須重驗 validator |
| 最終保真防線 | Python `verify_edit` 四道閘 | Python `_verify_key_quotes` 子字串 + specificity 閘 |
| 不變式 | clean ⊆ base（子序列，去標點 CJK） | quote ⊆ text_clean（連續子字串） |
| 主要風險 | 靜默退化為 no-op（全 fallback）；中英夾雜盲區 | per-topic 撞 65535；specificity 重生誤觸發 |
| 依賴關係 | **B 的前置**（B 吃 text_clean） | 依賴 A4/A5 落地與 text_clean 存在 |

---

## 4. 逐字稿保真清理 L1 詳規

### 4.1 Work items

| # | 任務 | 檔案:符號（行號僅參考，**以符號定位**） | 改法 | 風險 |
|---|---|---|---|---|
| A1 | 新增 `EditList` schema | `llm_utils.py`（鄰近 `PolishResult` 定義處） | Pydantic `EditList = {edits: List[Edit]}`、`Edit = {id: str, text: str}`。**刻意不加任何巢狀 maxItems**。與 `PolishResult` 並存，不改 `polish_text` | low |
| A2 | `clean_transcript_fidelity(segments)` | `llm_utils.py`（與 `generate_summary` 同層，**明確不重用** `polish_text`） | Prompt A 走 `config.system_instruction=` 參數（非字串串接）；`response_mime_type=application/json` + `response_schema=EditList`；`temperature=0`；`max_output_tokens≤65535`。輸入 batch **只放同一 speaker、時間相鄰** segment `[{id,text}]`，逐段獨立、禁跨段補全 | medium：prompt 強度需 ground-truth 校準 |
| A3 | `verify_edit(base, clean)` 四道護欄 | `llm_utils.py` 或新 util（緊接 A2） | 見 §4.2；任一違反→丟棄該 edit、fallback base、`logger.warning` | medium：中文 token 清單可能漏判 |
| A4 | `segment.text_clean` 衍生欄 + alembic | backend DB model（segment）+ 新 migration | nullable，raw 不可變不覆寫；未清理/fallback 時 `text_clean = base`；下游一律讀 `text_clean`（無則退回 raw）。**進 git worktree** 隔離，失敗只刪 worktree | high：schema 遷移 |
| A5 | pipeline 整合點 | `tasks.py`（`_link_speakers_across_chunks` 之前）；`multi_pass_summary.py`（Pass0 改吃 clean） | raw segments 後、講者整合/主題切段前呼叫 A2+A3 寫 `text_clean`；Pass0 與後續抽樣一律吃 `text_clean` | medium：確認下游不因欄位切換退化 |
| A6 | glossary 順序界定（解 conflict #3） | `tasks.py` 流程排序 + `correct_segments_glossary_llm`（既有，不改邏輯只定序） | 順序 `raw →（glossary 修已知詞）→ base → L1 刪噪音 → text_clean`。**verify_edit 的子序列參照文本是 base（glossary 修正後），不是 raw** | low |
| A7 | 冪等卡榫 + coverage 指標 | `llm_utils.py` / tasks 狀態表 | 對 A2 昂貴呼叫加狀態卡榫；**存已驗證的實際 text_clean 輸出**（非只存 input hash，因 temperature=0 非位元級確定，residual risk）；regen 設上限不成 retry storm。新增 `cleaning_coverage`（採納 edit 數 / 有噪音段數）指標，全 fallback 時告警 | low-medium |

### 4.2 Python 機械護欄（§保真最終防線，四道閘）

逐 edit 檢查，任一違反即**丟棄該 edit、fallback 回 base 原文、`logger.warning`**：

| 閘 | 規則 | 為何必要 |
|---|---|---|
| **閘1 子序列** | `clean` 去標點後的 CJK 序列必須是 `base` 去標點後的子序列（O(n) 雙指標）。**base = glossary 修正後文本**（非 raw） | 擋改字/換詞/調語序/增字/幻覺 |
| **閘2 不可刪 token 存在性** | `base` 內的否定詞(不/沒/別/沒有)、量詞(只/都/全部)、hedge(可能/應該/大概/好像)、句尾助詞(啦/喔/吧/嘛/耶/齁) 若在 `clean` 消失即 reject | **子序列驗證會放行否定詞刪除給偽安全感**，擋「我不同意→我同意」這類合法子序列但語意災難 |
| **閘3 長度下界** | `len(clean 去標點) < len(base 去標點) * 0.6` 視為過度刪除 → reject | 擋整段被過度刪 |
| **閘4 id⊆輸入** | 輸出 edits 的 id 必須是輸入 id 子集，非法丟棄 | 擋幻覺 id 對不齊 |

> **殘留風險（誠實揭露）**：
> - **英文盲區**：閘2 清單全中文，`I do not agree→I do agree`、`maybe/actually` 刪除**不會被擋**。中英夾雜逐字稿需在 §8 標為已知地板，可選加英文 not/no/never/maybe/actually 清單。
> - **靜默 no-op 退化**：嚴格 token 清單 + 0.6 閘可能讓多數 edit 被 reject → `text_clean≈base`，pipeline「能跑」但零效益。**必須靠 A7 的 `cleaning_coverage` 指標偵測**，否則無訊號。

### 4.3 資料模型（解 conflict #3：三種文本狀態）

實際存在 **raw / glossary 修正後(base) / clean** 三態。決策：

| 方案 | text_clean 的子序列參照 | 儲存欄位 | 優缺點 |
|---|---|---|---|
| **選定：base 參照** | clean ⊆ base（glossary 後） | raw（不可變）+ text_clean；glossary 修正**就地作用於 L1 的輸入 base**，不新增 text_glossary 欄 | ✅ 只加一欄；✅ 閘1 不會被 glossary 改字誤 reject；⚠️ base 非持久化，需在同一 task 內串起 glossary→L1 |
| 方案 B：三欄 | clean ⊆ text_glossary | raw + text_glossary + text_clean | ✅ 血緣完整可回溯；❌ schema 更重、遷移風險更高 |

**選定方案 A**：raw 不可變、只加 `text_clean`（nullable）。glossary 修正在同一批次任務內產生 base 傳入 L1，verify_edit 對 base 驗證。若日後需血緣再升級為方案 B（向後相容）。

### 4.4 Gemini 相容性

- `EditList` **無巢狀陣列 maxItems**（否則 FSM 400）；list 上限（若需）比照 `_truncate_summary_lists` Python 事後截尾。
- `temperature=0` 支援；`response_mime_type=application/json` + `response_schema=EditList`。
- Prompt A 走 `config.system_instruction=` 專屬參數（指令遵從度較高）。
- batch 只放同一 speaker 相鄰段 → **跨講者搬字在 API 呼叫粒度上天然不可能**。
- `max_output_tokens≤65535`（exclusive 65536）；逐段清理單次輸出遠低於上限，不截斷。
- 空段語意：整段只剩噪音時 `text=""` 但**保留該元素**，避免下游 id 對不齊。

---

## 5. 摘要深度萃取 L4 詳規

### 5.1 Work items

| # | 任務 | 檔案:符號（行號僅參考） | 改法 | 風險 |
|---|---|---|---|---|
| B1 | Pass1 → Prompt B | `multi_pass_summary.py`：`PASS1_PROMPT_TEMPLATE`、`_pass1_summarize_topic`、解析後補欄 | 輸出從 `bullets(20-30字)` 改 `essence(2-5條 thesis)` + `speaker_content(多條{point,elaboration}80-250字)` + `key_quotes` + `asr_flags`。每條至少一個可查證 specific。`temperature=0.2`。Pass1 **無 response_schema** → 純 prompt+JSON 解析，零 FSM 風險 | low-medium：需驗 JSON 不截斷 |
| B2 | 移硬截 + 移 uniform | `multi_pass_summary.py`：`topic_text[:15000]`、`topic_lines[::step]`、`max_output_tokens 16384`、MAX_TOKENS 分支 | 刪 `[:15000]` 硬截與 `[::step]` 抽樣；`max_output_tokens` 調高（如 32768，仍 <<65535）；MAX_TOKENS 時**該主題再切半重跑**而非截斷。**必須在 B3 遞迴落地後**才移硬截（見 §6 順序） | medium：需確認不撞 65535 |
| B3 | needs_split 真正遞迴 | `multi_pass_summary.py`：Pass0 後 Pass1 前插入 split；`_pass0_segment_topics` 回傳含 `needs_split` | Pass0 已生 `needs_split` 但 orchestrator 從不讀。對 `needs_split=true` 或 line 跨度過大者遞迴再切，每子主題各有預算。**設遞迴深度上限 + 主題數上限**防呼叫風暴 | medium：主題數↑→Vertex 呼叫↑，需冪等卡榫 |
| B4 | Pass2 → Prompt C | `multi_pass_summary.py`：`PASS2_PROMPT_TEMPLATE`、`_pass2_merge` | 跨主題二階綜合：點名橫跨哪幾個主題、保留講者宣稱標記、誠實少列。**merge 輸入改帶各主題 `essence` 全文 + `key_quotes` 全文，取代 `bullets[:5]` 截斷** | low-medium：merge context 變大但輸出小(~5K) |
| B5 | 單次路徑資訊契約 | `template_engine.py`：`SUMMARY_V2_REQUIREMENTS`、bullets 20-30字、`long_meeting_addendum`（含 `:417`） | bullets 長度契約→具體性契約（每單元至少一個 number/named-entity/case）；加禁用套話黑名單（進行了深入討論/強調重要性/涵蓋多個面向）；深度層**放寬/移除 `long_meeting_addendum` 的「精簡優先/寧可少列」**——長會議走 multi-pass per-topic 而非壓縮單次 | low：需確認 >15K 自動走 multi-pass |
| B6 | entity-preserving 抽樣 | `llm_utils.py`：`generate_summary` `lines[::step]`；`multi_pass_summary.py`：Pass0 sampled | `_entity_preserving_sample()`：對每行以 含數字/中文數字/具名實體/引號/專名 打分，優先保留高訊號、丟填充詞。**作用在 text_clean 之上**（合併 conflict #4：與 A5「改吃 text_clean」為**單一改動**，不 double-edit）。per-topic 路徑優先不抽樣 | medium：中文正則漏判，退化為 uniform 不致命 |
| B7 | speak_time_pct → Optional + Python 回填 | `llm_utils.py`：`SpeakerContribution.speak_time_pct`；`template_engine.py`；`multi_pass_summary.py` Pass2 prompt；回填點 `tasks.py` | `float → Optional[float]=None`；prompt 移除要 LLM 估 `speak_time_pct`；改在 tasks.py 依 **L2 canonical speaker map（D3）** 用 diarization segment 時長 Python 聚合回填。L2 仲裁已納入（Q3）→ 回填**產生真實值**，排在 L2 仲裁 phase 之後 | low schema / medium wiring |
| B8 | key_quotes 子字串驗證 | 新 helper `llm_utils.py`；呼叫點單次 `json.loads` 後、multi-pass `all_quotes` 組裝時 | `_verify_key_quotes(quotes, text_clean)`：quote.text 與 **text_clean**（非 raw，解 conflict #1）各自正規化後，驗證 quote 為 text_clean **連續子字串**；不符丟棄 + `logger.warning` | low-medium：正規化需處理標點/中英/全半形 |
| B9 | _truncate_summary_lists 排序截尾 | `llm_utils.py`：`_truncate_summary_lists`、各層截尾迴圈 | `val[:cap]` 頭部截尾 → **先按 specificity 分數（含數字/具名實體/引號）排序再截尾**；套用 chapters/bullets/key_quotes/**speaker_content**。判準與 B10 共用同一函式 | low |
| B10 | specificity_density + 軟閘門 + anchor | 新函式 `llm_utils.py` 或新 eval 模組；呼叫點 result 組裝後、generate_summary 回傳前 | `compute_specificity_density(units)`：含數字/具名實體單元佔比。**Q5：閾值不硬編**——先在 P0/P2 埋探針量測長會議分布，規劃收斂機制（如取分布分位數）再定；低於閾值 `logger.warning`；重生**預設關閉**（待實測再決定是否啟用 + 「一次上限」+ 會議長度門檻）。另提供 `anchor_hit_rate` 對 golden fixture 供 eval | low：與截尾共用判準 |
| B11 | Chapter schema 富欄位 | `llm_utils.py`：`Chapter`、新增 `SpeakerContent` | `SpeakerContent{point:str, elaboration:str}`；`Chapter` 增 `speaker_content: List[SpeakerContent]=[]` 與 `asr_flags: List[str]=[]`（Optional/default，舊資料不爆）。**扁平不加巢狀 maxItems**；list 上限靠 B9 事後截尾。**與 B7 合併為一批 schema 改動，對 live Gemini validator 一次重驗**（解 conflict #5） | low：影響單次路徑 response_schema |

### 5.2 Prompt 要點（全文放附錄/既有設計文件，此處只列工程契約）

- **Prompt B（Pass1 深度萃取）**：忠實性鐵則 + 具體性契約（每單元攜帶可查證 specific）+ 禁用套話黑名單 + 認知標記（講者口述/前後不一/疑 ASR）+ key_quotes 逐字複製。輸出 `essence + speaker_content{point,elaboration} + key_quotes + asr_flags`。
- **Prompt C（Pass2 二階綜合）**：點名橫跨哪幾個主題、保留講者宣稱標記、無跨主題母題就誠實少列；merge 帶各主題 `essence + key_quotes` 全文（非 `bullets[:5]`）。
- **SUMMARY_V2_REQUIREMENTS**：長度契約→具體性契約；bullets「20-30字」改「每條至少一個 specific」；加禁用套話規則。
- **long_meeting_addendum**：深度層放寬/移除「寧可少列/精簡優先」——由 multi-pass per-topic 分段避免截斷，而非壓縮稀釋。
- 移除各處要 LLM 估 `speak_time_pct` 的指令。
- **注意（gemini_compat）**：認知標記/自我檢查 checklist 在結構化 JSON 輸出下模型只能吐 JSON、無法顯示 checklist → 屬**內部軟引導**；要硬保證需兩段式（生成→自評）多一次呼叫（成本考量，預設不啟用）。

### 5.3 Gemini 相容性（B）

- Vertex ADC + Gemini 2.5-flash-lite；`max_output_tokens` 硬上限 65535（已 clamp）；per-topic 單次輸出 <<65535 是不截斷的關鍵。
- **禁在 schema 加巢狀 array maxItems**（FSM 狀態爆炸 → 400）；`speaker_content` 保持扁平 `List[{point,elaboration}]`，list 上限只能 Python 事後截尾。
- Pass1 用 `response_mime_type=application/json` 但**無 response_schema**（freeform JSON）→ 加 `speaker_content/asr_flags` 只需改 prompt 與解析，**零 FSM 風險**；單次路徑 `generate_summary` 用 `response_schema=Chapter`，改 Chapter 須**重驗 validator**（不加 maxItems）。
- 子字串/具體性/認知標記等跨欄位語意約束 Gemini schema 無法表達 → 只能靠 Python 後處理護欄。

---

## 6. 落地階段（合併排序 + 依賴）

**核心依賴斷言**：**A（保真清理）是 B（摘要萃取）的前置**——B 吃 text_clean，而 text_clean 需 A4（欄位）+ A5（pipeline 寫入）先就緒。若 B 的 prompt 改動先於欄位存在而落地，會跑在 raw 上、eval 無效。

| Phase | 內容 | 依賴 | 主要風險 | DoD（綠燈才 commit `[verified]`） | 回滾 |
|---|---|---|---|---|---|
| **P0 共用地基** | C1 共用正規化 util（去標點/全半形/CJK/中文數字）；C2 golden fixture + eval 指標骨架（anchor_hit_rate / specificity_density / cleaning_coverage）；**以符號重新定位所有 file:line 錨點**（residual risk：行號可能來自不同修訂版，一律以符號確認，勿照行號盲改） | 無 | 正規化判準分歧 | 正規化 util unit test（全半形/中英/中文數字/標點變體判定一致）綠燈；fixture 就緒 | 純新增，刪檔即可 |
| **P1 資料模型（worktree）** | A4 alembic `segment.text_clean`（nullable，raw 不可變）；C3 segment id 穩定性契約（ASR→L1→L2→L3 join 不斷，定義 id 何時可重切併） | P0 | schema 遷移 | migration 正向套用 + raw 不受影響 + 可逆（text_clean 可 null）；worktree 驗證後才併回 | 刪 worktree / migration down |
| **P2 L1 清理核心** | A1 EditList；A2 clean_transcript_fidelity；A3 四道護欄（消費 C1 util）；A6 glossary 順序；A7 冪等卡榫（存實際輸出）+ cleaning_coverage | P0, P1 | prompt 強度、no-op 退化 | 四道護欄 + 清理函式 unit test 綠燈；`py_compile` 過；「我不同意→我同意」被閘2 擋下 | git reset last-green |
| **P3 L1 pipeline 整合** | A5 插入整合點（講者/主題切段前）；下游 Pass0 改吃 text_clean | P2 | 下游退化 | 實跑真實會議：text_clean 讀起來乾淨且忠於講者（人工比對，非只型別/單測） | 整合點加 feature flag 關閉 |
| **P3b L2 講者整合仲裁（Q3 納入）** | D1 融合聲學 cosine + LLM `infer_speaker_roles` 成 canonical speaker map（仲裁：聲學為主、預設不合併、門檻先量測不憑空定）；D2 內容歸屬吃 map | P3（LLM 推斷吃 text_clean） | 門檻未校準 over-split；over-merge 不可逆 | 先量 cosine 分布/用 30s overlap 錨點；真實會議人工比對跨 chunk 同一人歸併正確、無 over-merge | flag 回退至現況雙機制 |
| **P4 摘要 schema（一批重驗）** | B11 SpeakerContent/Chapter 富欄位 + B7 speak_time_pct→Optional，**合併為一次 Gemini validator 重驗**（解 conflict #5） | P1 | FSM 400 歸因錯誤 | 單次路徑 `response_schema=Chapter` 通過 live validator（不加 maxItems）；舊 summary JSON 缺欄讀取不爆 | schema revert |
| **P5 needs_split 遞迴** | B3 遞迴切 mega-topic（深度/主題數上限） | P3, P4 | 遞迴爆炸、呼叫風暴 | 病態 mega-topic fixture：遞迴不超上限、冪等卡榫生效 | flag 關閉遞迴回單主題 |
| **P6 移硬截 + 給預算** | B2 刪 `[:15000]`+`[::step]`、調高 max_output_tokens、MAX_TOKENS 改遞迴。**必在 P5 之後**（先移硬截而無遞迴會灌爆單次撞 MAX_TOKENS） | **P5** | 撞 65535 | MAX_TOKENS 回歸測試：finish_reason 非 MAX_TOKENS、JSON 不截斷 | revert 至硬截 |
| **P7 深度萃取 prompt + 護欄** | B1 Prompt B；B4 Prompt C；B5 單次資訊契約；B6 entity-preserving（作用在 text_clean，與 A5 單一改動）；B8 key_quotes 對 text_clean 驗證；B9 排序截尾；B10 specificity_density。**B9/B10/B11 共用同一 specificity 判準函式** | P6 | 判準分歧、quote 誤丟 | key_quotes 驗證通過率趨近 100%；跨層 quote 測試（text_clean 連續、raw 非連續）通過；specificity_density 達實測收斂值（Q5） | prompt/護欄 revert |
| **P8 講者時長 + 檢索** | B7 Python 由 D3 canonical map 回填 speak_time_pct（真實值）；C5 embedding 改吃 text_clean + 遷移期一致性 | P7, **P3b** | 新舊資料不一致 | speak_time 聚合 ~100%；embedding 切換後檢索不退化 | embedding 雙索引並存 |
| **P9 歷史 A/B（Q4 納入）** | C5 歷史策略：選定舊會議**以音檔重跑**新 pipeline，產生新版產物；對同一音檔做「舊版 ↔ 新版」A/B（anchor_hit_rate / specificity_density / 人工比對） | P7, P8 | 音檔重轉成本、diarization 非決定性致基準漂移 | 至少 1 場長會議舊/新版 A/B 報告產出；量化指標對照可解讀 | 重跑產物存旁路，不覆蓋既有會議 |

> **依賴已解（Q3 定案）**：L2 講者仲裁納入為 **P3b**（不再是懸空依賴）。`speak_time_pct`（B7/D3）與 speaker_content 內容歸屬（D2）皆吃 P3b 的 canonical speaker map，回填**產生真實值**。
> **歷史策略（Q4 定案）**：改為「**以舊會議音檔重跑新 pipeline**」而非只回填 text_clean——因為新版含 L1 清理、深度萃取、L2 仲裁全鏈，只補 text_clean 無法產生可比的新版產物。重跑產物存旁路供 A/B，不覆蓋原會議。注意 diarization 非決定性，重轉的講者切分可能與舊版略異，屬已知基準漂移。

---

## 7. 驗收

### 7.1 Golden fixture

- `tests/fixtures/golden/.../transcript_raw.txt` + `must_capture_anchors.yaml`（錨點 = 數字/人名/類比/宣稱）。
- standard 化的「彙整.md」作為 speaker_content 深度基準（📝 講者原始內容層）。**in-repo 樣本見 [`reference-quality-benchmarks.md`](./reference-quality-benchmarks.md) §1.2**（Answer A/L6 基準見 §2）。

### 7.2 量化指標

| 指標 | 目標 | 能力 |
|---|---|---|
| `subsequence_pass_rate`（子序列 + 不可刪 token 檢查通過比例） | 趨近 100% | A |
| over-clean / under-clean 比例（ground-truth 迷你集） | 達標（強度 light、寧留勿刪） | A |
| `cleaning_coverage`（採納 edit / 有噪音段） | > 下界告警閾（防 no-op 退化） | A |
| 「我不同意→我同意」反轉命題刪除 | 被閘2 擋下 | A |
| speaker_content 字數 | 80-250 字 thesis-paragraph | B |
| `anchor_hit_rate`（must_capture_anchors 命中率） | 較 baseline 明顯上升 | B |
| `specificity_density`（含數字/具名實體單元佔比） | 閾值**待實測收斂**（Q5：先量長會議分布再定，非硬編 0.6） | B |
| `key_quotes` 子字串驗證通過率 | 趨近 100%；假引言被丟棄 | B |
| per-topic `finish_reason` | 非 MAX_TOKENS、JSON 不截斷 | B |
| 跨 chunk 同一人歸併正確率 / over-merge 數 | 正確率高、over-merge=0 | D |

> **eval 變因（Q4 定案處理）**：改以「同一舊會議**音檔重跑**新 pipeline」做舊版↔新版 A/B，兩版吃同一音檔源 → 對照有意義（不再是 clean-only 樣本子集的偏誤對照）。已知限制：diarization 非決定性，重轉的講者切分可能與舊版略異，屬基準漂移；數字對照以 `anchor_hit_rate`/`specificity_density` 為主、輔以人工。

### 7.3 必測清單（含批判補齊的跨層測試）

- **跨層 quote 路徑**：構造「text_clean 連續、raw 非連續」的逐字 quote，斷言對 text_clean 驗證通過、對 raw 驗證失敗（正是 conflict #1 盲點）。
- **正規化等價性**：verify_edit 與 _verify_key_quotes 對全半形數字/中英夾雜/中文數字/標點變體判定一致（黃金對照）。
- **glossary→clean 排序**：某段先 glossary 改字再跑 verify_edit，斷言對 base 驗證通過、不被 raw 子序列誤 reject。
- **L1 護欄誤拒率**：對 70% 是填充音的合法段量測 0.6 閘 + token 清單的誤 reject 率（防靜默全 fallback）。
- **冪等卡榫崩潰/重入**：清理到一半被重試、部分 text_clean 已寫，重跑不重複扣費也不寫壞（**存實際輸出**，temperature=0 非位元確定）。
- **MAX_TOKENS 回歸**：病態 mega-topic 斷言移硬截+調高後 finish_reason 非 MAX_TOKENS。
- **speak_time_pct**：Optional 後讀舊 summary（缺欄）不爆；重疊發言/未知講者聚合 ~100%。

### 7.4 人工實跑（型別/單測通過**不算**最終驗證）

- L1：實跑一場真實會議人工比對——text_clean 乾淨通順無 ASR 冗詞，但用詞語氣論證結構忠於講者。
- L4：實跑對比「彙整.md 📝 講者原始內容」層的深度與保真度。

---

## 8. 風險與限制（誠實）

| 風險 | 說明 | 緩解 |
|---|---|---|
| **ASR 錯誤地板** | L1 deletion-only 不修錯字，ASR 誤植字仍在 text_clean；glossary 只修已知詞，未知誤植留 L4 標 `asr_flags` | 天花板受限於 ASR + glossary，非本案能突破；誠實標記而非猜測 |
| **65K token 預算** | Gemini 硬上限 65535；per-topic 深度輸出上升 | needs_split 遞迴 + MAX_TOKENS 再切半；per-topic 單次仍 <<65535 |
| **模型能力樓地板** | 認知標記/自評 checklist 在 JSON 輸出下只能軟引導；temperature 非 0 有幻覺殘留 | 硬保證需兩段式多一次呼叫（成本，預設不啟用）；靠 Python 護欄兜底 |
| **L1 靜默退化為 no-op** | 嚴格 token 清單 + 0.6 閘 → 全 fallback、零效益且無訊號 | `cleaning_coverage` 指標 + 告警（P2 必含） |
| **中英夾雜盲區** | 閘2 全中文，英文 not/no/maybe/actually 反轉不被擋 | §8 標已知地板；可選加英文清單 |
| **key_quotes 過嚴** | 移標點/助詞後連續子字串過嚴 → 真 quote 大量被丟、key_quotes 稀疏 | 對 text_clean（非 raw）驗證 + 正規化寬鬆化（去標點/全半形） |
| **specificity 重生誤觸發** | 短會/閒聊真低內容也觸發，無效花費 | Q5：重生**預設關閉**，先實測分布規劃收斂機制，再決定是否啟用/閾值/會議長度門檻 |
| **L2 over-merge 不可逆（新增，Q3 納入）** | 把兩人併一人 → 發言張冠李戴、汙染待辦歸屬且不可逆 | 聲學為主、預設不合併、門檻先量測（30s overlap 錨點）；over-split 只是標籤冗餘可修 |
| **遷移可逆性僅 schema 層** | 血緣不可逆：摘要/embedding 已基於 text_clean 落庫後，回退欄位不回退衍生產物 | embedding 雙索引並存；回填 job 可重跑；重要節點快照 |
| **file:line 錨點不可靠** | spec 行號可能來自不同修訂版；照行號盲改會改錯程式碼 | **P0 強制以符號重新定位每個錨點** |
| **成本/延遲上升** | 每會議多 clean batch + needs_split 遞迴 Pass1 + L2 仲裁 + 可選重生；冪等卡榫只擋 retry storm 擋不住基準呼叫量 | Q5：上界**先寬**，先實測單一長會議實際呼叫數（含 needs_split 遞迴 + L2）再定 C6 上界 |

---

## 9. 已拍板決策（2026-07-10）

> [!IMPORTANT] 5 題已由使用者回答，決策如下並已傳播進本文各節。

| # | 問題 | 決策 | 已更新章節 |
|---|---|---|---|
| 1 | key_quotes 驗證基準 | **採「quote 是 text_clean 的連續子字串」**（靠 text_clean⊆base⊆raw 傳遞），不對 raw 直接驗 | §3.2、§4、§5 B8、§7.3 |
| 2 | verify_edit 子序列參照 | **以 base（glossary 修正後）為基準**，非 raw | §4.2 閘1、§4.3、§9-A6 |
| 3 | L2 講者仲裁 | **納入本次範圍** → 新增能力群 **D** + Phase **P3b**；`speak_time_pct`/內容歸屬吃 canonical map、**產生真實值** | §1.1、§3.1 D、§5 B7、§6 P3b/P8 |
| 4 | 歷史資料策略 | **以舊會議音檔重跑新 pipeline**，產生新版產物做「舊版↔新版」A/B（非只回填 text_clean）| §3.1 C5、§6 P9、§7.2 |
| 5 | 成本上界 / specificity 重生 | 上界**先寬**、先實測單一長會議呼叫數再定；`specificity_density` **規劃收斂機制**（先量分布）再定閾值，重生**預設關閉** | §3.1 C6、§5 B10、§7.2、§8 |

### 下一步

- 先做 **P0 共用地基**（正規化 util + fixture + 以符號重定位錨點），並**埋 Q5 的量測探針**（呼叫數、specificity_density 分布）。
- **P1 alembic `text_clean` 進 worktree**（全案硬前置，raw 不可變、可逆）。
- 依 §6 順序推進，嚴守三條依賴紅線：**A 是 B 前置**、**P3b(L2) 先於 P8 回填**、**needs_split 遞迴(P5) 先於移硬截(P6)**。
- 用 P0/P2 探針的實測數據，回填 C6 呼叫數上界與 specificity 收斂閾值（Q5）。