// audio-worklet-processor.ts
// This file runs in a separate AudioWorklet thread.
import { NoiseSuppressor } from 'sapphi-red/web-noise-suppressor';

class AudioPassThroughProcessor extends AudioWorkletProcessor {
  private noiseSuppressor: NoiseSuppressor | null = null;
  private isInitialized: boolean = false;

  constructor() {
    super();
    this.port.onmessage = async (event) => {
      if (event.data.type === 'init') {
        try {
            // Initialize noise suppressor with options from the main thread
            // The wasmFilePath is crucial for loading the WASM module.
            this.noiseSuppressor = new NoiseSuppressor(
              event.data.wasmFilePath, // Path to the WASM file
              event.data.sampleRate,
              event.data.frameSize
            );
            await this.noiseSuppressor.init();
            this.isInitialized = true;
            this.port.postMessage({ type: 'initialized' }); // Notify main thread
        } catch (error) {
            console.error('Failed to initialize NoiseSuppressor:', error);
            // Fallback: isInitialized remains false, audio will pass through unprocessed.
            this.port.postMessage({ type: 'error', error: 'NoiseSuppressor init failed' });
        }
      }
    };
  }

  process(inputs: Float32Array[][], outputs: Float32Array[][], parameters: Record<string, Float32Array>): boolean {
    const input = inputs[0];
    const output = outputs[0];

    if (!input || input.length === 0 || !input[0] || input[0].length === 0) {
      // If no input, just pass through silence or do nothing
      for (let channel = 0; channel < output.length; ++channel) {
        if (output[channel]) {
          output[channel].fill(0); // Fill with silence
        }
      }
      return true;
    }

    let processedAudioFrame: Float32Array;

    if (this.isInitialized && this.noiseSuppressor) {
      // --- Noise Suppression Step ---
      processedAudioFrame = this.noiseSuppressor.process(input[0]);
    } else {
      // If not initialized, just pass through original audio
      processedAudioFrame = input[0];
    }

    // Copy processed audio to output (for continued sound if connected to destination)
    for (let channel = 0; channel < output.length; ++channel) {
      if (output[channel]) {
        output[channel].set(processedAudioFrame);
      }
    }

    // Process and send audio data to the main thread
    const pcmData = new Int16Array(processedAudioFrame.length);
    let maxAmp = 0;

    for (let i = 0; i < processedAudioFrame.length; i++) {
      const s = Math.max(-1, Math.min(1, processedAudioFrame[i]));
      if (Math.abs(s) > maxAmp) maxAmp = Math.abs(s); 
      pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    if (maxAmp >= 0.001) { // Apply silence filter as in original processAudio
        this.port.postMessage(pcmData.buffer, [pcmData.buffer]);
    }

    return true; // Keep the processor alive
  }
}

registerProcessor('audio-pass-through-processor', AudioPassThroughProcessor);
