# 台語 recall 優化：閉集重正規化 + 不對稱成本實驗（2026-07-15）

> 承接 line#2。以第一性原理 + MECE 分析後，選定兩個「低成本、動 root cause」方案落地。
> 生產 revision：`meetchi-gpu-asr-00094-fxm`。

## 一、第一性原理與 root cause
MMS-LID softmax 攤在 4017 類，台語（nan）機率被近親漢語（cmn/yue/hak/wuu…）稀釋，
即使聲學上 nan 是最佳漢語匹配，top-1 也常輸 cmn → recall 低。

## 二、方案 A：閉集重正規化（closed-set renormalization）
把 MMS-LID 機率遮罩到「這場會議可能出現的語言」`{cmn, nan, eng}` 後重正規化，
nan 只需與華語一對一比，直接解稀釋。閉集模式改以「重正規化後 nan 機率 `nan_prob_cs`」路由。

### 實測（TaigiSpeech 台語 12 段 vs uat03 華語 29 段）
| 指標 | 台語 | 華語 |
|---|--:|--:|
| `nan_prob_cs` mean | **0.761** | **0.003** |
| `nan_prob_cs` max | 0.998 | 0.027 |
| **路由段數（recall / FP）** | **10/12 (83%)** | **0/29 (0%)** |

分離度極大（0.761 vs 0.003），門檻在 0.05–0.5 間皆可完美切開。最終取 `LID_CS_NAN_PROB=0.2`
（華語 max 0.027 的 ~7 倍餘裕）。

### recall 演進
| 判準 | 台語 recall | 華語 FP |
|---|--:|--:|
| top-1 = nan（原始） | 1/12 (8%) | 0/157 |
| nan ∈ top-3 | 7/12 (58%) | 1/157 (0.6%) |
| **閉集重正規化（採用）** | **10/12 (83%)** | **0/29 (0%)** |

## 三、方案 B：不對稱成本實驗（FP 到底貴不貴？）
問題：把華語段誤送 Breeze-26，品質會不會劣化？（決定能否「無腦積極路由」）

方法：對 uat03 華語 120s slice，比較純 Breeze-25 vs 強制 Breeze-26。
（confidence 路徑 threshold=0 → 29 段全送 Breeze-26，僅「信心更高」者替換 3/29。）

### 發現：FP **不是**免費的
被替換的段落中，Breeze-26 **會把華語轉錯且過度自信**，例如：
- `我們除了要符合法規之外`（Breeze-25 正確）→ `我們除了要組合法會之外`（Breeze-26 錯，且信心更高被採用）

→ 結論：**不可無腦積極路由**（會傷華語）。正確策略是「高 recall + 高 precision」，
即方案 A 的閉集重正規化——它給 83% recall 且 0% 華語 FP，恰好避開此劣化風險。

實測旁證：閉集模式下華語 slice **0/29 路由**，逐段文字與 Breeze-25 baseline **完全相同**（diff=0），
華語轉錄零影響。

## 四、最終生產設定與旋鈕
- `LID_ALLOWED_LANGS=cmn,nan,eng`（閉集；空＝停用回全 4017 類）
- `LID_CS_NAN_PROB=0.2`（閉集 nan 路由門檻）
- `TAIWANESE_ROUTING=lid`、`ENABLE_SPECTRAL_GATE=true`
- 回滾：清空 `LID_ALLOWED_LANGS` 即回開集 top-k 行為。

## 五、誠實限制
- 12 段台語樣本偏小；2 段未召回（`nan_prob_cs<0.2`）可能為短/雜訊段。
- 閉集需人工指定可能語言；若某場含此集以外語言（如客語 hak/粵語 yue），需調整 `LID_ALLOWED_LANGS`。
- recall 83% 非 100%；若需更高，下一步可疊 MECE 分析中的「講者條件先驗」或「序列平滑」。
