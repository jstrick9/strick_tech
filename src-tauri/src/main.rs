// Agentic OS v6.0 — Tauri Desktop App Entry Point
// Spawns the Python FastAPI backend and opens Mission Control in a native window.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Command, Child};
use std::sync::Mutex;
use std::time::Duration;
use std::thread;

struct BackendProcess(Mutex<Option<Child>>);

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            // Spawn Python backend
            let app_dir = app.path().app_data_dir()
                .unwrap_or_else(|_| std::path::PathBuf::from("."));

            let python = if cfg!(windows) { "python" } else { "python3" };

            // Look for run.py relative to executable
            let exe_dir = std::env::current_exe()
                .ok()
                .and_then(|p| p.parent().map(|p| p.to_path_buf()))
                .unwrap_or_else(|| std::path::PathBuf::from("."));

            let run_py = exe_dir.join("run.py");
            let run_py_str = if run_py.exists() {
                run_py.to_string_lossy().to_string()
            } else {
                "run.py".to_string()
            };

            let child = Command::new(python)
                .arg(&run_py_str)
                .spawn();

            match child {
                Ok(c) => {
                    let state = app.state::<BackendProcess>();
                    *state.0.lock().unwrap() = Some(c);
                    // Give backend time to start
                    thread::sleep(Duration::from_millis(1500));
                    println!("[Agentic OS] Backend started → http://localhost:8787");
                }
                Err(e) => {
                    eprintln!("[Agentic OS] Failed to start backend: {}", e);
                    eprintln!("Make sure Python 3 is installed: https://python.org");
                }
            }

            Ok(())
        })
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // Backend will be killed when the process exits
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_version,
            open_data_dir,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Agentic OS");
}

#[tauri::command]
fn get_version() -> String {
    "6.0.0".to_string()
}

#[tauri::command]
fn open_data_dir() -> String {
    if cfg!(windows) {
        std::env::var("APPDATA").unwrap_or_else(|_| "C:\\Users\\Public".to_string())
    } else if cfg!(target_os = "macos") {
        format!("{}/Library/Application Support/com.agenticosvault.app",
            std::env::var("HOME").unwrap_or_else(|_| "~".to_string()))
    } else {
        format!("{}/.local/share/agentic-os",
            std::env::var("HOME").unwrap_or_else(|_| "~".to_string()))
    }
}
