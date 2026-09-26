#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{AppHandle, Emitter, Manager, State, path::BaseDirectory};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
mod chrome;
mod settings;
mod updater;
mod logs;
use tokio::process::Child;
use tokio::sync::Mutex;
use tokio::sync::mpsc::Sender;

// ── 共享状态 ──
struct ApprovalState {
    child: Mutex<Option<Child>>,
    cancel_tx: Mutex<Option<Sender<String>>>,
    browser_launch: Mutex<()>,
}

/// 在工作目录及可执行文件周边探测 runner 路径
/// Prod 模式优先使用 resolve_resource 定位打包后的 ApprovalRunner.exe
fn find_runner_py(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    #[cfg(debug_assertions)]
    for candidate in ["python/runner.py", "src-tauri/python/runner.py"] {
        let path = std::path::PathBuf::from(candidate);
        if path.exists() {
            return Ok(path);
        }
    }
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
    let directory = settings::directory(app)?;
    let legacy = if directory.exists() { directory.join("config.json") } else { find_legacy_config(app, preferred)? };
    settings::initialize(&directory, &legacy)
}

fn find_legacy_config(app: &AppHandle, preferred: &str) -> Result<std::path::PathBuf, String> {
    #[cfg(debug_assertions)]
    for candidate in [preferred, "python/config.json", "src-tauri/python/config.json"] {
        let path = std::path::PathBuf::from(candidate);
        if path.exists() {
            return Ok(path);
        }
    }
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

#[tauri::command]
async fn detect_chrome(mode: String, port: u16, profile: String) -> Result<chrome::Detection, String> {
    if mode == "smart" {
        // Prefer the established debugging port; only try discovery when absent.
        if let Some(endpoint) = chrome::probe(port).await? {
            return Ok(chrome::Detection { endpoint, message: format!("已发现 Chrome（端口 {port}）") });
        }
        return chrome::detect("auto", port, &profile).await.map_err(|_| format!("未找到可用 Chrome。已检查 localhost:{port} 和新版调试入口；请先用原快捷方式打开 Chrome，或启动专用浏览器"));
    }
    chrome::detect(&mode, port, &profile).await
}

#[tauri::command]
fn get_browser_settings(app: AppHandle, legacy: Option<settings::BrowserSettings>) -> Result<settings::BrowserSettings, String> {
    find_config_json(&app, "src-tauri/python/config.json")?;
    settings::browser(&settings::directory(&app)?, legacy)
}

#[tauri::command]
async fn save_browser_settings(app: AppHandle, settings: settings::BrowserSettings, state: State<'_, ApprovalState>) -> Result<(), String> {
    let mut guard = state.child.lock().await;
    if let Some(child) = guard.as_mut() {
        if child.try_wait().map_err(|e| e.to_string())?.is_none() { return Err("审批运行期间不能修改设置".into()); }
    }
    settings::save_browser(&settings::directory(&app)?, &settings)
}

#[tauri::command]
fn get_app_info(app: AppHandle) -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({ "version": app.package_info().version.to_string(), "settings_directory": settings::directory(&app)?.display().to_string() }))
}

#[tauri::command]
async fn connect_chrome(cdp_endpoint: String) -> Result<(), String> {
    chrome::connect(&cdp_endpoint).await
}

#[tauri::command]
async fn launch_chrome(app: AppHandle, port: u16, executable: String, state: State<'_, ApprovalState>) -> Result<String, String> {
    let _guard = state.browser_launch.lock().await;
    let name = if port == 9222 { "ChromeProfile".to_string() } else { format!("ChromeProfile-{port}") };
    let profile = app.path().app_local_data_dir().map_err(|e| e.to_string())?.join(name);
    chrome::launch(profile, port, &executable).await
}

// ── 启动审批流程 ──
#[tauri::command]
fn get_workflow_settings(app: AppHandle) -> Result<settings::WorkflowSettings, String> {
    find_config_json(&app, "src-tauri/python/config.json")?;
    settings::workflow(&settings::directory(&app)?)
}

#[tauri::command]
async fn save_workflow_settings(app: AppHandle, settings: settings::WorkflowSettings, state: State<'_, ApprovalState>) -> Result<(), String> {
    let mut guard = state.child.lock().await;
    if let Some(child) = guard.as_mut() {
        if child.try_wait().map_err(|e| e.to_string())?.is_none() { return Err("运行期间不能修改调试与部门设置".into()); }
    }
    find_config_json(&app, "src-tauri/python/config.json")?;
    settings::save_workflow(&settings::directory(&app)?, &settings)
}

#[tauri::command]
async fn start_approval(
    app: AppHandle,
    cdp_endpoint: String,
    config_path: String,
    qty: String,
    biz_type: String,
    oa_type: String,
    test_mode: bool,
    inspect_only: Option<bool>,
    safe_debug: Option<bool>,
    state: State<'_, ApprovalState>,
) -> Result<(), String> {
    // 若上次进程已结束，自动清理；若仍在运行则拒绝重复启动
    let mut child_guard = state.child.lock().await;
    {
        let guard = &mut *child_guard;
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
    let workflow = settings::workflow(&settings::directory(&app)?)?;
    let inspect_only = inspect_only.unwrap_or(false);
    let safe_debug = workflow.debug_enabled || safe_debug.unwrap_or(false);
    if (safe_debug || inspect_only) && (oa_type != "old" || test_mode) {
        return Err("安全调试仅支持核心系统，不能运行 OA 或旧测试模式".into());
    }
    logs::record(&app, "runner/start", &format!("oa_type={oa_type}, test_mode={test_mode}, qty={qty}"));

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
    if inspect_only {
        cmd.arg("--inspect-departments");
    } else if safe_debug {
        cmd.arg("--safe-debug");
    } else if test_mode {
        cmd.arg("--test-mode");
    }

    cmd.env("PYTHONUNBUFFERED", "1")
        .stdout(std::process::Stdio::piped())
        .stdin(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("启动 Python 失败: {}", e))?;

    let stdout = child.stdout.take().ok_or("无法获取 Python stdout")?;
    let stderr = child.stderr.take().ok_or("无法获取 Python stderr")?;
    let stdin = child.stdin.take().ok_or("无法获取 Python stdin")?;

    let (cancel_tx, mut cancel_rx) = tokio::sync::mpsc::channel::<String>(1);

    {
        let mut tx_guard = state.cancel_tx.lock().await;
        *tx_guard = Some(cancel_tx);
    }
    *child_guard = Some(child);

    let app_stderr = app.clone();
    tokio::spawn(async move {
        let mut lines = BufReader::new(stderr).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            logs::record(&app_stderr, "runner/stderr", &line);
        }
    });

    // stdout 读取 + 事件转发
    let app_stdout = app.clone();
    tokio::spawn(async move {
        let reader = BufReader::new(stdout);
        let mut lines = reader.lines();

        while let Ok(Some(line)) = lines.next_line().await {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(&line) {
                if let Some(event_type) = value.get("event").and_then(|v| v.as_str()) {
                    // Do not duplicate entire extracted records in diagnostic files.
                    if !matches!(event_type, "data_extracted" | "submit_success" | "debug_result") {
                        logs::record(&app_stdout, "runner/event", &line);
                    }
                    let event_name = format!("approval:{}", event_type);
                    let _ = app_stdout.emit(&event_name, value);
                }
            } else { logs::record(&app_stdout, "runner/stdout", &line); }
        }

        logs::record(&app_stdout, "runner/finished", "执行组件输出结束");
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
#[derive(serde::Serialize, serde::Deserialize)]
struct PushSettings {
    wechat_enabled: bool,
    obsidian_enabled: bool,
    obsidian_directory: String,
    #[serde(default)]
    wechat_url: Option<String>,
    #[serde(default)]
    wechat_schema: Option<std::collections::BTreeMap<String, String>>,
    #[serde(default)]
    wechat_timeout: Option<u32>,
}

#[tauri::command]
async fn get_push_settings(app: AppHandle, config_path: String) -> Result<PushSettings, String> {
    let config = find_config_json(&app, &config_path)?;
    let path = config.with_file_name("push-settings.json");
    let text = tokio::fs::read_to_string(&config).await.map_err(|e| e.to_string())?;
    let config: serde_json::Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    let mut settings: PushSettings = if path.exists() {
        let text = tokio::fs::read_to_string(path).await.map_err(|e| e.to_string())?;
        serde_json::from_str(&text).map_err(|e| format!("登记设置读取失败: {}", e))?
    } else {
        PushSettings {
            wechat_enabled: config["webhook"]["enabled"].as_bool().unwrap_or(true),
            obsidian_enabled: false,
            obsidian_directory: String::new(),
            wechat_url: None,
            wechat_schema: None,
            wechat_timeout: None,
        }
    };
    settings.wechat_url.get_or_insert_with(|| config["webhook"]["url"].as_str().unwrap_or("").to_string());
    settings.wechat_schema.get_or_insert_with(|| {
        config["webhook"]["schema"].as_object().map(|fields| fields.iter()
            .filter_map(|(key, value)| value.as_str().map(|v| (key.clone(), v.to_string())))
            .collect()).unwrap_or_default()
    });
    settings.wechat_timeout.get_or_insert(config["webhook"]["timeout"].as_u64().unwrap_or(10) as u32);
    Ok(settings)
}

#[tauri::command]
async fn save_push_settings(
    app: AppHandle,
    config_path: String,
    mut settings: PushSettings,
    state: State<'_, ApprovalState>,
) -> Result<(), String> {
    let mut guard = state.child.lock().await;
    if let Some(child) = guard.as_mut() {
        if child.try_wait().map_err(|e| e.to_string())?.is_none() {
            return Err("审批运行期间不能修改登记设置".into());
        }
    }
    settings.obsidian_directory = settings.obsidian_directory.trim().to_string();
    if let Some(url) = settings.wechat_url.as_mut() { *url = url.trim().to_string(); }
    if let Some(schema) = settings.wechat_schema.as_mut() {
        for value in schema.values_mut() { *value = value.trim().to_string(); }
        schema.retain(|_, value| !value.is_empty());
        let distinct: std::collections::BTreeSet<_> = schema.values().collect();
        if distinct.len() != schema.len() { return Err("不同登记字段不能使用同一个字段标识".into()); }
    }
    if !(1..=120).contains(&settings.wechat_timeout.unwrap_or(10)) {
        return Err("请求超时时间须为 1 至 120 秒".into());
    }
    if settings.wechat_enabled {
        let url = settings.wechat_url.as_deref().unwrap_or("");
        let parsed = tauri::Url::parse(url).map_err(|_| "请填写有效的企业微信智能表格 Webhook 链接")?;
        if parsed.scheme() != "https" || parsed.host_str() != Some("qyapi.weixin.qq.com")
            || parsed.path() != "/cgi-bin/wedoc/smartsheet/webhook"
            || !parsed.query_pairs().any(|(key, value)| key == "key" && !value.is_empty()) {
            return Err("请使用企业微信智能表格 Webhook 链接，不是表格浏览链接或群机器人链接".into());
        }
        if settings.wechat_schema.as_ref().and_then(|s| s.get("title")).map_or(true, |s| s.is_empty()) {
            return Err("请配置项目名称对应的字段标识；其他字段可留空不登记".into());
        }
    }
    if settings.obsidian_enabled {
        let directory = std::path::Path::new(&settings.obsidian_directory);
        if !directory.is_absolute() || !directory.is_dir() {
            return Err("请选择存在的 Obsidian 记录文件夹，不能选择 .base 文件".into());
        }
    }
    let path = find_config_json(&app, &config_path)?.with_file_name("push-settings.json");
    let temp = path.with_extension("json.tmp");
    let content = serde_json::to_string_pretty(&settings).map_err(|e| e.to_string())?;
    tokio::fs::write(&temp, content).await.map_err(|e| format!("无法保存登记设置: {}", e))?;
    tokio::fs::rename(temp, path).await.map_err(|e| format!("无法替换登记设置: {}", e))?;
    Ok(())
}

#[tauri::command]
async fn select_obsidian_directory() -> Result<Option<String>, String> {
    // Use the built-in Windows folder dialog without another runtime dependency.
    let script = r#"
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = '选择 Obsidian 流程审核记录文件夹（不是 .base 文件）'
        try {
            if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                [Console]::Write($dialog.SelectedPath)
            }
        } finally { $dialog.Dispose() }
    "#;
    let mut command = tokio::process::Command::new("powershell.exe");
    command.args(["-NoProfile", "-STA", "-Command", script]);
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    let output = command.output().await.map_err(|e| format!("无法打开目录选择器: {}", e))?;
    if !output.status.success() {
        return Err("目录选择器启动失败，可手动输入目录路径".into());
    }
    let directory = String::from_utf8(output.stdout).map_err(|e| e.to_string())?;
    let directory = directory.trim().to_string();
    Ok(if directory.is_empty() { None } else { Some(directory) })
}

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
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(updater::UpdateState::default())
        .setup(|app| {
            logs::record(app.handle(), "app/start", &format!("version={}", app.package_info().version));
            Ok(())
        })
        .manage(ApprovalState {
            child: Mutex::new(None),
            cancel_tx: Mutex::new(None),
            browser_launch: Mutex::new(()),
        })
        .invoke_handler(tauri::generate_handler![
            connect_chrome,
            detect_chrome,
            launch_chrome,
            start_approval,
            cancel_approval,
            get_config,
            get_push_settings,
            save_push_settings,
            select_obsidian_directory,
            get_browser_settings,
            save_browser_settings,
            get_workflow_settings,
            save_workflow_settings,
            get_app_info,
            logs::append_ui_log,
            logs::open_log_directory,
            updater::update_info,
            updater::check_update,
            updater::install_update,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
