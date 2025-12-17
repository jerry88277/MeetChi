# TensorRT-LLM 與投機解碼 (Speculative Decoding) 研究計畫

**目標**: 評估並規劃將 `Breeze-ASR-25` 遷移至 NVIDIA TensorRT-LLM 架構，以利用其 **In-flight Batching** 與 **Speculative Decoding** 技術，達成極致的推論吞吐量與低延遲。

## 1. 背景與動機

目前系統使用 **Faster-Whisper (CTranslate2)**，在單一請求或低併發場景下表現優異且易於部署。然而，針對高併發雲端服務或需要極致低延遲 (Ultra-Low Latency) 的場景，**TensorRT-LLM** 提供了更強大的算子融合與記憶體管理機制。此外，TensorRT-LLM 原生支援投機解碼，這是在不犧牲模型品質的前提下，突破自回歸解碼速度瓶頸的關鍵技術。

## 2. 核心技術組件

*   **TensorRT-LLM**: NVIDIA 推出的高效能 LLM 推論庫。
*   **Breeze-ASR-25**: MediaTek Research 開發的繁體中文優化 Whisper 模型。
*   **Speculative Decoding (投機解碼)**: 使用小模型 (Draft Model) 快速生成 token，再由大模型 (Target Model) 驗證，以減少記憶體存取次數。

## 3. 實作路徑 (Implementation Path)

由於 TensorRT-LLM 的環境依賴複雜，強烈建議在 **NVIDIA Docker Container** 中進行開發與構建。

### 3.1 環境準備

*   **Docker Image**: `nvcr.io/nvidia/tensorrt-llm:latest` (需配合 Host 的 Driver 版本)。
*   **Hardware**: NVIDIA GPU (Ampere 或 Hopper 架構推薦，如 A100, H100, RTX 30/40 系列)。
*   **Dependencies**: TensorRT, CUDA Toolkit, cuDNN (包含在 Docker 中)。

### 3.2 模型轉換 (Model Conversion)

需將 Hugging Face 的 PyTorch Checkpoint 轉換為 TensorRT-LLM 的中間格式。

1.  **下載原始模型**: `MediaTek-Research/Breeze-ASR-25`。
2.  **轉換 Encoder**:
    ```bash
    python3 examples/whisper/convert_checkpoint.py \
        --model_dir MediaTek-Research/Breeze-ASR-25 \
        --output_dir ./tllm_checkpoint \
        --model_type whisper
    ```
    *注意*: 需確認 `convert_checkpoint.py` 是否支援 Breeze 的自定義 Tokenizer/Vocab size。若 Breeze 修改了模型架構 (如層數)，可能需要修改轉換腳本。

### 3.3 引擎構建 (Engine Building)

將轉換後的 Checkpoint 編譯為針對特定 GPU 優化的 TensorRT Engine (`.engine` 檔)。

1.  **構建 Encoder Engine**:
    ```bash
    trtllm-build --checkpoint_dir ./tllm_checkpoint/encoder \
                 --output_dir ./engines/encoder \
                 --paged_kv_cache disable
    ```
2.  **構建 Decoder Engine**:
    ```bash
    trtllm-build --checkpoint_dir ./tllm_checkpoint/decoder \
                 --output_dir ./engines/decoder \
                 --use_paged_context_fmha enable \
                 --use_gemm_plugin float16
    ```

### 3.4 投機解碼實作 (Speculative Decoding)

這是最挑戰也最具潛力的部分。

*   **策略 A: 蒸餾草稿模型 (Distilled Draft Model)**
    *   **方法**: 訓練一個由 Breeze-ASR-25 蒸餾而來的微型模型 (如 2 層 Decoder)。
    *   **優點**: 加速穩定。
    *   **缺點**: 訓練成本高，需準備大量繁體中文語音數據。
*   **策略 B: Medusa Heads (推薦)**
    *   **方法**: 凍結 Breeze 主幹，僅訓練多個預測頭 (Medusa Heads) 來預測未來 N 個 token。
    *   **優點**: 訓練快，顯存增加少，TensorRT-LLM 支援。
    *   **TensorRT 整合**: 需在構建 Decoder Engine 時啟用 `--speculative_decoding_mode` 並提供 Medusa Heads 的權重。

## 4. 風險與挑戰

1.  **模型相容性**: Breeze-ASR-25 若有非標準的架構修改，可能導致 TensorRT 轉換失敗，需深入源碼修改轉換邏輯。
2.  **硬體綁定**: 編譯出的 Engine 無法跨 GPU 架構使用 (如 A100 編譯的不能在 T4 跑)，增加了部署的運維複雜度。
3.  **草稿模型缺乏**: 目前沒有現成的 "Breeze-Tiny"，若要走投機解碼，必須自行投入資源進行蒸餾訓練或 Medusa Head 訓練。

## 5. 結論

遷移至 TensorRT-LLM 是一個高投入、高回報的工程。建議在以下條件滿足時啟動：
1.  **Faster-Whisper 效能遭遇瓶頸** (如單卡無法支撐目前的併發量)。
2.  **有專門的 AI 工程師** 能處理 CUDA/C++ 層級的除錯與模型訓練 (針對草稿模型)。
3.  **基礎設施固定**，能確保生產環境 GPU 型號一致。

短期內，直接使用 **Faster-Whisper (INT8)** 配合 **Breeze-ASR-25** 仍是性價比最高的選擇。
