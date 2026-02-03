use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Stream, StreamConfig, SampleRate};
use ringbuf::{HeapRb, traits::{Producer, Consumer, Split, Observer}};
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::{AppHandle, Emitter};
use std::sync::mpsc;
use std::error::Error;
use webrtc_vad::{Vad, SampleRate as VadSampleRate, VadMode};
use tokio::runtime::Runtime;
use futures_util::{StreamExt, SinkExt};
use tokio_tungstenite::{connect_async, tungstenite::protocol::Message};
use url::Url;
use std::sync::atomic::{AtomicBool, Ordering};

const TARGET_SAMPLE_RATE: u32 = 16000;
const VAD_WINDOW_SIZE_MS: u32 = 30;
const VAD_SAMPLE_SIZE: usize = (TARGET_SAMPLE_RATE / 1000 * VAD_WINDOW_SIZE_MS) as usize;

// Reconnection settings
const MAX_RECONNECT_ATTEMPTS: u32 = 10;
const RECONNECT_DELAY_MS: u64 = 2000;

pub struct AudioProcessor {
    stream_active: Arc<Mutex<bool>>,
    ws_connected: Arc<AtomicBool>,
    _audio_thread: Option<thread::JoinHandle<Result<(), Box<dyn Error + Send + Sync>>>>,
    stop_tx: Option<mpsc::Sender<()>>,
    runtime: Option<Runtime>,
}

impl AudioProcessor {
    pub fn new(_app_handle: &AppHandle) -> Result<Self, Box<dyn Error + Send + Sync>> {
        Ok(AudioProcessor {
            stream_active: Arc::new(Mutex::new(false)),
            ws_connected: Arc::new(AtomicBool::new(false)),
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
        meeting_id: String,
        overlap_duration: f32,
        mode: String,
        initial_prompt: String,
    ) -> Result<(), String> {
        if *self.stream_active.lock().unwrap() {
            return Err("Audio stream already running".into());
        }
        *self.stream_active.lock().unwrap() = true;

        // --- WebSocket Setup with Reconnection ---
        let rt = Runtime::new().map_err(|e: std::io::Error| e.to_string())?;
        
        let url_str = "ws://127.0.0.1:8000/ws/transcribe";
        
        // Initial connection attempt
        let (ws_stream, _) = rt.block_on(connect_async(url_str))
            .map_err(|e| format!("Failed to connect to backend: {}", e))?;
            
        let (write, read) = ws_stream.split();
        let write = Arc::new(tokio::sync::Mutex::new(write));
        let ws_connected = self.ws_connected.clone();
        ws_connected.store(true, Ordering::SeqCst);
            
        log::info!("WebSocket connected");

        // --- Send Config Message ---
        let config_msg = serde_json::json!({
            "type": "config",
            "meeting_id": meeting_id,
            "source_lang": "zh",
            "target_lang": "en",
            "overlap_duration": overlap_duration,
            "mode": mode,
            "initial_prompt": initial_prompt
        });
        let config_msg_str = config_msg.to_string();
        
        {
            let write_lock = rt.block_on(write.lock());
            let mut write_guard = write_lock;
            rt.block_on(async {
                write_guard.send(Message::Text(config_msg_str.clone())).await
            }).map_err(|e| format!("Failed to send config to WS: {}", e))?;
        }
        log::info!("Sent config to WebSocket with meeting_id: {}, mode: {}", meeting_id, mode);

        let (audio_tx, audio_rx) = tokio::sync::mpsc::unbounded_channel::<Vec<u8>>();
        let audio_rx = Arc::new(tokio::sync::Mutex::new(audio_rx));

        // Store config for reconnection
        let config_for_reconnect = config_msg.to_string();
        let url_for_reconnect = url_str.to_string();

        // Writer Task with reconnection support
        let write_clone = write.clone();
        let audio_rx_clone = audio_rx.clone();
        let ws_connected_writer = ws_connected.clone();
        let stream_active_writer = self.stream_active.clone();
        let app_handle_writer = app_handle.clone();
        let config_for_writer = config_for_reconnect.clone();
        let url_for_writer = url_for_reconnect.clone();
        
        rt.spawn(async move {
            let mut reconnect_attempts = 0;
            let mut current_write = write_clone;
            
            loop {
                // Check if still active
                if !*stream_active_writer.lock().unwrap() {
                    break;
                }

                let mut rx_guard = audio_rx_clone.lock().await;
                
                tokio::select! {
                    Some(data) = rx_guard.recv() => {
                        drop(rx_guard); // Release lock before send
                        let mut write_guard = current_write.lock().await;
                        if let Err(e) = write_guard.send(Message::Binary(data)).await {
                            log::error!("WS send error: {}. Attempting reconnect...", e);
                            ws_connected_writer.store(false, Ordering::SeqCst);
                            let _ = app_handle_writer.emit("backend-reconnecting", format!("Reconnecting... (attempt {}/{})", reconnect_attempts + 1, MAX_RECONNECT_ATTEMPTS));
                            
                            // Try to reconnect
                            drop(write_guard);
                            
                            while reconnect_attempts < MAX_RECONNECT_ATTEMPTS {
                                reconnect_attempts += 1;
                                log::info!("Reconnect attempt {}/{}", reconnect_attempts, MAX_RECONNECT_ATTEMPTS);
                                
                                tokio::time::sleep(tokio::time::Duration::from_millis(RECONNECT_DELAY_MS)).await;
                                
                                match connect_async(&url_for_writer).await {
                                    Ok((new_ws_stream, _)) => {
                                        let (new_write, _new_read) = new_ws_stream.split();
                                        let new_write_arc = Arc::new(tokio::sync::Mutex::new(new_write));
                                        
                                        // Send config again
                                        let mut new_write_guard = new_write_arc.lock().await;
                                        if let Err(e) = new_write_guard.send(Message::Text(config_for_writer.clone())).await {
                                            log::error!("Failed to send config after reconnect: {}", e);
                                            continue;
                                        }
                                        drop(new_write_guard);
                                        
                                        current_write = new_write_arc;
                                        ws_connected_writer.store(true, Ordering::SeqCst);
                                        reconnect_attempts = 0;
                                        log::info!("WebSocket reconnected successfully");
                                        let _ = app_handle_writer.emit("backend-reconnected", "Connection restored");
                                        break;
                                    }
                                    Err(e) => {
                                        log::error!("Reconnect failed: {}", e);
                                        let _ = app_handle_writer.emit("backend-reconnecting", format!("Reconnecting... (attempt {}/{})", reconnect_attempts + 1, MAX_RECONNECT_ATTEMPTS));
                                    }
                                }
                            }
                            
                            if reconnect_attempts >= MAX_RECONNECT_ATTEMPTS {
                                log::error!("Max reconnect attempts reached. Giving up.");
                                let _ = app_handle_writer.emit("backend-disconnected", "Failed to reconnect after multiple attempts");
                                break;
                            }
                        }
                    }
                    else => {
                        // Channel closed
                        break;
                    }
                }
            }
        });

        // Reader Task
        let app_handle_clone_ws = app_handle.clone();
        let ws_connected_reader = ws_connected.clone();
        rt.spawn(async move {
            let mut read = read;
            while let Some(msg) = read.next().await {
                match msg {
                    Ok(Message::Text(text)) => {
                        log::debug!("Received transcript: {}", text);
                        let _ = app_handle_clone_ws.emit("transcript-update", text);
                    }
                    Ok(Message::Close(_)) => {
                        log::info!("WS Closed by server");
                        ws_connected_reader.store(false, Ordering::SeqCst);
                        // Don't send disconnect event here - writer will handle reconnection
                        break;
                    }
                    Err(e) => {
                        log::error!("WS Read Error: {}", e);
                        ws_connected_reader.store(false, Ordering::SeqCst);
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