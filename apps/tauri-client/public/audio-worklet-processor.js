// public/audio-worklet-processor.js
// This file runs in a separate AudioWorklet thread.
// It must be pure JavaScript and cannot use ES module imports directly without a bundler.

class AudioPassThroughProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.isRecording = true; // Default to true or control via message
    
    this.port.onmessage = (event) => {
      if (event.data.type === 'init') {
        // Initialization logic (placeholder for future noise suppression)
        console.log("AudioWorklet: Initialized");
        this.port.postMessage({ type: 'initialized' });
      }
    };
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    const output = outputs[0];

    if (!input || input.length === 0 || !input[0] || input[0].length === 0) {
      return true;
    }

    const inputChannel0 = input[0];
    
    // Copy input to output (Pass-through to hear audio)
    for (let channel = 0; channel < output.length; ++channel) {
       if (output[channel] && input[channel]) {
         output[channel].set(input[channel]);
       }
    }

    // Process audio for visualization/transmission (Mono)
    // Convert Float32 [-1, 1] to Int16
    const pcmData = new Int16Array(inputChannel0.length);
    let maxAmp = 0;

    for (let i = 0; i < inputChannel0.length; i++) {
      const s = Math.max(-1, Math.min(1, inputChannel0[i]));
      if (Math.abs(s) > maxAmp) maxAmp = Math.abs(s); 
      pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // Simple silence gate to reduce bandwidth
    if (maxAmp >= 0.001) { 
        // Send PCM data to main thread
        // We must transfer the buffer to avoid copying overhead if possible, 
        // but postMessage copy is fine for small chunks.
        this.port.postMessage(pcmData.buffer, [pcmData.buffer]);
    }

    return true; // Keep processor alive
  }
}

registerProcessor('audio-pass-through-processor', AudioPassThroughProcessor);
