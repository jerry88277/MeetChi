# Pyannote Speaker Diarization - Model Manifest

## 模型資訊

| 項目 | 值 |
|------|------|
| **模型名稱** | `pyannote/speaker-diarization-community-1` |
| **pyannote.audio 版本** | `4.0.0` (config.yaml 指定) |
| **授權** | CC-BY-4.0 |
| **下載日期** | 2026-06-15 |
| **HuggingFace 來源** | https://huggingface.co/pyannote/speaker-diarization-community-1 |

## GCS 存放路徑

```
gs://prj-ai-meetchi-du-meetchi-audio/models/pyannote/speaker-diarization-community-1/
├── config.yaml                          # Pipeline 設定
├── segmentation/pytorch_model.bin       # 5.7 MB - 語音分段模型
├── embedding/pytorch_model.bin          # 26 MB  - 講者嵌入模型 (wespeaker-voxceleb-resnet34-LM)
├── plda/plda.npz                        # 131 KB - PLDA 評分
├── plda/xvec_transform.npz             # 132 KB - X-vector 轉換
└── README.md
```

**總大小**: ~32 MB

## 子模型組成

| 子模型 | 用途 | 來源 |
|--------|------|------|
| Segmentation | 語音活動偵測 + 重疊偵測 | pyannote/segmentation-3.0 |
| Embedding | 講者向量提取 | pyannote/wespeaker-voxceleb-resnet34-LM |
| PLDA | 講者聚類評分 | 內建 VBx clustering |

## Pipeline 參數 (config.yaml)

```yaml
pipeline:
  name: pyannote.audio.pipelines.SpeakerDiarization
  params:
    clustering: VBxClustering
    segmentation_batch_size: 32
    embedding_batch_size: 32
    embedding_exclude_overlap: true

params:
  clustering:
    threshold: 0.6
    Fa: 0.07
    Fb: 0.8
  segmentation:
    min_duration_off: 0.0
```

## Docker Image 整合方式

```dockerfile
# 在建置時從 GCS 拉取模型
FROM python:3.12-slim AS base

# 安裝 pyannote.audio
RUN pip install pyannote.audio==4.0.0 --no-cache-dir

# 複製模型到 image 中 (build 時從 GCS 下載)
COPY models/pyannote/speaker-diarization-community-1 /app/models/pyannote/speaker-diarization-community-1

# 使用本地模型
ENV PYANNOTE_MODEL_PATH=/app/models/pyannote/speaker-diarization-community-1
```

## 載入方式 (Python)

```python
from pyannote.audio import Pipeline

# 從本地路徑載入（不需要 HF token）
pipeline = Pipeline.from_pretrained(
    "/app/models/pyannote/speaker-diarization-community-1"
)

# 若有 GPU
import torch
pipeline.to(torch.device("cuda"))

# 執行 diarization
diarization = pipeline("audio.wav")
for turn, _, speaker in diarization.itertracks(yield_label=True):
    print(f"[{turn.start:.1f}s → {turn.end:.1f}s] {speaker}")
```

## 版本鎖定策略

- 模型權重固定存於 GCS，不隨 pip 更新而改變
- `pyannote.audio` pip 套件版本鎖定為 `4.0.0`
- 如需升級模型，重新從 HuggingFace 下載並更新此文件
