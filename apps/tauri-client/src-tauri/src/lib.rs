use tauri::{Manager, Emitter, State};
use cpal::traits::{HostTrait, DeviceTrait};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use std::sync::{Arc, Mutex};
mod audio_processor;
use audio_processor::AudioProcessor;

#[derive(serde::Serialize)]
struct AudioDevice {
    id: String,
    name: String,
}

#[tauri::command]
fn get_audio_devices() -> Result<Vec<AudioDevice>, String> {
    let host = cpal::default_host();
    let devices = host.input_devices().map_err(|e| e.to_string())?;
    
    let mut device_list = Vec::new();
    for device in devices {
        if let Ok(name) = device.name() {
             device_list.push(AudioDevice {
                 id: name.clone(),
                 name,
             });
        }
    }
    // Add Loopback Option
    device_list.push(AudioDevice {
        id: "loopback".to_string(),
        name: "System Audio (Loopback)".to_string(),
    });
    
    Ok(device_list)
}

#[tauri::command]
fn set_ignore_cursor_events(window: tauri::Window, ignore: bool) -> Result<(), String> {
    window.set_ignore_cursor_events(ignore).map_err(|e| e.to_string())
}

#[tauri::command]
fn start_audio_command(
    app_handle: tauri::AppHandle,
    processor_state: State<'_, Arc<Mutex<AudioProcessor>>>,
    device_id: String,
    vad_threshold: f32,
) -> Result<(), String> {
    (*processor_state).lock().unwrap().start_audio_stream(
        app_handle,
        device_id,
        vad_threshold,
    )
}

#[tauri::command]
fn stop_audio_command(
    processor_state: State<'_, Arc<Mutex<AudioProcessor>>>,
) -> Result<(), String> {
    (*processor_state).lock().unwrap().stop_audio_stream()
}


#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![set_ignore_cursor_events, get_audio_devices, start_audio_command, stop_audio_command])
    .setup(|app| {
      app.handle().plugin(tauri_plugin_fs::init())?;
      app.handle().plugin(tauri_plugin_shell::init())?;
      app.handle().plugin(tauri_plugin_process::init())?;
      
      let processor = AudioProcessor::new(&app.handle())
        .map_err(|e| format!("Failed to create AudioProcessor: {}", e))?;
      app.manage(Arc::new(Mutex::new(processor)));

      #[cfg(desktop)]
      {
          app.handle().plugin(
              tauri_plugin_global_shortcut::Builder::new()
                  .with_shortcut("CommandOrControl+Shift+L")?
                  .with_handler(|app, shortcut, event| {
                      if event.state == ShortcutState::Pressed {
                          if let Some(window) = app.get_webview_window("main") {
                              let _ = window.set_ignore_cursor_events(false);
                              let _ = window.emit("lock-state-changed", false);
                          }
                      }
                  })
                  .build(),
          )?;
      }

      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}