#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{AppHandle, Emitter, Manager, State, path::BaseDirectory};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::Child;
use tokio::sync::Mutex;
use tokio::sync::mpsc::Sender;

// ── 共享状态 ──
struct ApprovalState {
    child: Mutex<Option<Child>>,
    cancel_tx: Mutex<Option<Sender<String>>>,
}

/// 在工作目录及可执行文件周边探测 runner 路径
/// Prod 模式优先使用 resolve_resource 定位打包后的 ApprovalRunner.exe
fn find_runner_py(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    // 1. Prod 模式：尝试 resolve_resource 定位打包的 exe
    if let Ok(path) = app.path().resolve(
        "python/dist/ApprovalRunner/ApprovalRunner.exe",
        BaseDirectory::Resource,
    ) {
        if path.exists() {
            return Ok(path);
        }
    }

    // 2. 绿色版：exe 同级目录下的 python/dist/ApprovalRunner/ApprovalRunner.exe
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let green = exe_dir.join("python/dist/ApprovalRunner/ApprovalRunner.exe");
            if green.exists() {
                return Ok(green);
            }
        }
    }

    // 3. Dev 模式回退：原有候选路径探测
    let candidates = [
        std::path::PathBuf::from("python/runner.py"),
        std::path::PathBuf::from("src-tauri/python/runner.py"),
    ];
    for p in &candidates {
        if p.exists() {
            return Ok(p.clone());
        }
    }
    // 从 exe 路径回退查找
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let more = [
                exe_dir.join("../python/runner.py"),
                exe_dir.join("../../python/runner.py"),
                exe_dir.join("../../../python/runner.py"),
            ];
            for p in &more {
                if p.exists() {
                    return Ok(p.clone());
                }
            }
        }
    }
    Err("找不到 runner，请确认 Python 脚本或打包资源已正确放置".into())
}

/// 探测 config.json 路径：优先使用传入路径，再回退到 runner.py 同级目录
fn find_config_json(app: &AppHandle, preferred: &str) -> Result<std::path::PathBuf, String> {
    // 1. Prod 模式：尝试打包资源中 exe 同级目录的 config.json
    if let Ok(exe) = app.path().resolve(
        "python/dist/ApprovalRunner/ApprovalRunner.exe",
        BaseDirectory::Resource,
    ) {
        if let Some(dir) = exe.parent() {
            let cfg = dir.join("config.json");
            if cfg.exists() {
                return Ok(cfg);
            }
        }
    }

    // 2. 绿色版：exe 同级目录下的 python/dist/ApprovalRunner/config.json
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let green = exe_dir.join("python/dist/ApprovalRunner/config.json");
            if green.exists() {
                return Ok(green);
            }
        }
    }

    // 3. Dev 模式回退：原有候选路径探测
    let candidates = [
        std::path::PathBuf::from(preferred),
        std::path::PathBuf::from("python/config.json"),
        std::path::PathBuf::from("src-tauri/python/config.json"),
    ];
    for p in &candidates {
        if p.exists() {
            return Ok(p.clone());
        }
    }
    // 若 runner 存在，取其同级目录
    if let Ok(runner) = find_runner_py(app) {
        if let Some(dir) = runner.parent() {
            let fallback = dir.join("config.json");
            if fallback.exists() {
                return Ok(fallback);
            }
        }
    }
    Err(format!(
        "找不到 config.json（已尝试: {}）",
        preferred
    ))
}

// ── 验证 Chrome CDP 连接 ──
#[tauri::command]
async fn connect_chrome(cdp_endpoint: String) -> Result<String, String> {
    let url = cdp_endpoint.trim_end_matches('/');
    let host_port = url
        .strip_prefix("http://")
        .or_else(|| url.strip_prefix("https://"))
        .unwrap_or(url);

    let mut stream = tokio::net::TcpStream::connect(host_port)
        .await
        .map_err(|e| format!("无法连接 Chrome CDP 端口: {}", e))?;

    let request = format!(
        "GET /json/list HTTP/1.1\r\nHost: {}\r\nConnection: close\r\n\r\n",
        host_port
    );
    stream
        .write_all(request.as_bytes())
        .await
        .map_err(|e| format!("发送请求失败: {}", e))?;

    let mut buf = [0u8; 1024];
    let n = stream
        .read(&mut buf)
        .await
        .map_err(|e| format!("读取响应失败: {}", e))?;

    if n == 0 {
        return Err("Chrome 未返回任何数据".into());
    }

    let response = String::from_utf8_lossy(&buf[..n]);
    if response.contains("200 OK") {
        Ok("connected".into())
    } else {
        Err(format!(
            "Chrome 返回异常: {}",
            response.lines().next().unwrap_or("unknown")
        ))
    }
}

// ── 启动审批流程 ──
#[tauri::command]
async fn start_approval(
    app: AppHandle,
    cdp_endpoint: String,
    config_path: String,
    qty: String,
    biz_type: String,
    oa_type: String,
    test_mode: bool,
    state: State<'_, ApprovalState>,
) -> Result<(), String> {
    // 若上次进程已结束，自动清理；若仍在运行则拒绝重复启动
    {
        let mut guard = state.child.lock().await;
        if let Some(ref mut child) = *guard {
            match child.try_wait() {
                Ok(None) => return Err("已有正在运行的审批流程".into()),
                _ => {
                    *guard = None;
                }
            }
        }
    }

    let runner_path = find_runner_py(&app)?;
    let config_path = find_config_json(&app, &config_path)?;

    let is_exe = runner_path
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| ext.eq_ignore_ascii_case("exe"))
        .unwrap_or(false);

    let mut cmd = if is_exe {
        tokio::process::Command::new(&runner_path)
    } else {
        let mut c = tokio::process::Command::new("python");
        c.arg(&runner_path);
        c
    };
    cmd.arg("--cdp")
        .arg(&cdp_endpoint)
        .arg("--config")
        .arg(&config_path)
        .arg("--qty")
        .arg(&qty)
        .arg("--oa-type")
        .arg(&oa_type);

    if !biz_type.is_empty() {
        cmd.arg("--biz-type").arg(&biz_type);
    }
    if test_mode {
        cmd.arg("--test-mode");
    }

    cmd.env("PYTHONUNBUFFERED", "1")
        .stdout(std::process::Stdio::piped())
        .stdin(std::process::Stdio::piped())
        .stderr(std::process::Stdio::inherit());

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("启动 Python 失败: {}", e))?;

    let stdout = child.stdout.take().ok_or("无法获取 Python stdout")?;
    let stdin = child.stdin.take().ok_or("无法获取 Python stdin")?;

    let (cancel_tx, mut cancel_rx) = tokio::sync::mpsc::channel::<String>(1);

    {
        let mut tx_guard = state.cancel_tx.lock().await;
        *tx_guard = Some(cancel_tx);
    }
    {
        let mut child_guard = state.child.lock().await;
        *child_guard = Some(child);
    }

    // stdout 读取 + 事件转发
    let app_stdout = app.clone();
    tokio::spawn(async move {
        let reader = BufReader::new(stdout);
        let mut lines = reader.lines();

        while let Ok(Some(line)) = lines.next_line().await {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(&line) {
                if let Some(event_type) = value.get("event").and_then(|v| v.as_str()) {
                    let event_name = format!("approval:{}", event_type);
                    let _ = app_stdout.emit(&event_name, value);
                }
            }
        }

        let _ = app_stdout.emit("approval:finished", serde_json::json!({}));
    });

    // stdin 取消通道
    tokio::spawn(async move {
        if let Some(msg) = cancel_rx.recv().await {
            let mut stdin = stdin;
            let _ = stdin.write_all(msg.as_bytes()).await;
            let _ = stdin.flush().await;
        }
    });

    Ok(())
}

// ── 读取配置 ──
#[tauri::command]
async fn get_config(
    app: AppHandle,
    config_path: String,
) -> Result<serde_json::Value, String> {
    let path = find_config_json(&app, &config_path)?;
    let content = tokio::fs::read_to_string(&path)
        .await
        .map_err(|e| format!("读取 config.json 失败 ({}): {}", path.display(), e))?;
    let config: serde_json::Value = serde_json::from_str(&content)
        .map_err(|e| format!("解析 config.json 失败: {}", e))?;
    Ok(config)
}

// ── 取消审批流程 ──
#[tauri::command]
async fn cancel_approval(state: State<'_, ApprovalState>) -> Result<(), String> {
    let tx = {
        let mut tx_guard = state.cancel_tx.lock().await;
        tx_guard.take()
    };
    if let Some(tx) = tx {
        let _ = tx.send("cancel\n".to_string()).await;
    }

    let child = {
        let mut child_guard = state.child.lock().await;
        child_guard.take()
    };
    if let Some(mut child) = child {
        let _ = child.kill().await;
    }

    Ok(())
}

fn main() {
    tauri::Builder::default()
        .manage(ApprovalState {
            child: Mutex::new(None),
            cancel_tx: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            connect_chrome,
            start_approval,
            cancel_approval,
            get_config,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
