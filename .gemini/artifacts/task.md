# ASR Benchmark Task Checklist

- [x] 開發 `benchmark_worker.py` (負責單一模型、單一設定下的純淨隔離執行與記憶體/時間測量)
- [x] 開發 `run_benchmark.py` (自動排程各種參數排列疊代，依序跑完所有測試，避免記憶體洩漏與干擾)
- [/] 執行 `run_benchmark.py` 單檔案/多參數測試
    - [ ] `Hermes Agent 完整使用教程_1080p.mp4` x (Faster-Whisper, MLA) x (VAD On, VAD Off)
    - [ ] `馬爾地夫屎蛋介紹.m4a` x (Faster-Whisper, MLA) x (VAD On, VAD Off)
- [ ] 量測並抓取模型 Base VRAM、Peak VRAM 以及 RTF (Real-Time Factor)。
- [ ] 更新 `walkthrough.md` 並繪製比較表格 (Table) 解讀測試結果，用於決定後續 Cloud GPU 架構優化方向。
