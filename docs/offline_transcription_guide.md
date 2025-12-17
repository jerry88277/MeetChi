# 離線轉錄腳本使用指南 (Offline Transcription Guide)

本文件說明如何使用 `apps/backend/scripts/exec_whisperx_task_v1.2.py` 腳本進行高品質的離線語音轉錄。該腳本整合了 **WhisperX** 模型、**OpenCC** 簡繁轉換以及 **CKIP** 斷詞工具，能產生精確且符合繁體中文閱讀習慣的字幕文件。

## 1. 環境準備 (Prerequisites)

此腳本依賴於後端的 Python 環境。

1. 開啟終端機，進入後端目錄：
    ```bash
    cd apps/backend
    ```
2. 啟動虛擬環境：
    *   **Windows**: `.\.venv\Scripts\Activate.ps1`
    *   **Linux/Mac**: `source .venv/bin/activate`

## 2. 設定檔配置 (Configuration)

腳本執行前會讀取同目錄下的 `config.json` 檔案。請確保 `apps/backend/scripts/config.json` 存在且內容正確。

**範例 `config.json`:**
```json
{
    "as_dir_path": "D:\\Path\\To\\AudioSource",   // 原始音訊檔存放目錄
    "aslc_dir_path": "D:\\Path\\To\\AudioMono",   // 轉檔後(單聲道)音訊存放目錄
    "tr_dir_path": "D:\\Path\\To\\Transcript",    // 轉錄結果輸出目錄
    "log_path": "D:\\Path\\To\\Logs",             // 日誌存放目錄
    "device": "cuda",                             // 運算裝置 (cuda 或 cpu)
    "model_size": "large-v3",                     // 模型大小
    "compute_type": "int8",                       // 計算精度 (int8 或 float16)
    "batch_size": 4,                              // 批次大小
    "chunk_size": 30,                             // 音訊切分長度 (秒)
    "hf_token": "YOUR_HUGGING_FACE_TOKEN",        // (若需講者分離) Hugging Face Token
    "print_progress": true,
    "return_char_alignments": false,
    "min_speaker": 1,
    "max_speaker": 10
}
```

*注意：`as_filename` 參數僅需提供**檔名**，腳本會自動到 `as_dir_path` 下尋找該檔案。*

## 3. 執行指令 (Usage)

基本語法：
```bash
python scripts/exec_whisperx_task_v1.2.py <音訊檔名> <講者分離開關>
```

*   **`<音訊檔名>`**: 位於 `as_dir_path` 中的檔案名稱 (包含副檔名，如 `test_audio.wav`)。
*   **`<講者分離開關>`**: `0` 表示關閉，`1` 表示開啟 (需設定 Hugging Face Token)。

**範例 1：基本轉錄 (無講者分離)**
```bash
python scripts/exec_whisperx_task_v1.2.py "meeting_recording.mp3" 0
```

**範例 2：轉錄並進行講者分離 (Speaker Diarization)**
```bash
python scripts/exec_whisperx_task_v1.2.py "podcast_interview.wav" 1
```

## 4. 輸出結果 (Output)

腳本執行成功後，會在 `tr_dir_path` 設定的目錄下生成以下資料夾與檔案：

*   **`txt/`**: 純文字檔，包含時間戳記。
    *   格式: `[00:00:00,000 --> 00:00:05,000] 逐字稿內容...`
*   **`srt/`**: 標準 SRT 字幕檔，適合影片播放器掛載。
*   **`vtt/`**: WebVTT 字幕檔，適合網頁播放。
*   **`tsv/`**: 定界符分隔檔，包含 `Start`, `End`, `Text`, `Speaker` 欄位，方便匯入 Excel 分析。
*   **`json/`**: 包含完整詳細資訊 (Word-level timestamps) 的原始資料。

## 5. 功能特色 (Features)

*   **自動轉單聲道**: 腳本會自動呼叫 `ffmpeg` 將輸入音訊轉換為 16kHz 單聲道格式，以符合 Whisper 輸入要求。
*   **繁體優化**: 內建 `OpenCC ('s2twp')`，自動將 Whisper 可能輸出的簡體中文轉換為台灣正體中文。
*   **斷詞優化**: 針對繁體中文語境，使用 `CkipWordSegmenter` 進行斷詞處理，提升時間軸對齊的準確度。
*   **字幕優化**: 使用 `SubtitlesProcessor` 智慧斷句，避免字幕過長或斷在不自然的位置。

## 6. 常見問題 (Troubleshooting)

*   **找不到檔案**: 請確認 `config.json` 中的 `as_dir_path` 設定正確，且檔案確實在該目錄下。
*   **Out of Memory (OOM)**: 若 GPU 記憶體不足，請在 `config.json` 中將 `batch_size` 調小 (如 `1`)，或將 `compute_type` 設為 `int8`。
*   **FFmpeg 錯誤**: 請確保系統已安裝 FFmpeg 並已加入 PATH 環境變數。
