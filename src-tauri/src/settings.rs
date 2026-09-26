use std::{fs, path::{Path, PathBuf}, sync::Mutex};
use serde_json::Value;
use tauri::Manager;

static IO_LOCK: Mutex<()> = Mutex::new(());

pub fn directory(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let name = if cfg!(debug_assertions) { "Settings-dev" } else { "Settings" };
    Ok(app.path().app_local_data_dir().map_err(|e| e.to_string())?.join(name))
}

fn read_object(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("无法读取 {}: {e}", path.display()))?;
    let value: Value = serde_json::from_str(&text).map_err(|e| format!("配置格式错误 {}: {e}；原文件未修改", path.display()))?;
    if !value.is_object() { return Err(format!("配置必须为 JSON 对象：{}", path.display())); }
    Ok(value)
}

// Only the first launch migrates legacy files. Never replace a local setting
// with a default from an update, including when a saved file is damaged.
pub fn initialize(directory: &Path, legacy: &Path) -> Result<PathBuf, String> {
    let _guard = IO_LOCK.lock().map_err(|e| e.to_string())?;
    let config = directory.join("config.json");
    if directory.exists() {
        read_object(&config)?;
        return Ok(config);
    }
    let legacy_config = read_object(legacy)?;
    let push = legacy.with_file_name("push-settings.json");
    let push_value = if push.exists() { Some(read_object(&push)?) } else { None };
    let parent = directory.parent().ok_or("无法定位用户配置目录")?;
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let pending = parent.join(format!("Settings-migrating-{}-{}", std::process::id(),
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos()));
    fs::create_dir(&pending).map_err(|e| e.to_string())?;
    let result = (|| {
        fs::write(pending.join("config.json"), serde_json::to_vec_pretty(&legacy_config).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
        if let Some(value) = push_value {
            fs::write(pending.join("push-settings.json"), serde_json::to_vec_pretty(&value).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
        }
        fs::rename(&pending, directory).map_err(|e| format!("本机配置迁移失败，旧配置保留：{e}"))?;
        Ok(config)
    })();
    if pending.exists() { let _ = fs::remove_dir_all(&pending); }
    result
}

#[derive(Clone, serde::Serialize, serde::Deserialize)]
#[serde(default)]
pub struct BrowserSettings {
    pub mode: String,
    pub port: u16,
    pub profile: String,
    pub executable: String,
}

impl Default for BrowserSettings {
    fn default() -> Self { Self { mode: "smart".into(), port: 9222, profile: String::new(), executable: String::new() } }
}

impl BrowserSettings {
    pub fn validate(&self) -> Result<(), String> {
        if self.port == 0 || !matches!(self.mode.as_str(), "smart" | "auto" | "port") {
            return Err("请选择有效连接方式，端口需为 1 到 65535".into());
        }
        Ok(())
    }
}

pub fn browser(directory: &Path, legacy: Option<BrowserSettings>) -> Result<BrowserSettings, String> {
    let path = directory.join("browser.json");
    if path.exists() {
        let settings: BrowserSettings = serde_json::from_value(read_object(&path)?).map_err(|e| e.to_string())?;
        settings.validate()?;
        return Ok(settings);
    }
    let settings = legacy.unwrap_or_default();
    save_browser(directory, &settings)?;
    Ok(settings)
}

pub fn save_browser(directory: &Path, settings: &BrowserSettings) -> Result<(), String> {
    settings.validate()?;
    let _guard = IO_LOCK.lock().map_err(|e| e.to_string())?;
    let path = directory.join("browser.json");
    let temp = directory.join("browser.json.tmp");
    fs::write(&temp, serde_json::to_vec_pretty(settings).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    fs::rename(temp, path).map_err(|e| e.to_string())
}

#[derive(Clone, serde::Serialize, serde::Deserialize)]
pub struct Department { pub id: String, pub name: String }

#[derive(Clone, Default, serde::Serialize, serde::Deserialize)]
#[serde(default)]
pub struct WorkflowSettings {
    pub debug_enabled: bool,
    pub debug_steps: u8,
    pub show_department: bool,
    pub department_id: String,
    pub departments: Vec<Department>,
    pub source: String,
}

impl WorkflowSettings {
    pub fn validate(&self) -> Result<(), String> {
        if self.debug_steps > 10 || (self.debug_enabled && self.debug_steps == 0) {
            return Err("开启调试前请确认审批步骤数（1至10）".into());
        }
        let mut ids = std::collections::BTreeSet::new();
        for item in &self.departments {
            if item.id.trim().is_empty() || item.name.trim().is_empty() || !ids.insert(&item.id) {
                return Err("部门选项为空或编号重复，请重新读取".into());
            }
        }
        if !self.department_id.is_empty() && !ids.contains(&self.department_id) {
            return Err("所选部门不在已读取的选项中".into());
        }
        if !self.departments.is_empty() {
            let url = tauri::Url::parse(&self.source).map_err(|_| "部门来源无效")?;
            if !matches!(url.scheme(), "http" | "https") || url.origin().ascii_serialization() != self.source {
                return Err("部门来源无效，请重新读取".into());
            }
        }
        Ok(())
    }
}

pub fn workflow(directory: &Path) -> Result<WorkflowSettings, String> {
    let path = directory.join("workflow.json");
    let value: WorkflowSettings = if path.exists() {
        serde_json::from_value(read_object(&path)?).map_err(|e| e.to_string())?
    } else { WorkflowSettings::default() };
    value.validate()?;
    Ok(value)
}

pub fn save_workflow(directory: &Path, value: &WorkflowSettings) -> Result<(), String> {
    value.validate()?;
    let _guard = IO_LOCK.lock().map_err(|e| e.to_string())?;
    let path = directory.join("workflow.json");
    let temp = directory.join("workflow.json.tmp");
    fs::write(&temp, serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    fs::rename(temp, path).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn workflow_validation_requires_steps_and_unique_department() {
        let mut value = WorkflowSettings::default();
        assert!(value.validate().is_ok());
        value.debug_enabled = true;
        assert!(value.validate().is_err());
        value.debug_steps = 3;
        value.departments = vec![Department { id: "id1".into(), name: "Test".into() }];
        value.source = "http://fixture.test".into();
        value.department_id = "id1".into();
        assert!(value.validate().is_ok());
        value.department_id = "missing".into();
        assert!(value.validate().is_err());
        value.department_id = "id1".into();
        value.departments.push(Department { id: "id1".into(), name: "Duplicate".into() });
        assert!(value.validate().is_err());
    }
    #[test]
    fn upgrade_preserves_local_settings_and_fails_closed_on_corruption() {
        let root = std::env::temp_dir().join(format!("approval-settings-test-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let legacy = root.join("config.json");
        fs::write(&legacy, r#"{"webhook":{"url":"user-value"}}"#).unwrap();
        fs::write(root.join("push-settings.json"), r#"{"wechat_enabled":false,"obsidian_directory":"X:/records"}"#).unwrap();
        let local = root.join("Settings");
        initialize(&local, &legacy).unwrap();
        fs::write(&legacy, r#"{"webhook":{"url":"new-release-default"}}"#).unwrap();
        initialize(&local, &legacy).unwrap();
        assert_eq!(read_object(&local.join("config.json")).unwrap()["webhook"]["url"], "user-value");
        assert_eq!(read_object(&local.join("push-settings.json")).unwrap()["obsidian_directory"], "X:/records");
        let mut prefs = BrowserSettings::default();
        prefs.port = 12345;
        save_browser(&local, &prefs).unwrap();
        assert_eq!(browser(&local, Some(BrowserSettings::default())).unwrap().port, 12345);
        let workflow_prefs = WorkflowSettings { debug_enabled: true, debug_steps: 3, show_department: true, ..Default::default() };
        save_workflow(&local, &workflow_prefs).unwrap();
        assert!(workflow(&local).unwrap().debug_enabled);
        assert_eq!(workflow(&local).unwrap().debug_steps, 3);
        fs::write(local.join("config.json"), "broken").unwrap();
        assert!(initialize(&local, &legacy).is_err());
        assert_eq!(fs::read_to_string(local.join("config.json")).unwrap(), "broken");
        fs::remove_dir_all(root).unwrap();
    }
}
