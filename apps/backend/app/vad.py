import numpy as np
import io
import torch
import logging

logger = logging.getLogger(__name__)

class VADAudioBuffer:
    def __init__(self, sample_rate=16000, silence_threshold=0.4, min_silence_duration=1.0, max_duration=5.0):
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold # Restored to 0.4
        self.min_silence_duration = min_silence_duration # Restored to 1.0 for balanced performance
        self.min_speech_duration = 0.5 # New: filter out speech segments shorter than 0.5s
        self.max_duration = max_duration # Aggressively reduced to 5.0s
        
        self.buffer = io.BytesIO()
        self.silence_duration = 0.0
        self.total_duration = 0.0
        
        self.use_silero = False
        self.model = None
        
        try:
            logger.info("Loading Silero VAD model...")
            # Load Silero VAD from torch hub
            # This requires internet access on first run to download the model (~2MB)
            self.model, _ = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                           model='silero_vad',
                                           force_reload=False,
                                           trust_repo=True)
            self.model.eval()
            self.use_silero = True
            logger.info("Silero VAD loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load Silero VAD: {e}. Fallback to Energy VAD.")
            self.silence_threshold = 0.01 # Reset threshold for Energy VAD fallback

    def process_chunk(self, chunk_bytes, force_speech=False):
        """
        Process a chunk of audio bytes.
        Returns the accumulated audio bytes if a split point is found, otherwise None.
        """
        self.buffer.write(chunk_bytes)
        
        # Convert chunk to numpy for processing
        chunk_np = np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Calculate RMS for Debugging
        rms = np.sqrt(np.mean(chunk_np**2))
        
        chunk_duration = len(chunk_np) / self.sample_rate
        self.total_duration += chunk_duration
        
        is_speech = False
        
        if force_speech:
             is_speech = True
             # logger.info(f"DEBUG: Force Speech Active. RMS={rms:.4f}")
        elif self.use_silero:
            try:
                # Silero VAD (JIT) requires strictly 512 samples at 16kHz
                window_size_samples = 512
                
                # Iterate over sub-chunks (4096 / 512 = 8 checks)
                # If ANY sub-chunk detects speech, the whole 250ms block is considered speech
                for i in range(0, len(chunk_np), window_size_samples):
                    sub_chunk = chunk_np[i : i + window_size_samples]
                    
                    # Ensure correct size (pad if necessary)
                    if len(sub_chunk) != window_size_samples:
                        sub_chunk = np.pad(sub_chunk, (0, window_size_samples - len(sub_chunk)))
                    
                    tensor = torch.from_numpy(sub_chunk)
                    if len(tensor.shape) == 1:
                        tensor = tensor.unsqueeze(0)
                    
                    with torch.no_grad():
                        speech_prob = self.model(tensor, self.sample_rate).item()
                    
                    if speech_prob > self.silence_threshold:
                        is_speech = True
                        break # Stop checking once speech is found
                
                # --- Secondary RMS Check for Hallucination Filtering ---
                # Even if Silero thinks it's speech, if it's too quiet, it's likely noise/hallucination
                # rms = np.sqrt(np.mean(chunk_np**2)) # Already calculated above
                if is_speech and rms < 0.001: 
                    # logger.debug(f"Silero detected speech but RMS low ({rms:.4f}). Ignoring.")
                    is_speech = False

            except Exception as e:
                logger.error(f"Silero inference failed: {e}")
                self.use_silero = False # Switch to fallback immediately
        
        # Fallback Logic (if Silero failed or not loaded)
        if not self.use_silero:
            # rms = np.sqrt(np.mean(chunk_np**2)) # Already calculated
            is_speech = rms > 0.005

        # Debug Log
        # logger.info(f"VAD Check: RMS={rms:.5f}, Silero={self.use_silero}, Force={force_speech} -> Speech={is_speech}")

        # VAD State Machine
        if not is_speech:
            self.silence_duration += chunk_duration
        else:
            self.silence_duration = 0.0 # Reset silence counter if speech detected
            
        # Decision Logic
        should_split = False
        
        # 1. Silence split
        # If we have accumulated enough audio (> 1s) and detected a silence gap
        if self.total_duration > 1.0 and self.silence_duration >= self.min_silence_duration:
             should_split = True
             logger.info(f"Split triggered by silence. Total: {self.total_duration:.2f}s, Silence: {self.silence_duration:.2f}s")
             
        # 2. Max duration split (Force split to avoid latency)
        elif self.total_duration >= self.max_duration:
             should_split = True
             logger.info(f"Split triggered by max duration. Total: {self.total_duration:.2f}s")
             
        if should_split:
            return self.flush()
            
        return None

    def flush(self):
        """Return the current buffer content and reset."""
        buffer_size = self.buffer.tell()
        if buffer_size == 0:
            return None
            
        # Read data from buffer to calculate RMS
        self.buffer.seek(0)
        data = self.buffer.read()
        
        # Convert to numpy for RMS calculation
        flushed_np = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        flushed_rms = np.sqrt(np.mean(flushed_np**2))

        # Calculate actual duration of the flushed data
        flushed_duration = buffer_size / (self.sample_rate * 2) # 2 bytes per sample (Int16)
        
        # Filter very short segments (less than min_speech_duration) to prevent hallucinations
        if flushed_duration < self.min_speech_duration:
            logger.info(f"Flushed segment too short ({flushed_duration:.2f}s < {self.min_speech_duration}s), discarded. RMS={flushed_rms:.5f}")
            # Reset
            self.buffer = io.BytesIO()
            self.silence_duration = 0.0
            self.total_duration = 0.0
            return None

        # Filter segments that are essentially silent (very low RMS)
        SILENT_RMS_THRESHOLD = 0.0001 # Threshold for effectively silent audio
        if flushed_rms < SILENT_RMS_THRESHOLD:
            logger.info(f"Flushed segment too silent (RMS={flushed_rms:.5f} < {SILENT_RMS_THRESHOLD:.5f}), discarded.")
            # Reset
            self.buffer = io.BytesIO()
            self.silence_duration = 0.0
            self.total_duration = 0.0
            return None

        # self.buffer.seek(0) # Already seeked to 0
        # data = self.buffer.read() # Already read

        # Reset
        self.buffer = io.BytesIO()
        self.silence_duration = 0.0
        self.total_duration = 0.0
        
        return data

    def snapshot(self):
        """Return the current buffer content WITHOUT resetting. Used for partial transcription."""
        if self.buffer.tell() == 0:
            return None
        
        current_pos = self.buffer.tell()
        self.buffer.seek(0)
        data = self.buffer.read()
        self.buffer.seek(current_pos) # Restore position
        return data
