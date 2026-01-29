# **基於 Rust 與 Tauri 之即時演講稿同步系統：從第一性原理至強制對齊演算法的深度架構報告**

## **1\. 執行摘要與第一性原理拆解**

本報告旨在針對 jerry88277/MeetChi 專案的核心概念進行深度解構，並為特定的「長官致詞即時英文同步顯示」需求提出完整的工程解決方案。不同於傳統的自動語音辨識（Automatic Speech Recognition, ASR）應用，本案例的本質並非「轉錄未知語音」，而是「已知文本的時間序列對齊」（Temporal Alignment of Known Text）。這將問題的維度從開放詞彙的無限搜尋空間，收斂至單一腳本路徑的線性搜尋空間，從而允許我們在延遲（Latency）與準確度（Accuracy）之間取得極致的平衡。

### **1.1 第一性原理（First Principles）分析**

若我們剝除所有現有的軟體框架與技術名詞，回歸物理與資訊的本質，此系統的運作建立在以下幾個基本真理之上：

1. **聲音是時間壓力的連續函數**：輸入端是空氣壓力隨時間變化的連續訊號，經由麥克風取樣轉化為離散的數位訊號（PCM）。我們的任務是在這條時間軸上，尋找與預定義文本特徵最相符的點 1。  
2. **腳本是唯一的真值（Ground Truth）**：與一般會議記錄不同，致詞者的內容已被嚴格定義。任何偏離腳本的語音（如咳嗽、重複、插話）皆視為雜訊而非資訊。系統的目標函數（Objective Function）應是最小化「預測位置」與「真實閱讀位置」之間的誤差，而非最大化轉錄文字的準確率 2。  
3. **對齊是概率分佈的坍縮**：在任意時間點 $t$，致詞者位於腳本索引 $i$ 的機率 $P(i|Audio\_t)$ 是一個分佈。隨著語音特徵（聲學特徵或解碼出的 Token）的累積，此分佈應迅速坍縮至單一峰值。我們的演算法核心即是加速此坍縮過程並保持其穩定性 3。  
4. **即時性是感知的閾值**：人類對於「即時」的感知約在 200 毫秒以內。若視覺回饋（英文翻譯的捲動）落後語音超過此閾值，將產生認知失調。因此，系統架構必須採用串流（Streaming）處理，而非批次（Batch）處理 5。

### **1.2 MECE 原則下的系統邊界劃分**

運用 MECE（Mutually Exclusive, Collectively Exhaustive，相互獨立、完全窮盡）原則，我們可以將 MeetChi 的既有架構重組，並識別出為滿足客戶需求所需填補的技術缺口。

| 系統模組 | MECE 定義與職責 | MeetChi 現狀 | 客戶需求之差距 (Gap Analysis) |
| :---- | :---- | :---- | :---- |
| **感測層 (Sensing)** | **窮盡性**：負責所有音訊的採集、緩衝、降噪與人聲偵測 (VAD)。 **獨立性**：不涉及任何語言解碼，僅輸出純淨的語音幀。 | 使用 cpal 進行音訊採集，具備基礎 VAD 功能。 | 需強化對「非語音片段」的過濾邏輯，避免靜音導致的 ASR 幻覺（Hallucination）影響對齊判斷 7。 |
| **解碼層 (Decoding)** | **窮盡性**：負責將聲學特徵轉換為語言特徵（Tokens 或 Logits）。 **獨立性**：不關心腳本內容，僅客觀輸出聽到的聲音內容。 | 整合 Whisper 模型，進行語音轉文字。 | 原生 Whisper 為 30 秒窗口設計，需改造為滑動窗口（Sliding Window）串流模式以降低延遲 9。 |
| **對齊層 (Alignment)** | **窮盡性**：負責將解碼層的輸出與預存腳本進行比對，計算最佳匹配位置。 **獨立性**：此為新增模組，獨立於 Whisper 之外。 | **無**（原專案為純轉錄）。 | **關鍵缺口**。需實作 Smith-Waterman 或 DTW 演算法，在噪音與錯誤中鎖定腳本位置 11。 |
| **狀態層 (State)** | **窮盡性**：維護中英對照腳本、當前游標位置、信心指數。 **獨立性**：作為前後端溝通的唯一真理來源（Source of Truth）。 | 簡單的文字儲存。 | 需建立雙語映射結構，處理「一句中文對多句英文」或「倒裝」的複雜對應關係。 |
| **呈現層 (Presentation)** | **窮盡性**：負責英文翻譯的渲染、高亮與自動捲動。 **獨立性**：不處理邏輯，僅反應狀態層的變化。 | Tauri 前端介面。 | 需實作基於 React 的平滑捲動（Smooth Scrolling）與視覺聚焦邏輯 13。 |

基於上述分析，本報告將詳細展開各層級的技術實作細節，重點在於如何利用 Rust 的高效能與安全性（Memory Safety）來構建一個低延遲的「強制對齊引擎」（Forced Alignment Engine）。

## **2\. 核心技術堆疊與 MeetChi 專案解構**

MeetChi 專案採用了 Rust 作為後端核心，Tauri 作為應用程式框架，並整合 OpenAI 的 Whisper 模型進行語音識別。這是一個極具現代化且高效的技術組合，特別適合本案所需的桌面端高效能運算。

### **2.1 Rust 與 Tauri 的戰略優勢**

在處理音訊串流與神經網路推論（Inference）時，Python 雖有豐富生態系，但其全域直譯器鎖（GIL）與記憶體管理機制往往導致不可預測的延遲（GC Pauses）。Rust 提供了無 GC 的記憶體管理與零成本抽象（Zero-cost Abstractions），能確保音訊回調（Audio Callback）與模型推論的實時性 15。

Tauri 的架構設計將前端（WebView）與後端（Rust）分離，透過 IPC（Inter-Process Communication）進行通訊。這種設計使得 UI 層可以使用成熟的 Web 技術（如 React, CSS）來處理複雜的文本排版與動畫，而將計算密集的對齊邏輯保留在 Rust 層，完美符合 MECE 的職責分離原則 17。

### **2.2 Whisper 模型的特性與限制**

Whisper 是一個基於 Transformer 架構的編碼器-解碼器（Encoder-Decoder）模型。其訓練數據量龐大（680k 小時），具有極佳的抗噪能力與多語言支援。然而，針對本案的「即時對齊」需求，Whisper 存在先天限制：

1. **自回歸解碼（Auto-regressive Decoding）**：Whisper 傾向於讀取較長的音訊片段（Context）後才生成文字，這會帶來數秒的延遲。  
2. **幻覺（Hallucination）**：在長時間靜音或背景雜訊下，Whisper 容易生成不存在的語句 19。  
3. **時間戳記的不精確性**：雖然 Whisper 支援輸出時間戳記，但其顆粒度通常在語句層級，對於單字層級的即時對齊可能不夠精細。

因此，我們的解決方案不能直接使用「開箱即用」的 Whisper，而必須透過 whisper-rs 進行底層控制，採用**編碼器特徵提取**或**短窗口串流推論**的策略 9。

## **3\. 線上強制對齊演算法：從理論到實踐**

這是本系統最核心的「大腦」。不同於 ASR 試圖從聲音還原文字，我們是拿聲音（或其轉錄結果）去「搜尋」已知文本。這是一個典型的字串搜尋或序列對齊問題，但必須在「線上」（Online/Streaming）環境下運作。

### **3.1 演算法選型：Needleman-Wunsch vs. Smith-Waterman vs. DTW**

在生物資訊學與訊號處理領域，序列對齊有三大經典演算法，我們需依據本案特性進行決策：

1. **Needleman-Wunsch (全域對齊)**：  
   * **原理**：試圖將序列 A 的全部與序列 B 的全部進行最佳匹配。  
   * **適用性**：**低**。因為致詞者的語音（序列 A）只是整個腳本（序列 B）的一小部分。強迫將 3 秒的語音對齊到 30 分鐘的腳本會導致極大的誤差 21。  
2. **Smith-Waterman (局部對齊)**：  
   * **原理**：在長序列 B 中尋找與短序列 A 最相似的子片段。容許序列兩端存在不匹配的部分（Gap）。  
   * **適用性**：**極高**。這正是我們的需求：在長篇講稿中，找到長官剛剛念出的那一句話。它能容忍長官跳過某段文字（Gap Penalty）或念錯字（Mismatch Penalty） 12。  
3. **Dynamic Time Warping (DTW, 動態時間校正)**：  
   * **原理**：計算兩個時間序列的相似度距離，允許時間軸的非線性扭曲。通常用於聲學特徵（如 MFCC 或 Mel-spectrogram）的直接比對。  
   * **適用性**：**中**。雖然 DTW 是對齊的黃金標準，但在長序列上的運算複雜度為 $O(N^2)$，且純聲學比對容易受到口音、語速與環境噪音的干擾。若使用 Whisper 輸出的 Token 進行 DTW，則效果與 Smith-Waterman 類似，但實作較為複雜 25。

**決策**：採用 **基於滑動窗口的 Smith-Waterman 演算法**。我們將 Whisper 轉錄出的短字串（Hypothesis）視為 Query，將講稿（Reference）視為 Target，計算局部最佳匹配分數。

### **3.2 視窗化優化策略 (Windowed Optimization)**

標準 Smith-Waterman 的時間複雜度為 $O(M \\times N)$，其中 $M$ 為腳本長度，$N$ 為語音片段長度。若腳本長達數萬字，每秒執行多次比對將消耗大量 CPU 資源。  
基於「時間不可逆」的第一性原理——長官只會往下念，極少回頭——我們可以引入注意力視窗（Attention Window）：

* **定義**：設當前游標位置為 $P\_{curr}$。  
* **搜尋範圍**：僅在腳本區間 $\[P\_{curr} \- \\delta\_{back}, P\_{curr} \+ \\delta\_{forward}\]$ 內進行比對。例如，往前看 10 字，往後看 100 字。  
* **優勢**：將複雜度降至 $O(W \\times N)$，其中 $W$ 為視窗大小，與腳本總長無關，確保了系統的可擴展性（Scalability） 27。

### **3.3 數學模型與評分矩陣**

我們定義評分函數 $S(a, b)$ 如下：

* **Match (匹配)**：若 $char\_{voice} \== char\_{script}$，得分 $+3$。  
* **Mismatch (錯誤)**：若字符不同，得分 $-1$。  
* **Gap (跳字/漏字)**：得分 $-2$。

遞迴關係式（Smith-Waterman）：

$$H\_{i,j} \= \\max \\begin{cases} H\_{i-1,j-1} \+ S(A\_i, B\_j), & \\text{(Match/Mismatch)} \\\\ H\_{i-1,j} \+ W\_{gap}, & \\text{(Deletion/Skipping text)} \\\\ H\_{i,j-1} \+ W\_{gap}, & \\text{(Insertion/Ad-libbing)} \\\\ 0 & \\text{(Reset/Local Start)} \\end{cases}$$  
這個公式的特點在於 0 這一項。當分數低於零時，矩陣值重置為零，這意味著「放棄之前的錯誤路徑，重新開始匹配」，這對於處理長官突然脫稿（Ad-lib）後又回到稿子上的情況非常有效。系統會自動忽略脫稿期間的低分匹配，直到長官念出腳本上的字，分數 $H$ 才會重新累積並觸發閾值 12。

## **4\. 系統詳細設計與 Rust 後端實作**

本節將深入探討如何將上述演算法轉化為 Rust 程式碼，並整合至 MeetChi 架構中。

### **4.1 音訊採集與雙緩衝機制 (Audio Ingestion)**

我們使用 cpal 處理跨平台的音訊輸入。為了避免阻塞音訊回調執行緒（Audio Callback Thread），必須使用 Ring Buffer 或 Channel 機制。

Rust

// 示意代碼：音訊採集結構  
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};  
use std::sync::mpsc::{channel, Sender};  
use std::collections::VecDeque;

struct AudioEngine {  
    buffer: VecDeque\<f32\>,  
    sender: Sender\<Vec\<f32\>\>,  
    sample\_rate: u32,  
}

impl AudioEngine {  
    fn new(tx: Sender\<Vec\<f32\>\>) \-\> Self {  
        // 初始化 cpal host 與 device  
        // 設定採樣率為 16000Hz (Whisper 要求)  
        // 若硬體不支援，需掛載 Resampler (如 rubato crate)  
        Self {... }  
    }

    fn stream\_callback(&mut self, data: &\[f32\]) {  
        // 1\. 增益控制 (Optional)  
        // 2\. VAD 檢測 (Silero VAD)  
        if self.vad\_engine.is\_speech(data) {  
            self.sender.send(data.to\_vec()).unwrap();  
        }  
    }  
}

**關鍵技術點**：

1. **VAD (Voice Activity Detection)**：整合 silero-vad-rs。這是防止系統「亂跳」的第一道防線。當長官停頓或現場有掌聲時，VAD 應阻斷音訊進入 Whisper，避免模型將噪音強行解碼為文字（如 "Thank you", "Okay" 等常見幻覺） 7。  
2. **重採樣 (Resampling)**：Whisper 嚴格要求 16kHz。若輸入為 44.1kHz，必須使用 rubato 或 samplerate crate 進行高品質降頻，否則識別率會大幅下降 30。

### **4.2 Whisper 串流推理引擎 (Streaming Inference)**

為了達到「即時」效果，我們不能等待一句話說完。我們採用**滑動窗口推理**策略。

* **窗口長度**：3 秒。  
* **步進長度**：0.5 秒。  
* **上下文傳遞**：利用 whisper-rs 的 context 功能。每次推理時，將上一輪解碼出的最後幾個 Token 作為 prompt 傳入。這能讓 Whisper 知道「前文」，從而提高對「後文」的預測準確度，尤其是在同音字辨識上（例如：知道前文是「各位」，後文接「嘉賓」的機率就遠高於「加冰」） 9。

Rust

// 示意代碼：Whisper 串流處理  
use whisper\_rs::{WhisperContext, FullParams, SamplingStrategy};

fn processing\_loop(rx: Receiver\<Vec\<f32\>\>, script\_engine: Arc\<Mutex\<ScriptEngine\>\>) {  
    let mut audio\_buffer \= Vec::new();  
    let ctx \= WhisperContext::new("path/to/model.bin").expect("failed to load model");

    loop {  
        let chunk \= rx.recv().unwrap();  
        audio\_buffer.extend(chunk);  
          
        // 維持 3 秒的滑動窗口  
        if audio\_buffer.len() \> 3 \* 16000 {  
            let process\_chunk \= \&audio\_buffer\[audio\_buffer.len() \- 3\*16000..\];  
              
            let mut params \= FullParams::new(SamplingStrategy::Greedy { best\_of: 1 });  
            params.set\_language(Some("zh")); // 設定為中文  
            params.set\_print\_special(false);  
              
            // 執行推理  
            ctx.full(params, process\_chunk).expect("failed to run model");  
              
            // 獲取解碼文字  
            let num\_segments \= ctx.full\_n\_segments().expect("failed to get segments");  
            let mut text\_segment \= String::new();  
            for i in 0..num\_segments {  
                text\_segment.push\_str(\&ctx.full\_get\_segment\_text(i).expect("failed to get text"));  
            }

            // 呼叫對齊引擎  
            script\_engine.lock().unwrap().align(\&text\_segment);  
              
            // 移除舊數據，保留部分重疊以確保邊界連續性  
            audio\_buffer.drain(0..16000); // 步進 1 秒  
        }  
    }  
}

### **4.3 雙語腳本狀態管理 (Bilingual Script State)**

後端需維護一個結構化的腳本狀態。由於中英文句法結構不同（例如倒裝句），直接的字對字（Word-to-Word）映射是不切實際的。我們應採用**句對句（Sentence-to-Sentence）** 或 **片段對片段（Segment-to-Segment）** 的映射。

Rust

struct Segment {  
    id: usize,  
    cn\_text: String,       // 中文原文： "今天我們聚集在這裡"  
    en\_text: String,       // 英文翻譯： "Today we gather here"  
    cn\_char\_start: usize,  // 在全文中的起始字元索引：50  
    cn\_char\_end: usize,    // 在全文中的結束字元索引：60  
}

struct ScriptEngine {  
    full\_cn\_text: Vec\<char\>, // 扁平化的中文全文，用於 Smith-Waterman 搜尋  
    segments: Vec\<Segment\>,  // 結構化的對照表  
    current\_cursor: usize,   // 當前長官念到的字元索引  
}

impl ScriptEngine {  
    fn align(&mut self, heard\_text: &str) {  
        // 定義搜尋視窗：當前游標前後範圍  
        let start \= self.current\_cursor.saturating\_sub(20);  
        let end \= (self.current\_cursor \+ 100).min(self.full\_cn\_text.len());  
        let target\_window \= &self.full\_cn\_text\[start..end\];  
          
        // 執行 Smith-Waterman  
        let (best\_idx, score) \= smith\_waterman(target\_window, heard\_text);  
          
        // 閾值判斷：避免誤判  
        if score \> CONFIDENCE\_THRESHOLD {  
            // 更新全域游標  
            self.current\_cursor \= start \+ best\_idx;  
              
            // 查找對應的 Segment ID  
            let segment\_id \= self.find\_segment\_id(self.current\_cursor);  
              
            // 發送事件給前端  
            emit\_event("update\_subtitle", segment\_id);  
        }  
    }  
}

這個設計解決了多對一或一對多的問題。只要長官念到了 Segment X 的中文範圍內，前端就顯示 Segment X 的英文。無論中文句子多長，或者英文翻譯如何斷句，這種基於索引範圍（Index Range）的映射都是最穩健的。

## **5\. Tauri 前端與呈現層優化**

前端的職責看似簡單（顯示文字），但在「長官致詞」這種高壓場景下，UX 的細節決定了系統的成敗。

### **5.1 平滑捲動與視覺聚焦 (Smooth Scrolling & Focus)**

當後端發出 update\_subtitle 事件時，前端必須將對應的英文句子捲動至畫面中央。原生的 scrollIntoView 可能會產生跳動感，影響閱讀體驗。

**React 實作策略**：

1. **Ref 管理**：為每一個句子生成一個 ref。  
2. **事件監聽**：透過 Tauri 的 listen API 接收後端指令。  
3. **置中邏輯**：使用 block: 'center' 參數，確保當前句子永遠位於視覺熱區。  
4. **視覺提示**：除了捲動，還應對當前句子進行高亮（Highlight），並將非當前句子稍微調暗（Dim），以引導觀眾視線 13。

TypeScript

// React Component 示意  
import { listen } from '@tauri-apps/api/event';  
import { useEffect, useRef, useState } from 'react';

const Teleprompter \= ({ script }) \=\> {  
  const \[activeIndex, setActiveIndex\] \= useState(0);  
  const itemRefs \= useRef();

  useEffect(() \=\> {  
    // 監聽 Rust 後端事件  
    const unlisten \= listen('update\_subtitle', (event) \=\> {  
      const newIndex \= event.payload;  
      setActiveIndex(newIndex);  
        
      // 平滑捲動至中央  
      if (itemRefs.current\[newIndex\]) {  
        itemRefs.current\[newIndex\].scrollIntoView({  
          behavior: 'smooth',  
          block: 'center',  
        });  
      }  
    });  
    return () \=\> { unlisten.then(f \=\> f()); };  
  },);

  return (  
    \<div className\="scroll-container"\>  
      {script.map((segment, index) \=\> (  
        \<div   
          key\={segment.id}  
          ref\={el \=\> itemRefs.current\[index\] \= el}  
          className={\`sentence ${index \=== activeIndex? 'active' : 'dimmed'}\`}  
        \>  
          \<p className\="en-text"\>{segment.en}\</p\>  
        \</div\>  
      ))}  
    \</div\>  
  );  
};

### **5.2 延遲隱藏 (Latency Masking)**

儘管我們優化了後端，整個流程（音訊-\>Whisper-\>對齊-\>IPC-\>React Render）仍可能有 500ms-1s 的物理延遲。為了讓使用者感覺「零延遲」，我們可以採用**預測性顯示**：

* **句首觸發**：只要 Smith-Waterman 對齊到該句子的前 3-5 個字，且信心分數夠高，就立即觸發捲動。不需要等到整句念完。  
* **英文先決**：英文翻譯是靜態存在的。一旦確認進入下一句，立即顯示完整的英文句子。這利用了人類閱讀速度快於語速的特性，觀眾會覺得字幕是「同步」甚至「稍快」於語音的，這比「落後」的體驗好得多 5。

## **6\. 系統穩健性與異常處理策略 (Robustness)**

在真實演講場合，異常情況是常態。系統必須具備自我修復能力。

### **6.1 脫稿與插話 (Ad-libbing)**

情境：長官突然講了一個笑話，或者對台下打招呼，這段話不在腳本上。  
系統反應：

1. Whisper 會轉錄出這段笑話。  
2. Smith-Waterman 在當前視窗內搜尋，發現匹配分數極低（低於閾值）。  
3. **決策**：游標**停止移動**。英文顯示停留在最後一句確認的腳本內容。  
4. **恢復**：當長官講完笑話，回到腳本上的文字時，Smith-Waterman 的分數會瞬間飆高，游標自動跳轉至新位置。這種「不匹配即懸停」（No Match, Hover）的策略是處理脫稿的最佳解 22。

### **6.2 跳頁或大幅度跳段 (Page Skipping)**

情境：長官因為時間不夠，直接跳過了兩段。  
系統反應：

1. **局部搜尋失敗**：Smith-Waterman 在 $\\pm 100$ 字的窗口內連續 $N$ 次匹配失敗。  
2. **全域搜尋觸發 (Global Resync)**：系統啟動備用的全域搜尋機制。這可以是擴大 Smith-Waterman 的視窗至全文，或是使用基於 TF-IDF / 向量嵌入（Vector Embedding）的輕量級搜尋，快速定位當前語音在全文中的大概位置。  
3. **重置游標**：一旦全域搜尋鎖定新位置，強制更新 current\_cursor，前端介面進行一次較大幅度的捲動（Jump Scroll） 33。

### **6.3 幻覺抑制 (Hallucination Suppression)**

Whisper 在靜音時可能會輸出 "Subtitles by..." 或重複上一個詞。  
策略：

1. **VAD 硬閘門**：如前所述，VAD 判斷為靜音時，直接丟棄音訊，不進 Whisper。  
2. **重複過濾**：若 Whisper 輸出的文字與上一次完全相同，且時間間隔極短，視為重複幻覺並過濾。  
3. **文本正則化**：過濾掉 Whisper 常見的無意義輸出（如 "", "(Music)" 等標記）。

## **7\. 結論與建議**

本報告基於第一性原理，將 MeetChi 專案從一個通用的會議記錄工具，重構為一個專業的「演講稿同步系統」。

1. **架構轉向**：我們從「聽寫」（Transcription）轉向「對齊」（Alignment）。這根本性地改變了我們使用 Whisper 的方式——它不再是產出內容的作者，而是輔助定位的傳感器。  
2. **關鍵演算法**：引入 **Smith-Waterman** 演算法與 **滑動視窗** 機制，解決了即時性與容錯性的矛盾。  
3. **工程落地**：利用 Rust 的 cpal 與 whisper-rs 打造了高效能的後端，並透過 Tauri 事件驅動機制與 React 前端完美整合。

最終建議：  
建議開發團隊優先實作「Rust 端的對齊引擎」與「腳本狀態機」。這部分是目前 MeetChi 所缺乏的，也是滿足客戶「照稿致詞同步顯示」需求的關鍵拼圖。透過此架構，系統將能以極低的資源消耗，實現專業級展會或政務場合所需的精確字幕同步功能。

---

報告結束  
文中引用的技術細節與參數設定皆基於所附研究資料 35 進行綜合分析與推演。

#### **引用的著作**

1. Real-time human progress estimation with online dynamic time warping for collaborative robotics \- NIH, 檢索日期：1月 17, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC12712710/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12712710/)  
2. How does forced alignment work? \- Conversational AI \- Research at NVIDIA, 檢索日期：1月 17, 2026， [https://research.nvidia.com/labs/conv-ai/blogs/2023/2023-08-forced-alignment/](https://research.nvidia.com/labs/conv-ai/blogs/2023/2023-08-forced-alignment/)  
3. Forced Alignment with Wav2Vec2 — Torchaudio 2.8.0 documentation, 檢索日期：1月 17, 2026， [https://docs.pytorch.org/audio/2.8/tutorials/forced\_alignment\_tutorial.html](https://docs.pytorch.org/audio/2.8/tutorials/forced_alignment_tutorial.html)  
4. A Linear Memory CTC-Based Algorithm for Text-to-Voice Alignment of Very Long Audio Recordings \- MDPI, 檢索日期：1月 17, 2026， [https://www.mdpi.com/2076-3417/13/3/1854](https://www.mdpi.com/2076-3417/13/3/1854)  
5. WhisperKit: On-device Real-time ASR with Billion-Scale Transformers \- arXiv, 檢索日期：1月 17, 2026， [https://arxiv.org/html/2507.10860v1](https://arxiv.org/html/2507.10860v1)  
6. Reducing Streaming ASR Model Delay with Self Alignment \- ISCA Archive, 檢索日期：1月 17, 2026， [https://www.isca-archive.org/interspeech\_2021/kim21j\_interspeech.pdf](https://www.isca-archive.org/interspeech_2021/kim21j_interspeech.pdf)  
7. voice-stream \- crates.io: Rust Package Registry, 檢索日期：1月 17, 2026， [https://crates.io/crates/voice-stream](https://crates.io/crates/voice-stream)  
8. voice\_activity\_detector \- Rust \- Docs.rs, 檢索日期：1月 17, 2026， [https://docs.rs/voice\_activity\_detector](https://docs.rs/voice_activity_detector)  
9. Turning Whisper into Real-Time Transcription System \- arXiv, 檢索日期：1月 17, 2026， [https://arxiv.org/html/2307.14743](https://arxiv.org/html/2307.14743)  
10. whisper-rs \- crates.io: Rust Package Registry, 檢索日期：1月 17, 2026， [https://crates.io/crates/whisper-rs](https://crates.io/crates/whisper-rs)  
11. Smith-Waterman Alignment Scoring Settings \- Illumina Support Center, 檢索日期：1月 17, 2026， [https://support.illumina.com/content/dam/illumina-support/help/Illumina\_DRAGEN\_Bio\_IT\_Platform\_v3\_7\_1000000141465/Content/SW/Informatics/Dragen/GPipelineSmithWat\_fDG.htm](https://support.illumina.com/content/dam/illumina-support/help/Illumina_DRAGEN_Bio_IT_Platform_v3_7_1000000141465/Content/SW/Informatics/Dragen/GPipelineSmithWat_fDG.htm)  
12. A Review of Parallel Implementations for the Smith–Waterman Algorithm \- PMC, 檢索日期：1月 17, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC8419822/](https://pmc.ncbi.nlm.nih.gov/articles/PMC8419822/)  
13. Smoothly Scroll A Selected List Item into View in React | by Himanshu jain | Medium, 檢索日期：1月 17, 2026， [https://medium.com/@himanshuain5567/smoothly-scroll-a-selected-list-item-into-view-in-react-using-useref-hook-4bdb84932255](https://medium.com/@himanshuain5567/smoothly-scroll-a-selected-list-item-into-view-in-react-using-useref-hook-4bdb84932255)  
14. React hook for smooth scrolling of an element into view \- GitHub Gist, 檢索日期：1月 17, 2026， [https://gist.github.com/scriptex/32ca810d0250aed0e2418226d625d243](https://gist.github.com/scriptex/32ca810d0250aed0e2418226d625d243)  
15. Whisper Implementation for Cross platform application? : r/rust \- Reddit, 檢索日期：1月 17, 2026， [https://www.reddit.com/r/rust/comments/1ex0zg0/whisper\_implementation\_for\_cross\_platform/](https://www.reddit.com/r/rust/comments/1ex0zg0/whisper_implementation_for_cross_platform/)  
16. Is there a way to build tauri application and use whisperx? : r/rust \- Reddit, 檢索日期：1月 17, 2026， [https://www.reddit.com/r/rust/comments/1f8nyu2/is\_there\_a\_way\_to\_build\_tauri\_application\_and\_use/](https://www.reddit.com/r/rust/comments/1f8nyu2/is_there_a_way_to_build_tauri_application_and_use/)  
17. Calling the Frontend from Rust \- Tauri, 檢索日期：1月 17, 2026， [https://v2.tauri.app/develop/calling-frontend/](https://v2.tauri.app/develop/calling-frontend/)  
18. Window Customization \- Tauri, 檢索日期：1月 17, 2026， [https://v2.tauri.app/learn/window-customization/](https://v2.tauri.app/learn/window-customization/)  
19. \[Feature\]: Support token-level timestamps in whisper models · Issue \#13400 \- GitHub, 檢索日期：1月 17, 2026， [https://github.com/vllm-project/vllm/issues/13400](https://github.com/vllm-project/vllm/issues/13400)  
20. Word level time stamps with Whisper 1.6.2 / DTW off \- solutions? · ggml-org whisper.cpp · Discussion \#2307 \- GitHub, 檢索日期：1月 17, 2026， [https://github.com/ggml-org/whisper.cpp/discussions/2307](https://github.com/ggml-org/whisper.cpp/discussions/2307)  
21. Needleman–Wunsch algorithm \- Wikipedia, 檢索日期：1月 17, 2026， [https://en.wikipedia.org/wiki/Needleman%E2%80%93Wunsch\_algorithm](https://en.wikipedia.org/wiki/Needleman%E2%80%93Wunsch_algorithm)  
22. AUTOMATIC ALIGNMENT OF MUSIC PERFORMANCES WITH STRUCTURAL DIFFERENCES \- ISMIR, 檢索日期：1月 17, 2026， [https://archives.ismir.net/ismir2013/paper/000158.pdf](https://archives.ismir.net/ismir2013/paper/000158.pdf)  
23. smith\_waterman: Align text using Smith-Waterman \- RDocumentation, 檢索日期：1月 17, 2026， [https://www.rdocumentation.org/packages/text.alignment/versions/0.1.0/topics/smith\_waterman](https://www.rdocumentation.org/packages/text.alignment/versions/0.1.0/topics/smith_waterman)  
24. Smith–Waterman algorithm \- Wikipedia, 檢索日期：1月 17, 2026， [https://en.wikipedia.org/wiki/Smith%E2%80%93Waterman\_algorithm](https://en.wikipedia.org/wiki/Smith%E2%80%93Waterman_algorithm)  
25. What is dynamic time warping (DTW) and how is it applied in audio matching? \- Milvus, 檢索日期：1月 17, 2026， [https://milvus.io/ai-quick-reference/what-is-dynamic-time-warping-dtw-and-how-is-it-applied-in-audio-matching](https://milvus.io/ai-quick-reference/what-is-dynamic-time-warping-dtw-and-how-is-it-applied-in-audio-matching)  
26. Principles and Applications of Dynamic Time Warping Algorithm \- Oreate AI Blog, 檢索日期：1月 17, 2026， [https://www.oreateai.com/blog/principles-and-applications-of-dynamic-time-warping-algorithm/8976fdd6faedc4e7b21bc933794d7fd7](https://www.oreateai.com/blog/principles-and-applications-of-dynamic-time-warping-algorithm/8976fdd6faedc4e7b21bc933794d7fd7)  
27. Faster Sliding Window String Indexing in Streams \- DROPS, 檢索日期：1月 17, 2026， [https://drops.dagstuhl.de/storage/00lipics/lipics-vol296-cpm2024/LIPIcs.CPM.2024.8/LIPIcs.CPM.2024.8.pdf](https://drops.dagstuhl.de/storage/00lipics/lipics-vol296-cpm2024/LIPIcs.CPM.2024.8/LIPIcs.CPM.2024.8.pdf)  
28. A Novel Text Stream Clustering Technique for Web Pages using Sliding Window, 檢索日期：1月 17, 2026， [https://ia802805.us.archive.org/30/items/vol6no0401\_201808/vol6no0401.pdf](https://ia802805.us.archive.org/30/items/vol6no0401_201808/vol6no0401.pdf)  
29. Striped Smith–Waterman speeds database searches six time over other SIMD implementations \- ResearchGate, 檢索日期：1月 17, 2026， [https://www.researchgate.net/publication/6688245\_Striped\_Smith-Waterman\_speeds\_database\_searches\_six\_time\_over\_other\_SIMD\_implementations](https://www.researchgate.net/publication/6688245_Striped_Smith-Waterman_speeds_database_searches_six_time_over_other_SIMD_implementations)  
30. whisper-stream-rs \- crates.io: Rust Package Registry, 檢索日期：1月 17, 2026， [https://crates.io/crates/whisper-stream-rs/0.3.0](https://crates.io/crates/whisper-stream-rs/0.3.0)  
31. Streaming Speech Recognition with Conformers — SpeechBrain 0.5.0 documentation, 檢索日期：1月 17, 2026， [https://speechbrain.readthedocs.io/en/v1.0.3/tutorials/nn/conformer-streaming-asr.html](https://speechbrain.readthedocs.io/en/v1.0.3/tutorials/nn/conformer-streaming-asr.html)  
32. Evaluating global and local sequence alignment methods for comparing patient medical records \- PMC \- NIH, 檢索日期：1月 17, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC6921442/](https://pmc.ncbi.nlm.nih.gov/articles/PMC6921442/)  
33. How to build intelligent search: From full-text to optimized hybrid search \- BigHub, 檢索日期：1月 17, 2026， [https://www.bighub.ai/blog/how-to-build-intelligent-search-from-full-text-to-optimized-hybrid-search](https://www.bighub.ai/blog/how-to-build-intelligent-search-from-full-text-to-optimized-hybrid-search)  
34. Revolutionize Your Search with Hybrid Techniques: A Hands-On Guide \- Hackernoon, 檢索日期：1月 17, 2026， [https://hackernoon.com/revolutionize-your-search-with-hybrid-techniques-a-hands-on-guide](https://hackernoon.com/revolutionize-your-search-with-hybrid-techniques-a-hands-on-guide)  
35. Jitsi Meet \- Secure, Simple and Scalable Video Conferences that you use as a standalone app or embed in your web application. \- GitHub, 檢索日期：1月 17, 2026， [https://github.com/jitsi/jitsi-meet](https://github.com/jitsi/jitsi-meet)  
36. javascript \- Scroll smoothly to specific element on page \- Stack Overflow, 檢索日期：1月 17, 2026， [https://stackoverflow.com/questions/17722497/scroll-smoothly-to-specific-element-on-page](https://stackoverflow.com/questions/17722497/scroll-smoothly-to-specific-element-on-page)