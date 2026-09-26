use std::{path::PathBuf, time::Duration};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use futures_util::{SinkExt, StreamExt};

#[derive(serde::Serialize)]
pub struct Detection {
    pub endpoint: String,
    pub message: String,
}

fn local_websocket(endpoint: &str) -> Result<tauri::Url, String> {
    let url = tauri::Url::parse(endpoint).map_err(|_| "调试地址格式错误")?;
    if url.scheme() != "ws" || !matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"))
        || url.port().unwrap_or(0) == 0 || !url.path().starts_with("/devtools/browser/")
        || !url.username().is_empty() || url.password().is_some() {
        return Err("仅支持本机 Chrome 浏览器调试地址".into());
    }
    Ok(url)
}

fn active_endpoint(content: &str) -> Result<String, String> {
    let mut lines = content.lines().map(str::trim).filter(|s| !s.is_empty());
    let port = lines.next().unwrap_or("").parse::<u16>().map_err(|_| "Chrome 调试记录中的端口无效")?;
    let path = lines.next().unwrap_or("");
    let endpoint = format!("ws://localhost:{port}{path}");
    local_websocket(&endpoint)?;
    Ok(endpoint)
}

pub async fn detect(mode: &str, port: u16, profile: &str) -> Result<Detection, String> {
    if mode == "port" {
        let endpoint = probe(port).await?.ok_or("此端口没有调试浏览器；请先启用调试，或选择启动专用浏览器")?;
        return Ok(Detection { endpoint, message: format!("已发现端口 {port} 的 Chrome，请点击直接连接") });
    }
    if mode != "auto" { return Err("未知连接方式".into()); }
    let directory = if profile.trim().is_empty() {
        PathBuf::from(std::env::var_os("LOCALAPPDATA").ok_or("无法定位 Chrome 资料目录")?)
            .join("Google/Chrome/User Data")
    } else { PathBuf::from(profile.trim()) };
    let content = std::fs::read_to_string(directory.join("DevToolsActivePort"))
        .map_err(|_| "未发现新版 Chrome 调试记录。请在 chrome://inspect/#remote-debugging 启用；自定义资料目录可在连接设置中指定")?;
    let endpoint = active_endpoint(&content)?;
    let url = local_websocket(&endpoint)?;
    tokio::time::timeout(Duration::from_secs(5), tokio::net::TcpStream::connect(("localhost", url.port().unwrap())))
        .await.map_err(|_| "Chrome 调试端口检测超时")?
        .map_err(|_| "发现旧调试记录，但浏览器未响应；请重新启用 Chrome 调试")?;
    Ok(Detection { endpoint, message: "已发现新版 Chrome 调试入口，尚未验证授权；点击直接连接后请在 Chrome 中允许".into() })
}

// A real CDP request distinguishes a live browser from stale discovery files.
pub async fn connect(endpoint: &str) -> Result<(), String> {
    local_websocket(endpoint)?;
    tokio::time::timeout(Duration::from_secs(60), async {
        let (mut socket, _) = tokio_tungstenite::connect_async(endpoint).await
            .map_err(|e| format!("连接被拒绝或不可用，请检查 Chrome 授权提示：{e}"))?;
        socket.send(tokio_tungstenite::tungstenite::Message::Text(
            r#"{"id":1,"method":"Browser.getVersion"}"#.into())).await.map_err(|e| e.to_string())?;
        while let Some(message) = socket.next().await {
            let message = message.map_err(|e| e.to_string())?;
            if let Ok(text) = message.to_text() {
                if let Ok(data) = serde_json::from_str::<serde_json::Value>(text) {
                    if data["id"] == 1 {
                        if !data["result"]["product"].as_str().unwrap_or("").contains("Chrome/") {
                            return Err("目标未提供 Chrome 调试能力".into());
                        }
                        let _ = socket.close(None).await;
                        return Ok(());
                    }
                }
            }
        }
        Err("浏览器中断了连接，请重新连接".into())
    }).await.map_err(|_| "等待授权超时，请在 Chrome 中允许连接后重试".to_string())?
}

fn response_complete(response: &[u8]) -> bool {
    let Some(end) = response.windows(4).position(|part| part == b"\r\n\r\n") else { return false; };
    let header = String::from_utf8_lossy(&response[..end]);
    header.lines().filter_map(|line| line.split_once(':')).any(|(name, value)| {
        name.eq_ignore_ascii_case("content-length") && value.trim().parse::<usize>()
            .map(|length| length <= 65536 && response.len() - end - 4 >= length).unwrap_or(false)
    })
}

fn validate_version(response: &[u8], port: u16) -> Result<String, String> {
    let response = std::str::from_utf8(response).map_err(|_| "调试端口返回了无效数据")?;
    let (header, body) = response.split_once("\r\n\r\n").ok_or("调试端口响应不完整")?;
    if !header.lines().next().unwrap_or("").contains(" 200 ") {
        return Err("该端口不是可用的 Chrome 调试服务，请检查端口占用".into());
    }
    let data: serde_json::Value = serde_json::from_str(body).map_err(|_| "该端口未返回浏览器信息")?;
    let websocket = data["webSocketDebuggerUrl"].as_str().unwrap_or("");
    let url = local_websocket(websocket)?;
    if !data["Browser"].as_str().unwrap_or("").contains("Chrome/")
        || url.scheme() != "ws"
        || url.port() != Some(port)
        || !url.path().starts_with("/devtools/browser/") {
        return Err("该端口未提供有效的本机 Chrome 调试服务".into());
    }
    Ok(websocket.to_string())
}

// Only connection-refused means it is safe to try starting a new browser.
pub async fn probe(port: u16) -> Result<Option<String>, String> {
    if port == 0 { return Err("端口必须在 1 到 65535 之间".into()); }
    // Windows can take just over two seconds to report a refused loopback port.
    tokio::time::timeout(Duration::from_secs(5), async {
        // Keep the original localhost resolution: Chrome may listen only on ::1.
        let mut socket = match tokio::net::TcpStream::connect(("localhost", port)).await {
            Ok(socket) => socket,
            Err(e) if e.kind() == std::io::ErrorKind::ConnectionRefused => return Ok(None),
            Err(e) => return Err(format!("无法检查浏览器端口: {e}")),
        };
        socket.write_all(format!("GET /json/version HTTP/1.1\r\nHost: localhost:{port}\r\nConnection: close\r\n\r\n").as_bytes())
            .await.map_err(|e| e.to_string())?;
        let mut response = Vec::new();
        // Chrome may ignore Connection: close; stop at the declared body length.
        let mut buffer = [0u8; 4096];
        loop {
            let count = socket.read(&mut buffer).await.map_err(|e| e.to_string())?;
            if count == 0 { break; }
            response.extend_from_slice(&buffer[..count]);
            if response.len() > 65536 { return Err("调试端口响应过大".into()); }
            if response_complete(&response) { break; }
        }
        Ok(Some(validate_version(&response, port)?))
    }).await.map_err(|_| "检查浏览器端口超时，请确认端口未被其他程序占用".to_string())?
}

fn chrome_path() -> Result<PathBuf, String> {
    for root in ["PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"] {
        if let Some(root) = std::env::var_os(root) {
            let path = PathBuf::from(root).join("Google/Chrome/Application/chrome.exe");
            if path.is_file() { return Ok(path); }
        }
    }
    Err("未在常见安装目录找到 Google Chrome，请安装 Chrome 后重试；自定义安装可按原方式手动启动调试浏览器".into())
}

pub async fn launch(profile: PathBuf, port: u16, executable: &str) -> Result<String, String> {
    if let Some(endpoint) = probe(port).await? { connect(&endpoint).await?; return Ok(endpoint); }
    let executable = if executable.trim().is_empty() { chrome_path()? } else { PathBuf::from(executable.trim()) };
    if !executable.is_file() || executable.file_name().and_then(|n| n.to_str()).map(|n| !n.eq_ignore_ascii_case("chrome.exe")).unwrap_or(true) {
        return Err("请选择有效的 chrome.exe 文件".into());
    }
    std::fs::create_dir_all(&profile).map_err(|e| format!("无法创建审批浏览器资料目录: {e}"))?;
    let mut command = tokio::process::Command::new(executable);
    command.arg(format!("--remote-debugging-port={port}"))
        .arg("--remote-debugging-address=127.0.0.1")
        .arg(format!("--user-data-dir={}", profile.display()))
        .args(["--no-first-run", "--no-default-browser-check", "--new-window", "about:blank"])
        .stdin(std::process::Stdio::null()).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null());
    let _child = command.spawn().map_err(|e| format!("启动 Chrome 失败: {e}"))?;
    let deadline = tokio::time::Instant::now() + Duration::from_secs(15);
    while tokio::time::Instant::now() < deadline {
        if let Some(endpoint) = probe(port).await? { connect(&endpoint).await?; return Ok(endpoint); }
        tokio::time::sleep(Duration::from_millis(200)).await;
    }
    Err("Chrome 已尝试启动，但调试连接未就绪。请检查单位浏览器策略；若审批专用窗口已打开，请关闭该专用窗口后重试，无需关闭普通 Chrome".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn complete_body_does_not_require_connection_close() {
        assert!(!response_complete(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\n{}"));
        assert!(response_complete(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"));
        assert!(!response_complete(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"));
    }
    #[test]
    fn rejects_unrelated_service_and_remote_websocket() {
        assert!(validate_version(b"HTTP/1.1 200 OK\r\n\r\n<html>ok</html>", 9222).is_err());
        for host in ["127.0.0.1", "localhost", "[::1]", "example.com", "[::2]"] {
            let response = format!("HTTP/1.1 200 OK\r\n\r\n{{\"Browser\":\"Chrome/140.0\",\"webSocketDebuggerUrl\":\"ws://{host}:9222/devtools/browser/test\"}}");
            assert_eq!(validate_version(response.as_bytes(), 9222).is_ok(), matches!(host, "127.0.0.1" | "localhost" | "[::1]"));
        }
    }
    #[test]
    fn validates_dynamic_discovery() {
        assert_eq!(active_endpoint("54321\r\n/devtools/browser/test\r\n").unwrap(), "ws://localhost:54321/devtools/browser/test");
        for content in ["0\n/devtools/browser/test", "70000\n/devtools/browser/test", "9222\nhttp://example.com", "9222", "bad\n/devtools/browser/test"] {
            assert!(active_endpoint(content).is_err());
        }
    }
    #[test]
    fn connects_to_dynamic_cdp_and_rejects_invalid_product() {
        tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(async {
            for product in ["Chrome/153.0", "UnrelatedService/1"] {
                let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
                let port = listener.local_addr().unwrap().port();
                let server = tokio::spawn(async move {
                    let (stream, _) = listener.accept().await.unwrap();
                    let mut ws = tokio_tungstenite::accept_async(stream).await.unwrap();
                    let request = ws.next().await.unwrap().unwrap();
                    let request: serde_json::Value = serde_json::from_str(request.to_text().unwrap()).unwrap();
                    assert_eq!(request["method"], "Browser.getVersion");
                    ws.send(tokio_tungstenite::tungstenite::Message::Text(
                        serde_json::json!({"id": 1, "result": {"product": product}}).to_string().into())).await.unwrap();
                    let _ = ws.next().await;
                });
                assert_eq!(connect(&format!("ws://127.0.0.1:{port}/devtools/browser/test")).await.is_ok(), product.starts_with("Chrome/"));
                server.await.unwrap();
            }
        });
    }
    #[test]
    fn detects_and_connects_ipv4_only_and_ipv6_only_browsers() {
        tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(async {
            for address in ["127.0.0.1:0", "[::1]:0"] {
                let listener = tokio::net::TcpListener::bind(address).await.unwrap();
                let port = listener.local_addr().unwrap().port();
                let endpoint = format!("ws://localhost:{port}/devtools/browser/regression");
                let expected = endpoint.clone();
                let server = tokio::spawn(async move {
                    let (mut stream, _) = listener.accept().await.unwrap();
                    let mut request = Vec::new();
                    let mut buffer = [0; 1024];
                    while !request.windows(4).any(|part| part == b"\r\n\r\n") {
                        let count = stream.read(&mut buffer).await.unwrap();
                        assert!(count > 0);
                        request.extend_from_slice(&buffer[..count]);
                    }
                    assert!(String::from_utf8_lossy(&request).contains(&format!("Host: localhost:{port}")));
                    let body = serde_json::json!({"Browser": "Chrome/154.0", "webSocketDebuggerUrl": endpoint}).to_string();
                    stream.write_all(format!("HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n{body}", body.len()).as_bytes()).await.unwrap();
                    drop(stream);
                    let (stream, _) = listener.accept().await.unwrap();
                    let mut ws = tokio_tungstenite::accept_async(stream).await.unwrap();
                    let request = ws.next().await.unwrap().unwrap();
                    assert!(request.to_text().unwrap().contains("Browser.getVersion"));
                    ws.send(tokio_tungstenite::tungstenite::Message::Text(
                        r#"{"id":1,"result":{"product":"Chrome/154.0"}}"#.into())).await.unwrap();
                    let _ = ws.next().await;
                });
                tokio::time::timeout(Duration::from_secs(15), async {
                    let result = detect("port", port, "").await.unwrap();
                    assert_eq!(result.endpoint, expected);
                    connect(&result.endpoint).await.unwrap();
                    server.await.unwrap();
                }).await.unwrap();
            }
        });
    }
}
