use std::{fs, io::{Cursor, Read}, path::{Path, PathBuf}, time::Duration};
use tauri::{Emitter, Manager};
use tauri_plugin_updater::{Update, UpdaterExt};
use tokio::sync::Mutex;

#[derive(Default)]
pub struct UpdateState(pub Mutex<Option<Update>>);

#[derive(serde::Deserialize)]
struct Source { endpoint: String, pubkey: String }

fn source() -> Result<Source, String> {
    serde_json::from_str(include_str!("../update-source.json")).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn update_info(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    let source = source()?;
    let result_file = app.path().app_local_data_dir().map_err(|e| e.to_string())?.join("update-result.json");
    let last_result = fs::read_to_string(result_file).ok().and_then(|s| serde_json::from_str::<serde_json::Value>(s.trim_start_matches('\u{feff}')).ok());
    Ok(serde_json::json!({ "version": app.package_info().version.to_string(), "configured": !source.endpoint.is_empty() && !source.pubkey.is_empty(), "last_result": last_result }))
}

#[tauri::command]
pub async fn check_update(app: tauri::AppHandle, state: tauri::State<'_, UpdateState>) -> Result<serde_json::Value, String> {
    let mut pending = state.0.lock().await;
    *pending = None;
    let source = source()?;
    if source.endpoint.is_empty() || source.pubkey.is_empty() { return Err("更新服务尚未配置，请等待发布者提供启用联网更新的版本".into()); }
    let url = tauri::Url::parse(&source.endpoint).map_err(|e| e.to_string())?;
    if url.scheme() != "https" { return Err("更新源必须使用 HTTPS".into()); }
    let mut update = app.updater_builder().pubkey(source.pubkey).endpoints(vec![url]).map_err(|e| e.to_string())?
        .timeout(Duration::from_secs(20)).build().map_err(|e| e.to_string())?.check().await.map_err(|e| format!("检查更新失败，当前版本仍可使用：{e}"))?;
    let response = if let Some(ref mut update) = update {
        if update.download_url.scheme() != "https" { return Err("更新包必须使用 HTTPS".into()); }
        update.timeout = Some(Duration::from_secs(300));
        serde_json::json!({"available": true, "version": update.version, "notes": update.body})
    } else { serde_json::json!({"available": false}) };
    *pending = update;
    Ok(response)
}

fn allowed(name: &str) -> bool {
    !name.contains('\\') && !name.contains(':') && !name.split('/').any(|p| matches!(p, ".." | "." | "")) &&
        (matches!(name, "ApprovalTool.exe" | "python/dist/ApprovalRunner/ApprovalRunner.exe") || name.starts_with("python/dist/ApprovalRunner/_internal/"))
}

fn extract(bytes: Vec<u8>, destination: &Path, expected_version: &str) -> Result<(), String> {
    let mut archive = zip::ZipArchive::new(Cursor::new(bytes)).map_err(|e| e.to_string())?;
    // The signed ZIP binds its version to the manifest, preventing replay of an
    // older signed package under an inflated server-side version number.
    let mut metadata = String::new();
    archive.by_name("release.json").map_err(|_| "更新包缺少签名版本信息")?.take(4096)
        .read_to_string(&mut metadata).map_err(|e| e.to_string())?;
    let metadata: serde_json::Value = serde_json::from_str(&metadata).map_err(|_| "更新版本信息无效")?;
    if metadata["version"].as_str() != Some(expected_version) { return Err("签名更新包版本与服务器声明不一致，已拒绝更新".into()); }
    let mut total = 0u64;
    for i in 0..archive.len() {
        let mut file = archive.by_index(i).map_err(|e| e.to_string())?;
        if file.is_dir() || file.name() == "release.json" { continue; }
        if !allowed(file.name()) || file.enclosed_name().is_none() || file.unix_mode().map(|m| m & 0o170000 == 0o120000).unwrap_or(false) {
            return Err("更新包含非法路径或非程序文件，已拒绝安装".into());
        }
        total = total.checked_add(file.size()).ok_or("更新包过大")?;
        if total > 2_000_000_000 || i >= 20000 { return Err("更新包超过安全大小限制".into()); }
        let path = destination.join(file.name());
        fs::create_dir_all(path.parent().ok_or("无效更新路径")?).map_err(|e| e.to_string())?;
        let mut output = fs::OpenOptions::new().write(true).create_new(true).open(&path).map_err(|e| e.to_string())?;
        let expected = file.size();
        let copied = std::io::copy(&mut file.by_ref().take(expected + 1), &mut output).map_err(|e| e.to_string())?;
        if copied != expected { return Err("更新文件长度异常".into()); }
    }
    for relative in ["ApprovalTool.exe", "python/dist/ApprovalRunner/ApprovalRunner.exe"] {
        if !destination.join(relative).is_file() { return Err(format!("更新包缺少必要程序文件：{relative}")); }
    }
    if !destination.join("python/dist/ApprovalRunner/_internal").is_dir() { return Err("更新包缺少运行组件".into()); }
    Ok(())
}

#[tauri::command]
pub async fn install_update(app: tauri::AppHandle, state: tauri::State<'_, UpdateState>, approval: tauri::State<'_, crate::ApprovalState>) -> Result<(), String> {
    // Keep the same lock as start/save so no approval can start during replacement.
    let mut running = approval.child.lock().await;
    if let Some(child) = running.as_mut() {
        if child.try_wait().map_err(|e| e.to_string())?.is_none() { return Err("请等待当前审批完成后更新".into()); }
    }
    let pending = state.0.lock().await;
    let update = pending.as_ref().ok_or("请先检查更新")?;
    crate::find_config_json(&app, "src-tauri/python/config.json")?;
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    if exe.file_name().and_then(|n| n.to_str()) != Some("ApprovalTool.exe") { return Err("联网更新仅适用于完整绿色版，请勿在开发构建中安装".into()); }
    let root = dunce::canonicalize(exe.parent().ok_or("无法定位程序目录")?).map_err(|e| e.to_string())?;
    let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos();
    let stage = root.join(format!(".approval-update-{stamp}"));
    fs::create_dir(&stage).map_err(|e| format!("程序目录不可写，无法更新：{e}"))?;
    let mut downloaded = 0u64;
    let bytes = update.download(|chunk, total| {
        downloaded += chunk as u64;
        let _ = app.emit("update:progress", serde_json::json!({"downloaded": downloaded, "total": total}));
    }, || {}).await.map_err(|e| format!("下载或签名校验失败，旧程序未修改：{e}"))?;
    extract(bytes, &stage.join("new"), &update.version)?;
    let job = stage.join("job.json");
    let result: PathBuf = app.path().app_local_data_dir().map_err(|e| e.to_string())?.join("update-result.json");
    fs::write(&job, serde_json::to_vec(&serde_json::json!({ "root": root, "stage": stage, "pid": std::process::id(), "version": update.version, "result": result })).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    let script = stage.join("apply.ps1");
    fs::write(&script, include_bytes!("portable-update.ps1")).map_err(|e| e.to_string())?;
    let mut command = std::process::Command::new("powershell.exe");
    command.args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"]).arg(script).arg("-JobFile").arg(job);
    #[cfg(windows)] { use std::os::windows::process::CommandExt; command.creation_flags(0x08000000); }
    let mut helper = command.spawn().map_err(|e| format!("无法启动更新助手，旧程序未修改：{e}"))?;
    let deadline = tokio::time::Instant::now() + Duration::from_secs(10);
    while !stage.join("ready").exists() {
        if helper.try_wait().map_err(|e| e.to_string())?.is_some() {
            return Err("更新助手被系统策略阻止或无法启动；程序未退出、未替换".into());
        }
        if tokio::time::Instant::now() >= deadline {
            let _ = helper.kill();
            return Err("更新助手启动超时，程序未退出、未替换".into());
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    app.exit(0);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    #[test]
    fn plugin_initializes_even_before_publisher_is_configured() {
        let config: serde_json::Value = serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        let _: tauri_plugin_updater::Config = serde_json::from_value(config["plugins"]["updater"].clone()).unwrap();
    }
    #[test]
    fn update_paths_cannot_overwrite_settings_or_escape_directory() {
        for name in ["ApprovalTool.exe", "python/dist/ApprovalRunner/ApprovalRunner.exe", "python/dist/ApprovalRunner/_internal/library.zip"] { assert!(allowed(name)); }
        for name in ["../ApprovalTool.exe", "C:/secret", "python/dist/ApprovalRunner/config.json", "python/dist/ApprovalRunner/push-settings.json", "python/dist/ApprovalRunner/_internal/../../config.json", "ApprovalTool.exe:stream", "Settings/browser.json"] { assert!(!allowed(name)); }
    }
    #[test]
    fn extracts_complete_program_but_rejects_configuration_payload() {
        let root = std::env::temp_dir().join(format!("approval-zip-test-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        for inject_config in [false, true] {
            let mut zip = zip::ZipWriter::new(Cursor::new(Vec::new()));
            zip.start_file("release.json", zip::write::SimpleFileOptions::default()).unwrap();
            zip.write_all(br#"{"version":"2.1.0"}"#).unwrap();
            for path in ["ApprovalTool.exe", "python/dist/ApprovalRunner/ApprovalRunner.exe", "python/dist/ApprovalRunner/_internal/runtime.dll"] {
                zip.start_file(path, zip::write::SimpleFileOptions::default()).unwrap();
                zip.write_all(b"test-program").unwrap();
            }
            if inject_config {
                zip.start_file("python/dist/ApprovalRunner/config.json", zip::write::SimpleFileOptions::default()).unwrap();
                zip.write_all(b"must-not-replace-settings").unwrap();
            }
            let bytes = zip.finish().unwrap().into_inner();
            let destination = root.join(if inject_config { "invalid" } else { "valid" });
            assert!(extract(bytes.clone(), &root.join("wrong-version"), "9.0.0").is_err());
            assert_eq!(extract(bytes, &destination, "2.1.0").is_ok(), !inject_config);
            assert!(!destination.join("python/dist/ApprovalRunner/config.json").exists());
        }
        fs::remove_dir_all(root).unwrap();
    }
}
