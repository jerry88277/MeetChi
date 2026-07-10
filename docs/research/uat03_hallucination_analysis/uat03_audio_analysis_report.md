# uat03 Meeting Pre-Talk Hallucination — Audio Signal Analysis Report

Meeting: `50df45ce` (uat03). Known: the first ~7:52 is Whisper hallucination.
Analysis audio: first 12 minutes (16kHz mono). Window 1.5s, hop **0.5s** (fine grain), x-axis ticks every **15s**.
Boundary: **7:52 (472s)**. Pure numpy/scipy (no librosa/numba).

## First Principle
Whisper hallucination = the model is forced to decode "speech-like non-speech".
Goal: find **signal-dimension features that separate the hallucination region (0-7:52) from the real-speech region (7:52+)**, to build a pre-Whisper gate.

## Discrimination Results (Cohen's d, halluc 0-7:52 vs real 7:52+)

| Rank | Feature | d | Halluc | Real | Interpretation |
|---|---|---|---|---|---|
| 1 | Zero-Crossing Rate | **1.83** | 0.083 | 0.135 | halluc lower -> lacks high-freq |
| 2 | Spectral Centroid | **1.79** | 1310 Hz | 1860 Hz | halluc center of mass low |
| 3 | Speech-band Energy 100-2kHz | **1.46** | 0.78 | 0.67 | halluc energy crammed in low band |
| 4 | Spectral Flatness | **1.30** | 0.36 | 0.49 | halluc more tonal (not white noise) |
| 5 | Spectral Rolloff 85% | **1.28** | 2790 Hz | 3770 Hz | halluc little high-freq |
| 6 | Short-time RMS Variation | 0.57 | 4.9 dB | 6.9 dB | halluc more monotonous/steady |
| 7 | Pitch Periodicity Confidence | 0.39 | 0.36 | 0.41 | weak |
| 8 | **RMS Loudness** | **0.02** | -22.5 dBFS | -22.7 dBFS | **no difference! not a volume issue** |

## Core Insight (MECE)
The hallucination region is **NOT silence** (same -22 dBFS loudness - which is why `audio_stats` flagged it "healthy") and **NOT white noise** (lower flatness = more tonal). It is **low-frequency-dominant, muffled, steady, monotonous** audio - typical of:
- far-field / off-mic pre-meeting chatter (mic distant from speakers)
- HVAC / ambient hum + low-freq reverb
- device playback bleed

=> Enough energy to escape silence detection, yet lacking the **high-frequency articulation (consonants/formants)** of clear near-field speech -> Whisper loops into hallucination.

## Composite Speech-Confidence Gate (deployable)
Score = `z(centroid) + z(rolloff) + z(ZCR)` (strongest 3 features):
- **Hallucination region: 76% below threshold**; **Real region: 95% above threshold** -> a single lightweight feature set separates them effectively.

## Pre-Whisper Processing Recommendations (MECE, simple -> strong)
1. **Spectral gate (highest ROI, lightest)**: per-window centroid/rolloff/ZCR composite score; segments below threshold are **not fed to Whisper** (marked non-speech). Pure numpy/scipy, no model.
2. **Silero VAD instead of energy VAD**: faster-whisper's built-in VAD under-detects low-freq muffled murmur; Silero (learned speech-presence) is more accurate here.
3. **High-pass + articulation check**: hallucination region lacks >2kHz energy -> skip/deweight windows with too-low high-freq energy ratio.
4. **Stack with deployed hallucination-suppression params**: condition_on_previous_text=False + compression/log_prob/no_speech thresholds (live on gpu-asr 00081-h7d).

## Figures (boundary 7:52, English labels, 15s ticks)
- `uat03_signal_features.png` - 8-feature time series (hop 0.5s)
- `uat03_spectrogram.png` - spectrogram (left low-freq muffled vs right high-freq clear)
- `uat03_speech_confidence.png` - composite confidence score + suggested threshold

---

## Axis-B Validation (2026-07-10) — Spectral Gate Feature Design

Per user insight (boundary visible in <750Hz low band; single horizontal line on
prior features fails), tested spectral-STRUCTURE features with per-window optimal
single-threshold balanced accuracy against the 7:52 boundary.

| Feature | Cohen's d | Single-thr bal-acc | Note |
|---|---|---|---|
| **A1. Spectral Tilt (2-4kHz / <750Hz, dB)** | **2.39** | **90%** | strongest single; high=real |
| B1. Low-band CPP (dB) | 1.71 | 84% | harmonic-structure clarity, high=real |
| B2. Low-band(<750Hz) Flatness | 0.89 | 70% | smear=high, structured=low |
| B3. Low-band Spectral Contrast | 0.80 | 68% | harmonic peaks |
| **A1 + B1 (multivariate)** | **2.54** | **92%** | joint shape×structure |
| A1 + B1 + B2 | 2.76 | 92% | marginal gain |

### Validated design conclusion
- The discriminator is **spectral SHAPE + STRUCTURE**, not level (RMS d=0.02).
- **Axis A (spectral tilt)** — energy balance high-band vs the user's <750Hz band —
  is the single best feature (d=2.39, 90%), directly encoding "muffled far-field
  vs articulate near-field".
- **Axis B (low-band CPP)** — harmonic clarity in <750Hz ("clear line vs smear") —
  is complementary; combining A1+B1 reaches **92%** with the decision boundary
  landing at 7:52.
- Figure: `uat03_axisB_validation.png` (each feature's best single threshold shown).

### Recommended gate (to implement)
score = z(spectral_tilt) + z(low_band_CPP); gate-out sustained low-score spans
(hysteresis + min-duration), mask as non-speech before Whisper. Per-meeting
adaptive normalization (median/MAD) for robustness across rooms/mics.
