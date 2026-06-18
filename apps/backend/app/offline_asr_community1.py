"""
offline_asr_community1.py — EXPERIMENTAL: pyannote/speaker-diarization-community-1

命名規則：檔名後綴 _community1 代表此為實驗性版本，使用 pyannote.audio v4.0。
與 offline_asr.py (穩定版 pyannote 3.1) 並存，透過環境變數 DIARIZATION_MODEL=community-1 切換。

架構差異（相較 BreezeASRProvider）：
  - 轉錄層: faster-whisper (CTranslate2) ← 完全相同，不更動
  - 對齊層: whisperx.load_align_model / whisperx.align ← 完全相同
  - 分離層: pyannote/speaker-diarization-community-1 (v4.0) ← 此檔案的核心替換
  - 對齊邏輯: 自實作 _assign_speakers_to_segments_v4() ← 替換 whisperx.assign_word_speakers

已知限制（2026-04）：
  - 需要 pyannote.audio >= 4.0，與 whisperx 的 diarization 封裝不相容
  - 不使用 whisperx.DiarizationPipeline，直接呼叫 pyannote Pipeline
  - exclusive_speaker_diarization 屬性確保無重疊說話者段落

測試方法：
  部署 v13-community1 revision（流量 0%），直接 cURL 測試後比較結果。
"""

import os
import logging
import asyncio
from collections import Counter
from typing import List, Dict, Optional

from app.offline_asr import (
    OfflineASRProvider,
    ASRSegment,
    ASRResult,
    BreezeASRConfig,
)

logger = logging.getLogger(__name__)


# ============================================
# Community-1 Provider
# ============================================

class BreezeASRCommunity1Provider(OfflineASRProvider):
    """
    Experimental ASR provider using pyannote/speaker-diarization-community-1.

    Pipeline:
      1. faster-whisper transcribe (CTranslate2) ← same as BreezeASRProvider
      2. WhisperX forced alignment (wav2vec2)    ← same as BreezeASRProvider
      3. pyannote v4.0 speaker diarization        ← REPLACED (community-1 model)
      4. Custom speaker assignment (v4 API)       ← REPLACED (_assign_speakers_to_segments_v4)

    Requires:
      - HF token with access to pyannote/speaker-diarization-community-1
        (Accept terms at: https://huggingface.co/pyannote/speaker-diarization-community-1)
      - pyannote.audio >= 4.0.0
    """

    def __init__(self, config: Optional[BreezeASRConfig] = None):
        self.config = config or BreezeASRConfig(
            hf_token=os.getenv("HF_AUTH_TOKEN") or os.getenv("HF_TOKEN"),
        )
        self._model = None
        self._initialized = False

    @property
    def provider_name(self) -> str:
        return "Breeze-ASR-25-Community1 (CTranslate2 + pyannote v4.0)"

    def is_available(self) -> bool:
        """Check if faster-whisper is importable."""
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def _resolve_device(self) -> str:
        if self.config.device != "auto":
            return self.config.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def _resolve_compute_type(self, device: str) -> str:
        if self.config.compute_type != "auto":
            return self.config.compute_type
        return "float16" if device == "cuda" else "int8"

    def _load_model(self):
        """Lazy-load the faster-whisper model (same as BreezeASRProvider)."""
        if self._model is not None:
            return

        from faster_whisper import WhisperModel

        device = self._resolve_device()
        compute_type = self._resolve_compute_type(device)

        logger.info(
            f"[Community1] Loading Breeze ASR model: {self.config.model_name} "
            f"(device={device}, compute_type={compute_type})"
        )
        self._model = WhisperModel(
            self.config.model_name,
            device=device,
            compute_type=compute_type,
        )
        self._initialized = True
        logger.info("[Community1] Breeze ASR model loaded successfully.")

    # ------------------------------------------------------------------
    # Step 1 + 2: Transcription + Alignment (identical to BreezeASRProvider)
    # ------------------------------------------------------------------

    def _transcribe_sync(self, audio_path: str, language: str) -> ASRResult:
        """Full pipeline: CT2 transcription → wav2vec2 alignment → community-1 diarization."""
        self._load_model()

        # --- Step 1: CTranslate2 Transcription ---
        logger.info(f"[Community1] Step 1/3: Transcribing {audio_path}")
        segments_iter, info = self._model.transcribe(
            audio_path,
            language=language,
            beam_size=self.config.beam_size,
            vad_filter=self.config.vad_filter,
            vad_parameters=self.config.vad_parameters,
            word_timestamps=True,
        )

        raw_segments = list(segments_iter)
        logger.info(
            f"[Community1] Transcription done: {len(raw_segments)} segments, "
            f"language={info.language}, prob={info.language_probability:.2f}, "
            f"duration={info.duration:.1f}s"
        )

        if not raw_segments:
            return ASRResult(segments=[], language=language, duration=info.duration)

        asr_segments = [
            ASRSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                confidence=getattr(seg, 'avg_logprob', getattr(seg, 'avg_log_prob', 0.0)),
                language=language,
                words=[
                    {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                    for w in (seg.words or [])
                ],
            )
            for seg in raw_segments
        ]

        # --- Step 2: WhisperX Alignment (wav2vec2) ---
        asr_segments = self._try_whisperx_alignment(audio_path, asr_segments, language)

        # --- Step 3: Community-1 Diarization ---
        if self.config.enable_diarization:
            asr_segments, speaker_embeddings = self._try_diarization_community1(audio_path, asr_segments)
        else:
            speaker_embeddings = {}

        num_speakers = len(set(s.speaker for s in asr_segments if s.speaker))

        return ASRResult(
            segments=asr_segments,
            language=language,
            duration=info.duration,
            num_speakers=num_speakers,
            speaker_embeddings=speaker_embeddings,
        )

    def _try_whisperx_alignment(
        self, audio_path: str, segments: List[ASRSegment], language: str
    ) -> List[ASRSegment]:
        """WhisperX forced alignment — identical to BreezeASRProvider."""
        try:
            import whisperx

            device = self._resolve_device()
            logger.info("[Community1] Step 2/3: WhisperX alignment (wav2vec2)")

            audio = whisperx.load_audio(audio_path)
            align_model, align_metadata = whisperx.load_align_model(
                language_code=language, device=device
            )

            whisperx_segments = [
                {"start": s.start, "end": s.end, "text": s.text} for s in segments
            ]
            result = whisperx.align(
                whisperx_segments, align_model, align_metadata, audio, device
            )

            aligned = result.get("segments", [])
            if aligned:
                updated = [
                    ASRSegment(
                        start=a.get("start", 0),
                        end=a.get("end", 0),
                        text=a.get("text", ""),
                        language=language,
                        words=a.get("words", []),
                    )
                    for a in aligned
                ]
                logger.info(f"[Community1] Alignment done: {len(updated)} segments")
                return updated

        except ImportError:
            logger.info("[Community1] WhisperX not available, skipping alignment")
        except Exception as e:
            logger.warning(f"[Community1] Alignment failed: {e}, using raw timestamps")

        return segments

    # ------------------------------------------------------------------
    # Step 3: Community-1 Diarization (CORE DIFFERENCE)
    # ------------------------------------------------------------------

    def _build_community1_pipeline(self, device: str):
        """
        Load pyannote/speaker-diarization-community-1 (v4.0 API).

        Loading strategy (ordered):
          1. Local path from PYANNOTE_MODEL_PATH env var (baked into Docker image)
          2. HuggingFace Hub download with token authentication

        pyannote v4.0 API changes vs v3.x:
          - Removed: use_auth_token parameter
          - Use: token= parameter OR session login via huggingface_hub.login()
          - New: output.exclusive_speaker_diarization property
        """
        import torch as _torch

        # Strategy 1: Load from local baked model path (no network/token needed)
        local_model_path = os.getenv("PYANNOTE_MODEL_PATH", "")
        if local_model_path and os.path.isdir(local_model_path):
            config_path = os.path.join(local_model_path, "config.yaml")
            if os.path.isfile(config_path):
                try:
                    from pyannote.audio import Pipeline

                    logger.info(f"[Community1] Loading pipeline from local path: {local_model_path}")
                    pipeline = Pipeline.from_pretrained(config_path)

                    if pipeline is None:
                        raise RuntimeError("Pipeline.from_pretrained returned None for local model")

                    pipeline.to(_torch.device(device))
                    logger.info("[Community1] pyannote pipeline loaded from local model (offline)")
                    return pipeline

                except Exception as e:
                    logger.warning(f"[Community1] Local model load failed: {e}, trying HF Hub...")

        # Strategy 2: Fall back to HuggingFace Hub download
        import huggingface_hub

        hf_token = self.config.hf_token

        # Set session-level authentication
        try:
            huggingface_hub.login(token=hf_token, add_to_git_credential=False)
            logger.info("[Community1] HuggingFace session authenticated via login()")
        except Exception as e:
            logger.warning(f"[Community1] huggingface_hub.login() failed: {e}")

        # Load community-1 pipeline via pyannote v4.0 API
        try:
            from pyannote.audio import Pipeline

            try:
                pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-community-1",
                    token=hf_token,
                )
            except TypeError:
                logger.info("[Community1] token= kwarg not supported, using session token")
                pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-community-1",
                )

            if pipeline is None:
                raise RuntimeError(
                    "Pipeline.from_pretrained returned None. "
                    "Did you accept the terms at: "
                    "https://huggingface.co/pyannote/speaker-diarization-community-1?"
                )

            pipeline.to(_torch.device(device))
            logger.info("[Community1] pyannote/speaker-diarization-community-1 loaded from HF Hub")
            return pipeline

        except Exception as e:
            raise RuntimeError(
                f"[Community1] Failed to load community-1 pipeline: {e}\n"
                "Ensure:\n"
                "  1. PYANNOTE_MODEL_PATH points to local model dir, OR\n"
                "  2. HF token is valid and terms accepted at "
                "https://huggingface.co/pyannote/speaker-diarization-community-1\n"
                "  3. pyannote.audio >= 4.0.0 is installed"
            )

    def _assign_speakers_to_segments_v4(
        self,
        segments: List[ASRSegment],
        diarization_output,  # DiarizeOutput (v4.0) or pyannote.core.Annotation
    ) -> List[ASRSegment]:
        """
        Self-implemented speaker assignment for pyannote v4.0 output.
        Replaces whisperx.assign_word_speakers() which is incompatible with v4.0 API.

        Strategy:
          - Use exclusive_speaker_diarization if available (no overlaps, cleaner)
          - Fall back to standard itertracks if exclusive property not available
          - For each ASRSegment, find speaker with maximum time overlap
          - For word-level: assign speaker to each word individually

        Args:
            segments: List of ASRSegment with word timestamps from CT2 + wav2vec2
            diarization_output: pyannote.core.Annotation or DiarizeOutput from pipeline()

        Returns:
            segments with .speaker field populated
        """
        # Try exclusive_speaker_diarization (pyannote v4.0 community-1 feature)
        try:
            diar_iter = list(diarization_output.exclusive_speaker_diarization.itertracks(yield_label=True))
            logger.info(
                f"[Community1] Using exclusive_speaker_diarization "
                f"({len(diar_iter)} turns)"
            )
        except AttributeError:
            # Fallback: standard itertracks
            main_annotation = getattr(diarization_output, "speaker_diarization", diarization_output)
            diar_iter = list(main_annotation.itertracks(yield_label=True))
            logger.info(
                f"[Community1] exclusive_speaker_diarization not available, "
                f"using standard itertracks ({len(diar_iter)} turns)"
            )

        def _find_dominant_speaker(seg_start: float, seg_end: float) -> Optional[str]:
            """Find speaker with maximum overlap in [seg_start, seg_end]."""
            overlaps: Dict[str, float] = {}
            for turn, _, speaker in diar_iter:
                overlap = min(seg_end, turn.end) - max(seg_start, turn.start)
                if overlap > 0:
                    overlaps[speaker] = overlaps.get(speaker, 0) + overlap
            if overlaps:
                return max(overlaps, key=overlaps.get)
            return None

        for seg in segments:
            # Assign speaker to segment
            seg.speaker = _find_dominant_speaker(seg.start, seg.end)

            # Assign speaker to individual words (for word-level granularity)
            updated_words = []
            for word in seg.words:
                w_start = word.get("start", seg.start)
                w_end = word.get("end", seg.end)
                word["speaker"] = _find_dominant_speaker(w_start, w_end) or seg.speaker
                updated_words.append(word)
            seg.words = updated_words

            # Fallback: infer speaker from majority of words if segment-level missed
            if not seg.speaker and seg.words:
                word_speakers = [w.get("speaker") for w in seg.words if w.get("speaker")]
                if word_speakers:
                    seg.speaker = Counter(word_speakers).most_common(1)[0][0]

        return segments

    def _try_diarization_community1(
        self, audio_path: str, segments: List[ASRSegment]
    ) -> tuple:
        """Run pyannote community-1 diarization + custom speaker assignment.

        Returns:
            (segments, speaker_embeddings) where speaker_embeddings is a dict
            mapping speaker label → centroid embedding (list of floats).
            If diarization fails, returns (segments, {}).
        """
        if not self.config.hf_token:
            logger.warning(
                "[Community1] HF_TOKEN not set, skipping diarization. "
                "Set HF_AUTH_TOKEN env var."
            )
            return segments, {}

        try:
            device = self._resolve_device()
            logger.info("[Community1] Step 3/3: Speaker diarization (community-1)")

            pipeline = self._build_community1_pipeline(device)

            import torchaudio
            
            # Load audio to memory to avoid pyannote/torchcodec AudioDecoder bug
            waveform, sample_rate = torchaudio.load(audio_path)
            audio_input = {"waveform": waveform, "sample_rate": sample_rate}

            # Run diarization
            diarization_output = pipeline(
                audio_input,
                min_speakers=self.config.min_speakers,
                max_speakers=self.config.max_speakers,
            )

            # Log diarization summary
            speakers_found = set()
            main_annotation = getattr(diarization_output, "speaker_diarization", diarization_output)
            for _, _, speaker in main_annotation.itertracks(yield_label=True):
                speakers_found.add(speaker)
            logger.info(
                f"[Community1] Diarization done: {len(speakers_found)} speakers — {speakers_found}"
            )

            # Assign speakers to segments (self-implemented, no whisperx dependency)
            segments = self._assign_speakers_to_segments_v4(segments, diarization_output)

            num_assigned = sum(1 for s in segments if s.speaker)
            logger.info(
                f"[Community1] Speaker assignment done: "
                f"{num_assigned}/{len(segments)} segments assigned"
            )

            # Phase B: Extract per-speaker centroid embeddings for cross-chunk linking
            speaker_embeddings = self._extract_speaker_embeddings(
                pipeline, waveform, sample_rate, main_annotation, speakers_found
            )

            return segments, speaker_embeddings

        except ImportError as e:
            logger.warning(f"[Community1] Import error, skipping diarization: {e}")
        except Exception as e:
            logger.error(f"[Community1] Diarization failed: {e}", exc_info=True)

        return segments, {}

    def _extract_speaker_embeddings(
        self,
        pipeline,
        waveform,
        sample_rate: int,
        annotation,
        speakers: set,
    ) -> Dict[str, List[float]]:
        """Extract per-speaker centroid embeddings using pyannote's internal embedding model.

        Strategy:
          1. Access the pipeline's embedding model (wespeaker/speechbrain)
          2. For each speaker, collect their longest segments (up to 30s total)
          3. Extract embeddings from those segments
          4. Average to get centroid embedding per speaker

        Returns:
            {"SPEAKER_00": [float, ...], "SPEAKER_01": [float, ...]}
        """
        import torch
        import numpy as np

        embeddings_dict: Dict[str, List[float]] = {}

        try:
            # Access pyannote's internal embedding model
            # Pipeline structure: pipeline._embedding (or pipeline.embedding)
            embedding_model = getattr(pipeline, "_embedding", None)
            if embedding_model is None:
                embedding_model = getattr(pipeline, "embedding", None)
            if embedding_model is None:
                # Try accessing via klass attribute (pyannote 4.x internals)
                for attr_name in dir(pipeline):
                    attr = getattr(pipeline, attr_name, None)
                    if hasattr(attr, "__call__") and "embed" in attr_name.lower():
                        embedding_model = attr
                        break

            if embedding_model is None:
                logger.warning("[Community1] Cannot find embedding model in pipeline, skipping embedding extraction")
                return {}

            logger.info(f"[Community1] Extracting speaker embeddings for {len(speakers)} speakers")

            # Resample to 16kHz if needed (standard for speaker embeddings)
            if sample_rate != 16000:
                import torchaudio.transforms as T
                resampler = T.Resample(sample_rate, 16000)
                waveform_16k = resampler(waveform)
                sr = 16000
            else:
                waveform_16k = waveform
                sr = sample_rate

            # Ensure mono
            if waveform_16k.shape[0] > 1:
                waveform_16k = waveform_16k.mean(dim=0, keepdim=True)

            for speaker in speakers:
                # Collect segments for this speaker (sorted by duration, longest first)
                speaker_turns = []
                for turn, _, spk in annotation.itertracks(yield_label=True):
                    if spk == speaker:
                        speaker_turns.append((turn.start, turn.end, turn.end - turn.start))
                speaker_turns.sort(key=lambda x: x[2], reverse=True)

                # Take up to 30s of audio from longest segments
                total_dur = 0.0
                selected_segments = []
                for start, end, dur in speaker_turns:
                    if total_dur >= 30.0:
                        break
                    selected_segments.append((start, end))
                    total_dur += dur

                if not selected_segments:
                    continue

                # Extract audio clips and compute embeddings
                chunk_embeddings = []
                for seg_start, seg_end in selected_segments:
                    start_sample = int(seg_start * sr)
                    end_sample = int(seg_end * sr)
                    # Clamp to waveform bounds
                    end_sample = min(end_sample, waveform_16k.shape[1])
                    if end_sample <= start_sample:
                        continue

                    clip = waveform_16k[:, start_sample:end_sample]

                    # Minimum 0.5s for meaningful embedding
                    if clip.shape[1] < sr * 0.5:
                        continue

                    try:
                        # pyannote embedding model expects {"waveform": tensor, "sample_rate": int}
                        with torch.no_grad():
                            emb = embedding_model({"waveform": clip.unsqueeze(0), "sample_rate": sr})
                            # emb shape: (1, embedding_dim) or (batch, 1, embedding_dim)
                            if emb.dim() == 3:
                                emb = emb.squeeze(1)
                            emb = emb.squeeze(0).cpu().numpy()
                            chunk_embeddings.append(emb)
                    except Exception as e:
                        logger.debug(f"[Community1] Embedding extraction failed for {speaker} segment: {e}")
                        continue

                if chunk_embeddings:
                    # Average embeddings to get centroid
                    centroid = np.mean(chunk_embeddings, axis=0)
                    # L2-normalize for cosine similarity
                    norm = np.linalg.norm(centroid)
                    if norm > 0:
                        centroid = centroid / norm
                    embeddings_dict[speaker] = centroid.tolist()

            logger.info(
                f"[Community1] Speaker embeddings extracted: "
                f"{len(embeddings_dict)}/{len(speakers)} speakers "
                f"(dim={len(next(iter(embeddings_dict.values()), []))})"
            )

        except Exception as e:
            logger.warning(f"[Community1] Speaker embedding extraction failed (non-fatal): {e}")

        return embeddings_dict

    async def transcribe_with_diarization(
        self,
        audio_path: str,
        language: str = "zh",
        **kwargs,
    ) -> ASRResult:
        """Async wrapper — runs sync pipeline in thread pool."""
        logger.info(
            f"[Community1] Starting transcription: {audio_path} (lang={language})"
        )
        return await asyncio.to_thread(self._transcribe_sync, audio_path, language)
