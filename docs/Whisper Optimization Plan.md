# **進階自動語音辨識推論引擎優化策略：針對 Breeze-ASR-25 的 Faster-Whisper、TensorRT-LLM 與投機解碼架構之深度技術分析報告**

## **1\. 執行摘要 (Executive Summary)**

隨著大型語言模型（Large Language Models, LLMs）與大規模自動語音辨識（Automatic Speech Recognition, ASR）模型的快速發展，如何將其高效部署於生產環境已成為人工智慧基礎設施領域的核心挑戰。聯發科技研究中心（MediaTek Research）推出的 **Breeze-ASR-25** 模型，基於 OpenAI Whisper Large-v2 架構並針對台灣繁體中文（Taiwanese Mandarin）與中英混合語境（Code-switching）進行了深度微調，展現了卓越的辨識準確率 1。然而，其高達 15.5 億參數的 Transformer 編碼器-解碼器（Encoder-Decoder）架構，在推論階段面臨著自回歸解碼（Autoregressive Decoding）帶來的巨大記憶體頻寬瓶頸，這對於即時字幕生成、對話系統與邊緣運算應用構成了嚴峻的延遲挑戰。

本研究報告針對 5.1 節「推論引擎的選擇」進行了詳盡的技術剖析，深度比較了兩大主流推論框架：基於 CTranslate2 的 **Faster-Whisper** 與 NVIDIA 針對資料中心 GPU 優化的 **TensorRT-LLM**。同時，本報告亦探討了 **投機解碼（Speculative Decoding）** 技術在 ASR 領域的應用潛力與實作路徑。

分析顯示，**Faster-Whisper** 憑藉其輕量化的 C++ 運行時與穩健的 INT8 量化策略，在邊緣裝置與消費級 GPU 上提供了最佳的易用性與記憶體效率，且對 Breeze-ASR-25 的特殊詞表具有良好的原生支援。相對地，**TensorRT-LLM** 透過激進的算子融合（Kernel Fusion）、飛行批次處理（In-flight Batching）與 KV Cache 分頁管理技術，在 NVIDIA Ampere 與 Hopper 架構 GPU 上展現了極致的吞吐量優勢，特別適合高併發的雲端服務場景。然而，其對 Breeze-ASR-25 的部署需要複雜的模型轉換與權重映射工程。此外，投機解碼技術（如 SpecASR 與 Medusa）雖能顯著降低延遲，但目前受限於缺乏針對繁體中文優化的「草稿模型」（Draft Model），其實際落地仍需額外的蒸餾訓練投入。

本報告旨在為架構師與開發者提供具體的決策依據，從理論基礎、實作細節到效能基準，全面解析如何為 Breeze-ASR-25 構建最佳化的推論管線。

## ---

**2\. ASR 推論優化的理論框架與挑戰**

### **2.1 Transformer ASR 的自回歸瓶頸解析**

Breeze-ASR-25 繼承了 Whisper 的編碼器-解碼器架構。在推論過程中，計算負載呈現出顯著的兩極化特徵：

1. **編碼器（Encoder）：** 負責處理輸入的梅爾頻譜圖（Log-Mel Spectrogram）。由於音訊特徵具有固定的時間維度，編碼器可以利用 Transformer 的並行計算能力，一次性處理所有音訊幀。此階段屬於 **計算密集型（Compute-bound）**，現代 GPU 的 Tensor Core 可以極高效率地完成此任務。  
2. 解碼器（Decoder）： 負責將編碼器的隱藏狀態轉換為文字 token。此過程是 自回歸（Autoregressive） 的，即生成第 $t$ 個 token $y\_t$ 必須依賴於前 $t-1$ 個 token $y\_{\<t}$ 的結果：

   $$P(y|X) \= \\prod\_{t=1}^{T} P(y\_t | y\_{\<t}, X)$$

   這意味著 GPU 無法並行計算未來的 token。對於每一個生成的 token，GPU 都必須從高頻寬記憶體（HBM）中讀取整個解碼器的權重（對於 Whisper Large-v2 約為 3GB），載入到 SRAM 進行運算，然後再寫回。由於單次解碼的計算量相對於權重讀取量極小，這導致解碼階段嚴重受限於 記憶體頻寬（Memory-bound）。這就是所謂的「記憶體牆（Memory Wall）」問題。

### **2.2 關鍵優化向量**

為了突破上述瓶頸，現代推論引擎主要採用以下幾種優化策略：

* **量化（Quantization）：** 降低數值精度（如從 FP16 降至 INT8 或 INT4）。這不僅減少了模型權重佔用的 VRAM，更重要的是減少了從 HBM 讀取數據的頻寬需求，從而直接提升解碼速度。  
* **算子融合（Kernel Fusion）：** 將多個細碎的運算（如矩陣乘法 \+ 偏差相加 \+ 激活函數）合併為單一 GPU Kernel 啟動，減少 Kernel 啟動的 CPU 開銷（Launch Overhead）與記憶體讀寫次數。  
* **記憶體管理優化：** 針對 Transformer 的 Attention 機制，優化 Key-Value (KV) Cache 的存儲與讀取。例如 FlashAttention 通過重新計算（Recomputation）與分塊計算（Tiling）減少 HBM 存取；PagedAttention 則解決了顯存碎片化問題。  
* **演算法加速：** 即投機解碼，試圖在單次模型前向傳播中生成多個 token，打破序列依賴的限制。

## ---

**3\. Faster-Whisper：基於 CTranslate2 的高效能實作**

**Faster-Whisper** 是目前開源社群中最受歡迎的 Whisper 優化實現之一。它並非單純的 Python 腳本優化，而是基於 **CTranslate2** 推論引擎的封裝。

### **3.1 CTranslate2 的架構優勢**

CTranslate2 是由 SYSTRAN 開發的，專門針對 Transformer 模型（如 BERT, GPT-2, T5, Whisper）進行優化的 C++ 推論引擎 4。與通用的深度學習框架（如 PyTorch 或 TensorFlow）相比，CTranslate2 具有以下顯著優勢：

1. **輕量級 C++ 運行時：** 它擺脫了 PyTorch 龐大的依賴庫與 Python 的 GIL（Global Interpreter Lock）限制，使得多執行緒併發處理更加高效，特別是在 CPU 推論場景下。  
2. **記憶體佈局優化：** CTranslate2 在轉換模型時，會重排權重矩陣的記憶體佈局，以最大化 CPU 和 GPU 上 GEMM（通用矩陣乘法）運算的快取命中率。  
3. **計算類型（Compute Type）抽象：** 引擎支援動態的精度選擇。開發者可以在載入模型時指定 compute\_type="int8"，引擎會自動處理權重的反量化或使用硬體加速的整數運算指令，而無需重新轉換模型檔案 4。

### **3.2 針對 Breeze-ASR-25 的實作流程**

要將 MediaTek 的 Breeze-ASR-25 部署於 Faster-Whisper，必須將 Hugging Face 格式的 PyTorch Checkpoint 轉換為 CTranslate2 的二進制格式。這是一個關鍵步驟，直接影響模型的正確性與效能。

#### **3.2.1 模型轉換詳解**

使用 ct2-transformers-converter 工具進行轉換。對於 Breeze-ASR-25，由於其針對繁體中文優化，保留原始的 Tokenizer 設定至關重要 2。

Bash

\# 建立虛擬環境並安裝依賴  
pip install transformers ctranslate2

\# 執行轉換指令  
ct2-transformers-converter \\  
    \--model MediaTek-Research/Breeze-ASR-25 \\  
    \--output\_dir faster-whisper-Breeze-ASR-25 \\  
    \--copy\_files tokenizer.json preprocessor\_config.json \\  
    \--quantization float16

* **\--model**: 指定 Hugging Face 上的模型 ID 或本地路徑。  
* **\--copy\_files tokenizer.json...**: **這是針對 Breeze-ASR-25 最關鍵的參數**。Breeze 模型擴充或調整了原始 Whisper 的詞表以適應繁體中文與台灣用語。如果轉換過程中丟失了這些設定檔，推論時將使用預設 Whisper Tokenizer，導致繁體中文輸出亂碼或轉為簡體，嚴重破壞模型價值 1。  
* **\--quantization float16**: 此參數控制**儲存**在磁碟上的權重精度。建議存為 FP16 以節省磁碟空間，推論時可再動態降級為 INT8。

#### **3.2.2 推論程式碼實作**

轉換完成後，使用 faster\_whisper 庫進行載入與推論：

Python

from faster\_whisper import WhisperModel

model\_path \= "faster-whisper-Breeze-ASR-25"

\# 在 GPU 上運行，使用 FP16 精度（若顯卡支援）  
\# 對於極致速度，可將 compute\_type 設為 "int8\_float16"  
model \= WhisperModel(model\_path, device="cuda", compute\_type="float16")

segments, info \= model.transcribe(  
    "audio.wav",  
    beam\_size=5,  
    language="zh", \# 強制指定中文，或讓其自動偵測  
    initial\_prompt="以下是繁體中文的逐字稿。" \# Breeze 支援 Prompting  
)

for segment in segments:  
    print("\[%.2fs \-\> %.2fs\] %s" % (segment.start, segment.end, segment.text))

### **3.3 效能與量化分析**

#### **3.3.1 量化對繁體中文的影響**

Faster-Whisper 支援多種量化模式，其中 **INT8 量化** 是最常用的加速手段。研究與實測數據表明，將 Whisper 模型從 FP32/FP16 轉換為 INT8，模型體積可縮小約 2-4 倍，推論速度提升 4-5 倍 4。

針對 Breeze-ASR-25 這類針對特定語言微調的模型，開發者常擔憂量化會導致精度損失（Wer Error Rate, WER 上升）。然而，多項研究指出，對於 Transformer 架構，INT8 量化帶來的 WER 損失通常微乎其微（\< 1%），且人類幾乎無法感知。這是因為語音辨識的聲學特徵在編碼器階段已經被高度抽象化，解碼器對權重的數值擾動具有較強的魯棒性。僅在極端嘈雜或極低資源的語言場景下，INT8 才可能出現明顯的性能下降 8。

#### **3.3.2 資源消耗**

* **VRAM 佔用：** 原生 PyTorch 運行 Whisper-Large-v2 需要約 4-5GB VRAM（FP16）。Faster-Whisper 在 INT8 模式下僅需約 2-3GB，這使得在消費級顯卡（如 RTX 3060 甚至 4GB VRAM 的筆電顯卡）上運行 Breeze-ASR-25 成為可能 7。  
* **CPU 推論：** CTranslate2 對 Intel/AMD CPU 的 AVX-512/VNNI 指令集有深度優化。若無 GPU，Faster-Whisper 的 INT8 模式是目前在 CPU 上運行 Large 模型的唯一實用方案，速度遠超 PyTorch CPU 推論。

## ---

**4\. NVIDIA TensorRT-LLM：極致效能的企業級方案**

若 Faster-Whisper 是「效率」的代表，那麼 **TensorRT-LLM** 則是「吞吐量（Throughput）」與「延遲（Latency）」的極致追求者。這是 NVIDIA 專為大型語言模型與序列生成模型開發的推論庫，整合了 TensorRT 的編譯優化與針對 Transformer 的手寫 CUDA Kernel 11。

### **4.1 TensorRT-LLM 的核心技術優勢**

#### **4.1.1 飛行批次處理（In-flight Batching）**

這是 TensorRT-LLM 與 Faster-Whisper 最大的區別，也是其在伺服器端應用具有統治地位的原因。

* **靜態批次（Static Batching，Faster-Whisper 採用）：** 假設一個 Batch 有 4 個請求，長度分別為 2秒、5秒、10秒、3秒。系統必須等待最長的 10秒請求處理完畢，才能釋放整個 Batch 的資源。這導致處理短請求的計算單元在大部分時間處於閒置狀態。  
* **飛行批次（In-flight Batching）：** TensorRT-LLM 在「迭代（Iteration）」層級進行調度。當 2秒的請求處理完畢後，系統會立即將其移除，並從佇列中拉取一個新的請求填入該空位。這使得 GPU 的利用率始終維持在峰值，顯著提升了服務的總吞吐量，並降低了單個請求的排隊延遲 13。

#### **4.1.2 記憶體管理：Paged KV Cache**

受到作業系統虛擬記憶體分頁技術的啟發，TensorRT-LLM 引入了 Paged KV Cache。在自回歸解碼中，KV Cache（Key-Value Cache）會隨著生成的 token 數量動態增長。傳統方法需要預先分配連續的顯存空間，容易導致碎片化與浪費（OOM）。Paged Attention 允許將 KV Cache 存儲在不連續的記憶體區塊中，極大提升了顯存利用率，使得在同樣的硬體上可以支援更大的 Batch Size 11。

#### **4.1.3 算子融合（Kernel Fusion）**

TensorRT-LLM 能夠將 Transformer 中的多個操作（如 LayerNorm、MatMul、Residual Add、GELU）融合為單個 CUDA Kernel。這減少了 GPU 記憶體的讀寫往返次數（Memory Access）與 Kernel 啟動的 CPU 開銷。對於 Breeze-ASR-25 這種深層網路，這種優化帶來的加速效果極為顯著 16。

### **4.2 Breeze-ASR-25 在 TensorRT-LLM 的實作挑戰**

雖然 TensorRT-LLM 效能強大，但其部署複雜度遠高於 Faster-Whisper。Breeze-ASR-25 的部署需要經過繁瑣的構建流程。

#### **4.2.1 編碼器與解碼器的分離構建**

TensorRT-LLM 將 Whisper 模型視為兩個獨立的引擎：

1. **Encoder Engine:** 非自回歸模型，輸入音訊特徵，輸出隱藏狀態。  
2. **Decoder Engine:** 自回歸模型，輸入 Encoder 隱藏狀態與當前 Token，輸出下一個 Token。

這需要使用 NVIDIA 提供的 convert\_checkpoint.py 腳本，將 Breeze-ASR-25 的權重映射到 TensorRT-LLM 的層結構中。由於 Breeze-ASR-25 與 Whisper 架構完全相容，通常可以直接使用 Whisper 的轉換腳本，但必須注意詞表大小（Vocab Size）的設定是否因微調而改變 17。

#### **4.2.2 構建指令範例**

實作過程通常涉及以下步驟（需在 NVIDIA Docker 容器中執行）：

Bash

\# 1\. 下載 Breeze-ASR-25 模型  
git clone https://huggingface.co/MediaTek-Research/Breeze-ASR-25

\# 2\. 轉換權重 (需分別轉換 Encoder 和 Decoder)  
python3 examples/whisper/convert\_checkpoint.py \\  
    \--model\_dir Breeze-ASR-25 \\  
    \--output\_dir./tllm\_checkpoint \\  
    \--model\_type whisper

\# 3\. 編譯 TensorRT 引擎 (Engine Build)  
\# 啟用 Paged Context FMHA 以支援 KV Cache Reuse 和高效能  
trtllm-build \--checkpoint\_dir./tllm\_checkpoint/encoder \\  
             \--output\_dir./engines/encoder \\  
             \--paged\_kv\_cache disable  \# Encoder 不需要 KV Cache

trtllm-build \--checkpoint\_dir./tllm\_checkpoint/decoder \\  
             \--output\_dir./engines/decoder \\  
             \--use\_paged\_context\_fmha enable \\  
             \--use\_gemm\_plugin float16 \# 啟用 FP16 加速插件

特別需要注意的是 \--use\_gpt\_attention\_plugin 和 \--use\_gemm\_plugin 參數，這是啟用 NVIDIA 手寫優化 Kernel 的關鍵。若未啟用，TensorRT 可能會退回到標準實現，效能將大打折扣 17。

#### **4.2.3 硬體綁定限制**

TensorRT 生成的 .engine 檔案是與 GPU 架構（SM 版本）嚴格綁定的。在 A100 上編譯的引擎無法在 RTX 4090 上運行。這意味著在異構集群或雲端自動擴展場景中，必須為每種 GPU 型號維護獨立的引擎庫，增加了維運的複雜度 18。

### **4.3 效能對比：TensorRT-LLM vs. Faster-Whisper**

根據多項基準測試數據 7 的綜合分析：

| 評估指標 | Faster-Whisper (INT8) | TensorRT-LLM (FP16/INT8) | 分析與洞察 |
| :---- | :---- | :---- | :---- |
| **單流延遲 (Latency)** | 極低 (\~200ms) | **極致低 (\<100ms)** | 對於單一使用者的即時聽寫，兩者差異不大，但 TRT-LLM 的 Kernel Fusion 能進一步壓低延遲下限。 |
| **最大吞吐量 (Throughput)** | 高 (受限於靜態批次) | **超高 (In-flight Batching)** | 在高併發場景下，TRT-LLM 的吞吐量可達 Faster-Whisper 的 1.5 倍至 2 倍以上。 |
| **顯存效率** | **極佳** (動態釋放) | 中等 (靜態分配) | Faster-Whisper 更適合顯存受限的邊緣裝置；TRT-LLM 傾向於預先佔用顯存以換取效能。 |
| **部署靈活性** | 高 (Python, 跨 GPU) | 低 (需編譯, 綁定硬體) | Faster-Whisper 適合快速迭代與多樣化硬體；TRT-LLM 適合定型後的生產環境。 |
| **Breeze-ASR-25 相容性** | **原生支援** | 需轉換工程 | Faster-Whisper 對自定義 Tokenizer 的支援較為直觀；TRT-LLM 需確保轉換腳本正確處理特殊 Token。 |

## ---

**5\. 投機解碼（Speculative Decoding）：打破序列生成瓶頸**

### **5.1 投機解碼的運作原理**

投機解碼是一種旨在加速自回歸模型推論的演算法技術。其核心思想是「預測-驗證（Draft-and-Verify）」：

1. **草稿階段（Draft）：** 使用一個更小、更快的「草稿模型（Draft Model）」快速生成 $K$ 個候選 token。  
2. **驗證階段（Verify）：** 使用完整的大模型（如 Breeze-ASR-25）進行一次並行的前向傳播，計算這 $K$ 個 token 的真實機率。  
3. **接受/拒絕：** 若草稿 token 與大模型的預測一致（或滿足特定機率分佈），則接受該 token；否則拒絕並修正。

由於驗證 $K$ 個 token 是並行的，只要草稿模型的準確率夠高，就能在一次大模型運算中生成多個 token，從而顯著降低記憶體讀取次數與總延遲 21。

### **5.2 ASR 領域的獨特優勢**

相比於開放式文本生成（如寫詩），ASR 任務的輸出受到輸入音訊的強烈約束（Audio-Conditioned）。這意味著「下一個詞」的確定性（Entropy 較低）遠高於純文本生成。因此，草稿模型在 ASR 任務中通常能達到極高的接受率（Acceptance Rate），使得投機解碼在 ASR 中的加速效果往往優於 LLM 21。

### **5.3 針對 Breeze-ASR-25 的投機解碼策略**

#### **5.3.1 策略一：Distil-Whisper 作為草稿模型**

**Distil-Whisper** 是 Whisper 的蒸餾版本（如只有 2 層 Decoder），速度快 6 倍。理論上，它是 Breeze-ASR-25 的完美草稿模型。

* **挑戰：** 目前開源的 Distil-Whisper 模型多為英文版 25。若直接用英文 Distil-Whisper 作為 Breeze-ASR-25（繁體中文）的草稿模型，預測準確率將極低，導致頻繁拒絕，反而拖慢速度。  
* **解決方案：** 必須針對 Breeze-ASR-25 的訓練數據進行知識蒸餾，訓練一個「Breeze-Tiny」或「Distilled-Breeze」模型。這需要額外的訓練成本，但能帶來最穩定的加速收益。

#### **5.3.2 策略二：Whisper-Medusa**

**Medusa** 架構不依賴獨立的草稿模型，而是在 Breeze-ASR-25 的最後一層添加多個「預測頭（Heads）」，分別預測 $t+1, t+2, \\dots$ 個 token。

* **優勢：** 無需維護兩個獨立模型，顯存佔用增加極少。  
* **實作：** 需要凍結 Breeze-ASR-25 的主幹，僅訓練 Medusa Heads。這比完整的知識蒸餾要快得多且容易實現。目前已有開源的 Whisper-Medusa 實作，證明可達 1.5 倍加速 27。對於 TensorRT-LLM，它已原生支援 Medusa 解碼模式 30。

#### **5.3.3 策略三：SpecASR (Tree-based Drafting)**

**SpecASR** 是一種專為 ASR 設計的進階框架。它不只預測單一序列，而是構建一個 token 樹（Token Tree），並利用「草稿序列回收（Draft Sequence Recycling）」技術，將上一步驟中被拒絕但可能在當前步驟正確的 token 重複利用。

* **效能：** 據文獻報導，SpecASR 可達到 3 倍以上的加速 21。  
* **現狀：** 這是較新的研究成果，TensorRT-LLM 目前對 Tree-based speculative decoding 有支援（如 SpecInfer/Eagle），但針對 ASR 特定優化的整合可能尚需自行開發或等待更新。

### **5.4 TensorRT-LLM 中的投機解碼實作**

TensorRT-LLM 提供了 Orchestrator 模式來支援投機解碼。要為 Breeze-ASR-25 啟用此功能，需要在構建引擎時指定參數：

Bash

\# 構建目標模型 (Target Engine)  
trtllm-build \--checkpoint\_dir./breeze\_large\_ckpt \\  
             \--speculative\_decoding\_mode draft\_tokens\_external \\  
             \--output\_dir./engines/target

\# 構建草稿模型 (Draft Engine, 假設已有 Breeze-Tiny)  
trtllm-build \--checkpoint\_dir./breeze\_tiny\_ckpt \\  
             \--output\_dir./engines/draft

在運行時，透過 executor API 配置 speculative\_decoding\_config 即可啟用。這使得 Breeze-ASR-25 能在享受 TensorRT-LLM 硬體加速的同時，進一步透過演算法突破延遲下限 30。

## ---

**6\. 即時串流架構與 WhisperLiveKit 整合**

對於 ASR 應用，推論引擎只是核心，外圍的串流處理架構同樣決定了使用者的最終體驗。**WhisperLiveKit** 是一個優秀的參考架構，專注於即時語音轉文字 32。

### **6.1 串流策略：AlignAtt vs. LocalAgreement**

Whisper 本質上是處理長片段的，不適合逐字串流。WhisperLiveKit 引入了幾種策略：

* **SimulStreaming (AlignAtt 策略)：** 這是目前最先進的方案。它利用 Whisper 內部的 Cross-Attention 權重來判斷當前生成的詞是否「穩定」。如果模型對某個詞的注意力高度集中且穩定，則輸出該詞；否則等待更多音訊輸入。這解決了即時字幕常見的「閃爍（Flickering）」與「回溯修正」問題 32。  
* **LocalAgreement：** 運行兩個不同上下文窗口的解碼過程，只有當兩者結果一致時才輸出。這增加了計算量，但提高了穩定性。

### **6.2 TensorRT-LLM 的串流整合：KV Cache Reuse**

在串流場景中，使用者音訊是分塊到達的（Chunk 1 \-\> Chunk 2 \-\>...）。傳統做法是每次都將「Chunk 1 \+ Chunk 2」重新送入模型，這會導致計算量隨時間呈平方級增長。

TensorRT-LLM 支援 **KV Cache Reuse（或稱 Stateful Serving）**。系統可以將 Chunk 1 計算出的 KV Cache 保留在顯存中（Context Phase），當 Chunk 2 到達時，只需計算 Chunk 2 的 KV，並與之前的 Cache 連接。這對於長對話或長會議的即時轉錄至關重要，能將複雜度從 $O(N^2)$ 降至 $O(N)$。在構建 TensorRT 引擎時，必須啟用 \--use\_paged\_context\_fmha enable 以支援此功能 34。

WhisperLiveKit 的 TensorRT 後端目前已透過 Docker 容器支援此整合，允許開發者直接掛載預先構建好的 Breeze-ASR-25 TensorRT 引擎進行即時服務 17。

## ---

**7\. 結論與建議 (Conclusion and Recommendations)**

針對 Breeze-ASR-25 的推論引擎選擇，本研究得出以下具體建議：

1. **對於邊緣運算與快速部署（Edge / On-Premise）：**  
   * **首選：Faster-Whisper (CTranslate2)。**  
   * **理由：** 其 INT8 量化在消費級硬體上表現優異，且部署過程簡單（僅需一次轉換），對 Breeze-ASR-25 的繁體中文 Tokenizer 支援最為穩健。適合資源受限或需要快速迭代的場景。  
2. **對於大規模雲端服務（High-Concurrency Cloud）：**  
   * **首選：TensorRT-LLM。**  
   * **理由：** 雖然構建過程複雜，但其 In-flight Batching 與 Paged Attention 技術能顯著提升單卡吞吐量，降低單位請求成本。對於服務大量使用者的 SaaS 平台，這是唯一能充分榨乾 A100/H100 效能的方案。  
3. **對於極致低延遲需求（Ultra-Low Latency）：**  
   * **策略：TensorRT-LLM \+ 投機解碼（需定制開發）。**  
   * **路徑：** 由於缺乏現成的繁體中文草稿模型，建議優先嘗試訓練 **Whisper-Medusa** 頭部（Heads），配合 TensorRT-LLM 運行。這比蒸餾一個完整的 Breeze-Tiny 成本更低，且能有效利用 Breeze-ASR-25 的強大編碼能力，預期可將延遲進一步降低 30-50%。

綜上所述，Breeze-ASR-25 的效能釋放不僅取決於模型本身，更取決於推論引擎與硬體架構的深度適配。開發者應根據實際的併發需求與硬體預算，在 Faster-Whisper 的靈活性與 TensorRT-LLM 的極致效能之間做出權衡。

#### **引用的著作**

1. MediaTek-Research/Breeze-ASR-25 · Hugging Face, 檢索日期：12月 11, 2025， [https://huggingface.co/MediaTek-Research/Breeze-ASR-25](https://huggingface.co/MediaTek-Research/Breeze-ASR-25)  
2. SoybeanMilk/faster-whisper-Breeze-ASR-25 \- Hugging Face, 檢索日期：12月 11, 2025， [https://huggingface.co/SoybeanMilk/faster-whisper-Breeze-ASR-25](https://huggingface.co/SoybeanMilk/faster-whisper-Breeze-ASR-25)  
3. mtkresearch repositories \- GitHub, 檢索日期：12月 11, 2025， [https://github.com/orgs/mtkresearch/repositories](https://github.com/orgs/mtkresearch/repositories)  
4. Converting Your Fine-Tuned Whisper Model to Faster-Whisper Using CTranslate2 \- Medium, 檢索日期：12月 11, 2025， [https://medium.com/@balaragavesh/converting-your-fine-tuned-whisper-model-to-faster-whisper-using-ctranslate2-b272063d3204](https://medium.com/@balaragavesh/converting-your-fine-tuned-whisper-model-to-faster-whisper-using-ctranslate2-b272063d3204)  
5. whisper-ctranslate2 \- PyPI, 檢索日期：12月 11, 2025， [https://pypi.org/project/whisper-ctranslate2/](https://pypi.org/project/whisper-ctranslate2/)  
6. How to Convert Whisper from HF's Transformer format into Ctranslate2 format (needed for FasterWhisper) \- GitHub Gist, 檢索日期：12月 11, 2025， [https://gist.github.com/AmgadHasan/389ca9772e4d505a0d1e9be693064b2e](https://gist.github.com/AmgadHasan/389ca9772e4d505a0d1e9be693064b2e)  
7. Faster Whisper transcription with CTranslate2 \- GitHub, 檢索日期：12月 11, 2025， [https://github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)  
8. How does quantization (such as int8 quantization or using float16) affect the accuracy and speed of Sentence Transformer embeddings and similarity calculations? \- Milvus, 檢索日期：12月 11, 2025， [https://milvus.io/ai-quick-reference/how-does-quantization-such-as-int8-quantization-or-using-float16-affect-the-accuracy-and-speed-of-sentence-transformer-embeddings-and-similarity-calculations](https://milvus.io/ai-quick-reference/how-does-quantization-such-as-int8-quantization-or-using-float16-affect-the-accuracy-and-speed-of-sentence-transformer-embeddings-and-similarity-calculations)  
9. Quantizing Whisper-small: How design choices affect ASR performance \- arXiv, 檢索日期：12月 11, 2025， [https://arxiv.org/pdf/2511.08093](https://arxiv.org/pdf/2511.08093)  
10. LoRA-INT8 Whisper: A Low-Cost Cantonese Speech Recognition Framework for Edge Devices \- PMC \- NIH, 檢索日期：12月 11, 2025， [https://pmc.ncbi.nlm.nih.gov/articles/PMC12431075/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12431075/)  
11. Welcome to TensorRT LLM's Documentation\!, 檢索日期：12月 11, 2025， [https://nvidia.github.io/TensorRT-LLM/](https://nvidia.github.io/TensorRT-LLM/)  
12. NVIDIA TensorRT-LLM \- NVIDIA Docs, 檢索日期：12月 11, 2025， [https://docs.nvidia.com/tensorrt-llm/index.html](https://docs.nvidia.com/tensorrt-llm/index.html)  
13. Generally Available: The fastest, most accurate and cost-efficient Whisper transcription, 檢索日期：12月 11, 2025， [https://www.baseten.co/blog/the-fastest-most-accurate-and-cost-efficient-whisper-transcription/](https://www.baseten.co/blog/the-fastest-most-accurate-and-cost-efficient-whisper-transcription/)  
14. yoonlee666/TensorRT-LLM \- Gitee, 檢索日期：12月 11, 2025， [https://gitee.com/yoonlee666/TensorRT-LLM](https://gitee.com/yoonlee666/TensorRT-LLM)  
15. DéjàVu: KV-cache Streaming for Fast, Fault-tolerant Generative LLM Serving \- arXiv, 檢索日期：12月 11, 2025， [https://arxiv.org/html/2403.01876v1](https://arxiv.org/html/2403.01876v1)  
16. Ultra-Low Latency with NVIDIA TensorRT-LLM \- Moveworks, 檢索日期：12月 11, 2025， [https://www.moveworks.com/us/en/resources/blog/moveworks-achieves-low-latency-with-nvidia-tensorrt-llm](https://www.moveworks.com/us/en/resources/blog/moveworks-achieves-low-latency-with-nvidia-tensorrt-llm)  
17. WhisperLive/TensorRT\_whisper.md at main \- GitHub, 檢索日期：12月 11, 2025， [https://github.com/collabora/WhisperLive/blob/main/TensorRT\_whisper.md](https://github.com/collabora/WhisperLive/blob/main/TensorRT_whisper.md)  
18. Benchmarking NVIDIA TensorRT-LLM \- Jan.ai, 檢索日期：12月 11, 2025， [https://www.jan.ai/post/benchmarking-nvidia-tensorrt-llm](https://www.jan.ai/post/benchmarking-nvidia-tensorrt-llm)  
19. Why is vLLM Outperforming TensorRT-LLM (Nvidia's deployment library)? My Shocking Benchmarks on GPT-OSS-120B with H100 : r/LocalLLaMA \- Reddit, 檢索日期：12月 11, 2025， [https://www.reddit.com/r/LocalLLaMA/comments/1oyawkl/why\_is\_vllm\_outperforming\_tensorrtllm\_nvidias/](https://www.reddit.com/r/LocalLLaMA/comments/1oyawkl/why_is_vllm_outperforming_tensorrtllm_nvidias/)  
20. Official code for "F5-TTS: A Fairytaler that Fakes Fluent and Faithful Speech with Flow Matching" \- GitHub, 檢索日期：12月 11, 2025， [https://github.com/SWivid/F5-TTS](https://github.com/SWivid/F5-TTS)  
21. SpecASR: Accelerating LLM-based Automatic Speech Recognition via Speculative Decoding \- arXiv, 檢索日期：12月 11, 2025， [https://arxiv.org/html/2507.18181v1](https://arxiv.org/html/2507.18181v1)  
22. Speculative Decoding for 2x Faster Whisper Inference \- Google Colab, 檢索日期：12月 11, 2025， [https://colab.research.google.com/github/sanchit-gandhi/notebooks/blob/main/speculative\_decoding.ipynb](https://colab.research.google.com/github/sanchit-gandhi/notebooks/blob/main/speculative_decoding.ipynb)  
23. SpecInfer: Accelerating Large Language Model Serving with Tree-based Speculative Inference and Verification | Request PDF \- ResearchGate, 檢索日期：12月 11, 2025， [https://www.researchgate.net/publication/380150985\_SpecInfer\_Accelerating\_Large\_Language\_Model\_Serving\_with\_Tree-based\_Speculative\_Inference\_and\_Verification](https://www.researchgate.net/publication/380150985_SpecInfer_Accelerating_Large_Language_Model_Serving_with_Tree-based_Speculative_Inference_and_Verification)  
24. Model-free Speculative Decoding for Transformer-based ASR with Token Map Drafting \- Eusipco 2025, 檢索日期：12月 11, 2025， [https://eusipco2025.org/wp-content/uploads/pdfs/0000361.pdf](https://eusipco2025.org/wp-content/uploads/pdfs/0000361.pdf)  
25. distil-whisper (Whisper Distillation) \- Hugging Face, 檢索日期：12月 11, 2025， [https://huggingface.co/distil-whisper](https://huggingface.co/distil-whisper)  
26. How to set the target language for examples in README? · Issue \#130 · huggingface/distil-whisper \- GitHub, 檢索日期：12月 11, 2025， [https://github.com/huggingface/distil-whisper/issues/130](https://github.com/huggingface/distil-whisper/issues/130)  
27. Whisper-Medusa: Using multiple Decoding Heads to Achieve 1.5X Speedup \- Medium, 檢索日期：12月 11, 2025， [https://medium.com/@sgl.yael/whisper-medusa-using-multiple-decoding-heads-to-achieve-1-5x-speedup-7344348ef89b](https://medium.com/@sgl.yael/whisper-medusa-using-multiple-decoding-heads-to-achieve-1-5x-speedup-7344348ef89b)  
28. Whisper in Medusa's Ear: Multi-head Efficient Decoding for Transformer-based ASR \- arXiv, 檢索日期：12月 11, 2025， [https://arxiv.org/html/2409.15869v1](https://arxiv.org/html/2409.15869v1)  
29. Whisper-Medusa: Using multiple Decoding Heads to Achieve 1.5X Speedup, 檢索日期：12月 11, 2025， [https://keshet.technion.ac.il/whisper-medusa-using-multiple-decoding-heads-to-achieve-1-5x-speedup/](https://keshet.technion.ac.il/whisper-medusa-using-multiple-decoding-heads-to-achieve-1-5x-speedup/)  
30. Speculative Sampling — TensorRT-LLM \- GitHub Pages, 檢索日期：12月 11, 2025， [https://nvidia.github.io/TensorRT-LLM/advanced/speculative-decoding.html](https://nvidia.github.io/TensorRT-LLM/advanced/speculative-decoding.html)  
31. Release Notes — TensorRT LLM \- GitHub Pages, 檢索日期：12月 11, 2025， [https://nvidia.github.io/TensorRT-LLM/release-notes.html](https://nvidia.github.io/TensorRT-LLM/release-notes.html)  
32. WhisperLiveKit: The Ultimate Solution for Real-time Speech Recognition \- Skywork ai, 檢索日期：12月 11, 2025， [https://skywork.ai/blog/whisperlivekit-the-ultimate-solution-for-real-time-speech-recognition/](https://skywork.ai/blog/whisperlivekit-the-ultimate-solution-for-real-time-speech-recognition/)  
33. whisperlivekit \- PyPI, 檢索日期：12月 11, 2025， [https://pypi.org/project/whisperlivekit/0.2.2/](https://pypi.org/project/whisperlivekit/0.2.2/)  
34. KV cache reuse — TensorRT-LLM \- GitHub Pages, 檢索日期：12月 11, 2025， [https://nvidia.github.io/TensorRT-LLM/advanced/kv-cache-reuse.html](https://nvidia.github.io/TensorRT-LLM/advanced/kv-cache-reuse.html)  
35. collabora/WhisperLive: A nearly-live implementation of OpenAI's Whisper. \- GitHub, 檢索日期：12月 11, 2025， [https://github.com/collabora/WhisperLive](https://github.com/collabora/WhisperLive)