// Agentic OS v6.0 — Tauri Desktop App Entry Point
// Spawns the Python FastAPI backend and opens Mission Control in a native window.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Command, Child};
use std::sync::Mutex;
use std::time::Duration;
use std::thread;
use std::path::PathBuf;
use tauri::Manager;

struct BackendProcess(Mutex<Option<Child>>);

fn find_run_py() -> String {
    // Try multiple locations for run.py
    let candidates = vec![
        PathBuf::from("run.py"),
        PathBuf::from("../run.py"),
        PathBuf::from("../../run.py"),
    ];

    // Also try relative to executable
    if let Ok(exe_dir) = std::env::current_exe() {
        if let Some(parent) = exe_dir.parent() {
            let candidates_from_exe = vec![
                parent.join("run.py"),
                parent.join("../run.py"),
                parent.join("../../run.py"),
                parent.join("Resources/run.py"),       // macOS bundle
                parent.join("../Resources/run.py"),     // macOS bundle alt
            ];
            for c in candidates_from_exe {
                if c.exists() {
                    return c.to_string_lossy().to_string();
                }
            }
        }
    }

    for c in &candidates {
        if c.exists() {
            return c.to_string_lossy().to_string();
        }
    }

    // Default fallback
    "run.py".to_string()
}

fn find_python_binary() -> String {
    // 1. Check for bundled standalone embedded Python runtime inside Resources/python_embedded/bin/python3
    if let Ok(exe_dir) = std::env::current_exe() {
        if let Some(parent) = exe_dir.parent() {
            let embedded_candidates = vec![
                parent.join("Resources/python_embedded/bin/python3"),     // macOS bundle standalone
                parent.join("../Resources/python_embedded/bin/python3"),  // macOS alt
                parent.join("python_embedded/bin/python3"),               // linux/unix bundle
                parent.join("python_embedded/python.exe"),                // windows standalone
                parent.join("Resources/python_embedded/python.exe"),
            ];
            for c in embedded_candidates {
                if c.exists() {
                    println!("[Agentic OS] Found embedded standalone Python runtime: {:?}", c);
                    return c.to_string_lossy().to_string();
                }
            }
        }
    }

    // 2. Check local relative directory
    let local_candidates = vec![
        PathBuf::from("python_embedded/bin/python3"),
        PathBuf::from("python_embedded/python.exe"),
    ];
    for c in local_candidates {
        if c.exists() {
            println!("[Agentic OS] Found local embedded Python runtime: {:?}", c);
            return c.to_string_lossy().to_string();
        }
    }

    // 3. Fallback to system Python
    if cfg!(windows) { "python".to_string() } else { "python3".to_string() }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            let run_py = find_run_py();
            let python = find_python_binary();

            let run_dir = std::path::Path::new(&run_py)
                .parent()
                .map(|p| p.to_path_buf())
                .unwrap_or_else(|| {
                    std::env::current_exe()
                        .ok()
                        .and_then(|p| p.parent().map(|p| p.to_path_buf()))
                        .unwrap_or_else(|| PathBuf::from("."))
                });

            println!("[Agentic OS] Starting backend: {} {} (cwd: {:?})", python, run_py, run_dir);

            let data_dir = if cfg!(target_os = "macos") {
                let home = std::env::var("HOME").unwrap_or_else(|_| "~".to_string());
                PathBuf::from(format!("{}/Library/Application Support/com.stricktech.agenticos", home))
            } else if cfg!(windows) {
                let appdata = std::env::var("APPDATA").unwrap_or_else(|_| "C:\\Users\\Public".to_string());
                PathBuf::from(format!("{}\\agentic-os", appdata))
            } else {
                let home = std::env::var("HOME").unwrap_or_else(|_| "~".to_string());
                PathBuf::from(format!("{}/.local/share/agentic-os", home))
            };
            let _ = std::fs::create_dir_all(&data_dir);
            std::env::set_var("AGENTIC_OS_DATA_DIR", &data_dir);

            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if let Ok(meta) = std::fs::metadata(&python) {
                    let mut perms = meta.permissions();
                    if perms.mode() & 0o111 == 0 {
                        perms.set_mode(0o755);
                        let _ = std::fs::set_permissions(&python, perms);
                    }
                }
            }

            let log_path = data_dir.join("backend.log");
            let stdout_file = std::fs::File::create(&log_path).expect("failed to create log file");
            let stderr_file = stdout_file.try_clone().expect("failed to clone log file");

            let child = Command::new(&python)
                .arg(&run_py)
                .current_dir(&run_dir)
                .env("AGENTIC_OS_DATA_DIR", &data_dir)
                .stdout(std::process::Stdio::from(stdout_file))
                .stderr(std::process::Stdio::from(stderr_file))
                .spawn();

            match child {
                Ok(c) => {
                    if let Ok(mut guard) = app.state::<BackendProcess>().inner().0.lock() {
                        *guard = Some(c);
                    }
                    let app_handle = app.handle().clone();
                    std::thread::spawn(move || {
                        println!("[Agentic OS] Background monitor: waiting for TCP port 8787...");
                        let mut online = false;
                        for _ in 0..300 {
                            if std::net::TcpStream::connect("127.0.0.1:8787").is_ok() {
                                online = true;
                                break;
                            }
                            thread::sleep(Duration::from_millis(100));
                        }
                        if online {
                            println!("[Agentic OS] Backend confirmed online! Navigating windows...");
                            for (label, win) in app_handle.webview_windows() {
                                println!("[Agentic OS] Navigating window '{}' to http://localhost:8787", label);
                                let _ = win.eval("window.location.href = 'http://localhost:8787';");
                            }
                        } else {
                            eprintln!("[Agentic OS] Error: Backend did not respond on port 8787 within 30 seconds. Check {:?}", log_path);
                        }
                    });
                }
                Err(e) => {
                    eprintln!("[Agentic OS] Failed to start backend: {}", e);
                    eprintln!("Make sure Python 3.10+ is installed: https://python.org");
                    eprintln!("And run: pip install -r requirements.txt");
                }
            }

            Ok(())
        })
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                use tauri::Manager;
                if let Ok(mut guard) = _window.state::<BackendProcess>().inner().0.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_version,
            open_data_dir,
            get_backend_url,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Agentic OS");
}

#[tauri::command]
fn get_version() -> String {
    "10.0.0".to_string()
}

#[tauri::command]
fn get_backend_url() -> String {
    let port = std::env::var("AGENTIC_OS_PORT").unwrap_or_else(|_| "8787".to_string());
    format!("http://localhost:{}", port)
}

#[tauri::command]
fn open_data_dir() -> String {
    if cfg!(windows) {
        std::env::var("APPDATA").unwrap_or_else(|_| "C:\\Users\\Public".to_string())
    } else if cfg!(target_os = "macos") {
        format!("{}/Library/Application Support/com.stricktech.agenticos",
            std::env::var("HOME").unwrap_or_else(|_| "~".to_string()))
    } else {
        format!("{}/.local/share/agentic-os",
            std::env::var("HOME").unwrap_or_else(|_| "~".to_string()))
    }
}
