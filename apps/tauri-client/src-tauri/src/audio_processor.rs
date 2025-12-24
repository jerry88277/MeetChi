use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Stream, StreamConfig, SampleRate};
use ringbuf::{HeapRb, traits::{Producer, Consumer, Split, Observer}};
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::{AppHandle, Emitter};
// Remove unused imports to keep it clean
// use anyhow::{Result, anyhow};
use std::sync::mpsc;
use std::error::Error;
use webrtc_vad::{Vad, SampleRate as VadSampleRate, VadMode};
use tokio::runtime::Runtime;
use futures_util::{StreamExt, SinkExt};
use tokio_tungstenite::{connect_async, tungstenite::protocol::Message};
use url::Url;

const TARGET_SAMPLE_RATE: u32 = 16000;
const VAD_WINDOW_SIZE_MS: u32 = 30;
const VAD_SAMPLE_SIZE: usize = (TARGET_SAMPLE_RATE / 1000 * VAD_WINDOW_SIZE_MS) as usize;

pub struct AudioProcessor {
    stream_active: Arc<Mutex<bool>>,
    _audio_thread: Option<thread::JoinHandle<Result<(), Box<dyn Error + Send + Sync>>>>,
    stop_tx: Option<mpsc::Sender<()>>,
    runtime: Option<Runtime>,
}

impl AudioProcessor {
    pub fn new(_app_handle: &AppHandle) -> Result<Self, Box<dyn Error + Send + Sync>> {
        Ok(AudioProcessor {
            stream_active: Arc::new(Mutex::new(false)),
            _audio_thread: None,
            stop_tx: None,
            runtime: None,
        })
    }

    pub fn start_audio_stream(
        &mut self,
        app_handle: AppHandle,
        device_id: String,
        vad_threshold: f32, 
    ) -> Result<(), String> {
        if *self.stream_active.lock().unwrap() {
            return Err("Audio stream already running".into());
        }
        *self.stream_active.lock().unwrap() = true;

        // --- WebSocket Setup ---
        let rt = Runtime::new().map_err(|e: std::io::Error| e.to_string())?;
        
        let url = Url::parse("ws://127.0.0.1:8000/ws/transcribe").map_err(|e| e.to_string())?;
        
        // Connect synchronously here to fail early
        let (ws_stream, _) = rt.block_on(connect_async(url.to_string()))
            .map_err(|e| format!("Failed to connect to backend: {}", e))?;
            
        log::info!("WebSocket connected");

        let (mut write, mut read) = ws_stream.split();
        let (audio_tx, mut audio_rx) = tokio::sync::mpsc::unbounded_channel::<Vec<u8>>();

        // Writer Task
        rt.spawn(async move {
            while let Some(data) = audio_rx.recv().await {
                if let Err(e) = write.send(Message::Binary(data)).await {
                    log::error!("WS send error: {}", e);
                    break;
                }
            }
        });

        // Reader Task
        let app_handle_clone_ws = app_handle.clone();
        rt.spawn(async move {
            while let Some(msg) = read.next().await {
                match msg {
                    Ok(Message::Text(text)) => {
                        log::debug!("Received transcript: {}", text);
                        let _ = app_handle_clone_ws.emit("transcript-update", text);
                    }
                    Ok(Message::Close(_)) => {
                        log::info!("WS Closed");
                        break;
                    }
                    Err(e) => {
                        log::error!("WS Read Error: {}", e);
                        break;
                    }
                    _ => {}
                }
            }
        });
        
        self.runtime = Some(rt);
        // -----------------------

        let host = cpal::default_host();
        let device = if device_id == "loopback" {
            host.default_output_device().ok_or_else(|| "Default output device not found".to_string())?
        } else if device_id == "default" {
            host.default_input_device().ok_or_else(|| "Default input device not found".to_string())?
        } else {
            host.input_devices()
                .map_err(|e: cpal::DevicesError| e.to_string())?
                .find(|d| d.name().ok() == Some(device_id.clone()))
                .ok_or_else(|| format!("Input device '{}' not found", device_id))?
        };

        log::info!("Starting audio stream on device: {}", device.name().unwrap_or_default());

        let supported_config = if device_id == "loopback" {
             device.default_output_config()
        } else {
             device.default_input_config()
        }.map_err(|e| e.to_string())?;
        
        let sample_rate = supported_config.sample_rate().0;
        let channels = supported_config.channels();
        let config: StreamConfig = supported_config.into();
        
        log::info!("Audio config: Rate={}, Channels={}", sample_rate, channels);

        let rb = HeapRb::<f32>::new(VAD_SAMPLE_SIZE * 20); 
        let (mut producer, mut consumer) = rb.split();

        let stream_active_clone = self.stream_active.clone();
        let app_handle_clone = app_handle.clone();
        let (stop_tx_inner, stop_rx_inner) = mpsc::channel();

        // Convert float threshold to VAD mode, passed into thread by value
        let vad_mode = if vad_threshold < 0.01 { VadMode::Quality } 
                  else if vad_threshold < 0.03 { VadMode::LowBitrate } 
                  else if vad_threshold < 0.05 { VadMode::Aggressive } 
                  else { VadMode::VeryAggressive };
        

        let audio_thread = thread::spawn(move || {
            // --- VAD Initialization INSIDE THREAD ---
            let mut vad = Vad::new_with_rate(VadSampleRate::Rate16kHz);
            vad.set_mode(vad_mode);
            // ----------------------------------------

            let stream = device
                .build_input_stream(
                    &config,
                    move |data: &[f32], _: &cpal::InputCallbackInfo| {
                        let ratio = sample_rate as f32 / TARGET_SAMPLE_RATE as f32;
                        let stride = channels as f32 * ratio;
                        
                        let mut index = 0.0;
                        while (index as usize) < data.len() {
                            let i = index as usize;
                            let mut sum = 0.0;
                            let mut count = 0;
                            for c in 0..channels {
                                if i + (c as usize) < data.len() {
                                    sum += data[i + (c as usize)];
                                    count += 1;
                                }
                            }
                            if count > 0 {
                                let sample = sum / count as f32;
                                let _ = producer.try_push(sample);
                            }
                            index += stride;
                        }
                    },
                    move |err: cpal::StreamError| eprintln!("Stream error: {}", err),
                    None,
                )
                .map_err(|e| e.to_string())?;

            stream.play().map_err(|e| e.to_string())?;

            let mut sample_buffer = vec![0.0; VAD_SAMPLE_SIZE];
            let mut i16_buffer = vec![0i16; VAD_SAMPLE_SIZE];

            while *stream_active_clone.lock().unwrap() && stop_rx_inner.try_recv().is_err() {
                if consumer.occupied_len() >= VAD_SAMPLE_SIZE {
                    let _ = consumer.pop_slice(&mut sample_buffer);
                    
                    for (i, &sample) in sample_buffer.iter().enumerate() {
                        i16_buffer[i] = (sample * 32767.0).max(-32768.0).min(32767.0) as i16;
                    }

                    let is_speech = vad.is_voice_segment(&i16_buffer).unwrap_or(false);

                    if is_speech {
                         let _ = app_handle_clone.emit("speech-detected", true);
                         
                         let mut bytes = Vec::with_capacity(VAD_SAMPLE_SIZE * 2);
                         for sample in &i16_buffer {
                             bytes.extend_from_slice(&sample.to_le_bytes());
                         }
                         let _ = audio_tx.send(bytes); 

                    } else {
                         let _ = app_handle_clone.emit("speech-detected", false);
                    }
                } else {
                     thread::sleep(std::time::Duration::from_millis(5));
                }
            }
            Ok(())
        });
        
        self._audio_thread = Some(audio_thread);
        self.stop_tx = Some(stop_tx_inner);
        Ok(())
    }

    pub fn stop_audio_stream(&mut self) -> Result<(), String> {
        if !*self.stream_active.lock().unwrap() {
            return Err("Audio stream not running".into());
        }
        *self.stream_active.lock().unwrap() = false;

        if let Some(stop_tx) = self.stop_tx.take() {
            let _ = stop_tx.send(());
        }

        if let Some(handle) = self._audio_thread.take() {
            let _ = handle.join();
        }
        
        if let Some(rt) = self.runtime.take() {
            rt.shutdown_background();
        }

        log::info!("Audio stream stopped.");
        Ok(())
    }
}