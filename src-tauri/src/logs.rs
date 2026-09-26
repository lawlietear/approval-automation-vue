use std::{fs::{self, OpenOptions}, io::Write, path::{Path, PathBuf}, sync::{Mutex, OnceLock}};
use chrono::{Local, NaiveDate, Days};
use regex::Regex;
use tauri::{AppHandle, Manager, Emitter};

static LOCK: Mutex<()> = Mutex::new(());

pub fn directory(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app.path().app_local_data_dir().map_err(|e| e.to_string())?
        .join(if cfg!(debug_assertions) { "Logs-dev" } else { "Logs" }))
}

fn redact(text: &str) -> String {
    fn clean(value: &mut serde_json::Value) {
        match value {
            serde_json::Value::String(text) => *text = redact_text(text),
            serde_json::Value::Array(items) => items.iter_mut().for_each(clean),
            serde_json::Value::Object(map) => for (key, value) in map {
                let key = key.to_ascii_lowercase().replace(['_', '-'], "");
                if matches!(key.as_str(), "authorization" | "apikey" | "accesstoken" | "token" | "secret" | "password" | "key") {
                    *value = serde_json::Value::String("[已隐藏]".into());
                } else { clean(value); }
            },
            _ => {}
        }
    }
    if let Ok(mut value) = serde_json::from_str::<serde_json::Value>(text) {
        clean(&mut value);
        return value.to_string();
    }
    redact_text(text)
}

fn redact_text(text: &str) -> String {
    static URL: OnceLock<Regex> = OnceLock::new();
    static SECRET: OnceLock<Regex> = OnceLock::new();
    let url = URL.get_or_init(|| Regex::new(r#"(?i)(?:https?|wss?)://[^\s<>"']+"#).unwrap());
    let secret = SECRET.get_or_init(|| Regex::new(
        r#"(?i)(["']?(?:authorization|api[_-]?key|access[_-]?token|token|secret|password|key)["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|Bearer\s+[^\s,;}]+|[^\s,;}]+)"#
    ).unwrap());
    let text = url.replace_all(text, "[链接已隐藏]");
    secret.replace_all(&text, "${1}[已隐藏]").into_owned()
}

fn append_at(directory: &Path, date: NaiveDate, timestamp: &str, source: &str, message: &str) -> Result<(), String> {
    let _guard = LOCK.lock().map_err(|e| e.to_string())?;
    fs::create_dir_all(directory).map_err(|e| e.to_string())?;
    let cutoff = date.checked_sub_days(Days::new(4)).ok_or("日志日期无效")?;
    // Only remove our dated regular files, never directories or linked files.
    for entry in fs::read_dir(directory).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if let Some(day) = name.strip_prefix("approval-").and_then(|v| v.strip_suffix(".log")) {
            if let Ok(parsed) = NaiveDate::parse_from_str(day, "%Y-%m-%d") {
                if parsed < cutoff && name == format!("approval-{}.log", parsed.format("%Y-%m-%d"))
                    && entry.file_type().map_err(|e| e.to_string())?.is_file() {
                    fs::remove_file(entry.path()).map_err(|e| e.to_string())?;
                }
            }
        }
    }
    let path = directory.join(format!("approval-{}.log", date.format("%Y-%m-%d")));
    if let Ok(meta) = fs::symlink_metadata(&path) {
        if !meta.is_file() || meta.file_type().is_symlink() { return Err("日志目标不是普通文件".into()); }
    }
    let mut file = OpenOptions::new().create(true).append(true).open(path).map_err(|e| e.to_string())?;
    let record = serde_json::json!({"time": timestamp, "pid": std::process::id(), "source": source, "message": redact(message)});
    writeln!(file, "{record}").map_err(|e| e.to_string())
}

pub fn append(app: &AppHandle, source: &str, message: &str) -> Result<(), String> {
    let now = Local::now();
    append_at(&directory(app)?, now.date_naive(), &now.to_rfc3339(), source, message)
        .map_err(|e| format!("本地日志保存失败：{e}"))
}

pub fn record(app: &AppHandle, source: &str, message: &str) {
    if let Err(error) = append(app, source, message) {
        let _ = app.emit("approval:log", serde_json::json!({"level":"error", "msg":error}));
    }
}

#[tauri::command]
pub fn append_ui_log(app: AppHandle, level: String, message: String) -> Result<(), String> {
    append(&app, &format!("ui/{level}"), &message)
}

#[tauri::command]
pub fn open_log_directory(app: AppHandle) -> Result<(), String> {
    let path = directory(&app)?;
    fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    std::process::Command::new("explorer.exe").arg(path).spawn().map_err(|e| e.to_string())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn retains_five_calendar_days_and_appends_across_restart() {
        let root = std::env::temp_dir().join(format!("approval-logs-test-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("keep.log"), "keep").unwrap();
        fs::create_dir_all(root.join("approval-2026-01-01.log")).unwrap();
        for day in 18..=24 {
            append_at(&root, NaiveDate::from_ymd_opt(2026, 9, day).unwrap(), "time", "test", "first").unwrap();
        }
        append_at(&root, NaiveDate::from_ymd_opt(2026, 9, 24).unwrap(), "time", "test", "second\nline").unwrap();
        assert!(!root.join("approval-2026-09-19.log").exists());
        for day in 20..=24 { assert!(root.join(format!("approval-2026-09-{day}.log")).exists()); }
        let content = fs::read_to_string(root.join("approval-2026-09-24.log")).unwrap();
        assert_eq!(content.lines().count(), 2);
        for line in content.lines() { serde_json::from_str::<serde_json::Value>(line).unwrap(); }
        assert!(root.join("keep.log").exists());
        assert!(root.join("approval-2026-01-01.log").is_dir());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn redacts_urls_and_credentials_but_keeps_error_codes() {
        let text = redact(r#"HTTP 403 errcode=40001 https://example.test/hook?key=private api_key=abc {"password":"two words", "token":"xyz"}"#);
        for secret in ["private", "abc", "two words", "xyz", "example.test"] { assert!(!text.contains(secret)); }
        assert!(text.contains("40001"));
        let event = serde_json::json!({"msg": "failed password=hidden Authorization: Bearer secret123", "token":"xyz"}).to_string();
        let safe = redact(&event);
        for secret in ["hidden", "secret123", "xyz"] { assert!(!safe.contains(secret)); }
    }
    #[test]
    fn concurrent_messages_remain_complete_and_io_errors_are_reported() {
        let root = std::env::temp_dir().join(format!("approval-logs-concurrent-{}", std::process::id()));
        let date = NaiveDate::from_ymd_opt(2026, 9, 24).unwrap();
        let workers: Vec<_> = (0..12).map(|i| {
            let root = root.clone();
            std::thread::spawn(move || append_at(&root, date, "time", "test", &format!("record-{i}")).unwrap())
        }).collect();
        for worker in workers { worker.join().unwrap(); }
        let path = root.join("approval-2026-09-24.log");
        let content = fs::read_to_string(&path).unwrap();
        assert_eq!(content.lines().count(), 12);
        for line in content.lines() { serde_json::from_str::<serde_json::Value>(line).unwrap(); }
        assert!(append_at(&path, date, "time", "test", "fail").is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
