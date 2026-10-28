use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "macos")]
use std::os::unix::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const STARTUP_TIMEOUT: Duration = Duration::from_secs(90);
#[cfg(target_os = "macos")]
const PROCESS_GROUP_STOP_TIMEOUT: Duration = Duration::from_secs(3);

pub struct BackendState {
    child: Mutex<Option<Child>>,
}

pub struct LaunchedBackend {
    pub child: Child,
    pub url: String,
}

impl BackendState {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
        }
    }

    pub fn track(&self, mut child: Child) -> Result<(), String> {
        let Ok(mut guard) = self.child.lock() else {
            terminate_child(&mut child);
            return Err("无法记录内置后端进程".to_string());
        };
        if guard.is_some() {
            terminate_child(&mut child);
            return Err("内置后端进程已经启动".to_string());
        }
        *guard = Some(child);
        Ok(())
    }

    pub fn stop(&self) -> bool {
        let Ok(mut guard) = self.child.lock() else {
            return false;
        };
        let Some(mut child) = guard.take() else {
            return false;
        };
        terminate_child(&mut child);
        true
    }
}

impl Drop for BackendState {
    fn drop(&mut self) {
        self.stop();
    }
}

fn terminate_child(child: &mut Child) {
    #[cfg(target_os = "windows")]
    {
        let pid = child.id().to_string();
        let _ = Command::new("taskkill")
            .args(["/PID", pid.as_str(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(target_os = "macos")]
    terminate_macos_process_group(child);
    #[cfg(not(target_os = "macos"))]
    {
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[cfg(target_os = "macos")]
fn terminate_macos_process_group(child: &mut Child) {
    let Ok(process_group) = i32::try_from(child.id()) else {
        let _ = child.kill();
        let _ = child.wait();
        return;
    };

    send_macos_process_group_signal(process_group, libc::SIGTERM);
    let deadline = Instant::now() + PROCESS_GROUP_STOP_TIMEOUT;
    while macos_process_group_is_alive(process_group) && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(50));
    }
    if macos_process_group_is_alive(process_group) {
        send_macos_process_group_signal(process_group, libc::SIGKILL);
    }
    let _ = child.wait();
}

#[cfg(target_os = "macos")]
fn send_macos_process_group_signal(process_group: i32, signal: i32) {
    unsafe {
        libc::kill(-process_group, signal);
    }
}

#[cfg(target_os = "macos")]
fn macos_process_group_is_alive(process_group: i32) -> bool {
    let result = unsafe { libc::kill(-process_group, 0) };
    result == 0 || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
}

#[cfg(all(test, target_os = "macos"))]
fn pid_is_alive(pid: u32) -> bool {
    let Ok(pid) = i32::try_from(pid) else {
        return false;
    };
    let result = unsafe { libc::kill(pid, 0) };
    result == 0 || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
}

pub fn launch(app: &AppHandle) -> Result<LaunchedBackend, String> {
    let user_root = app
        .path()
        .app_local_data_dir()
        .map_err(|error| format!("无法解析用户数据目录: {error}"))?;
    let logs_dir = user_root.join("logs");
    fs::create_dir_all(&logs_dir).map_err(|error| format!("无法创建桌面日志目录: {error}"))?;

    let backend_path = resolve_backend_path(app)?;
    if !backend_path.is_file() {
        return Err(format!("内置后端不存在: {}", backend_path.display()));
    }

    let config_dir = user_root.join("config");
    fs::create_dir_all(&config_dir)
        .map_err(|error| format!("无法创建配置目录: {error}"))?;
    let port_file = config_dir.join("backend-port");
    let _ = fs::remove_file(&port_file);

    let log_path = logs_dir.join("backend-console.log");
    let stdout = open_log(&log_path)?;
    let stderr = stdout
        .try_clone()
        .map_err(|error| format!("无法复制后端日志句柄: {error}"))?;

    let mut command = Command::new(&backend_path);
    command
        .arg("--port")
        .arg("0")
        .arg("--user-data-dir")
        .arg(&user_root)
        .current_dir(&user_root)
        .env("PYTHONUTF8", "1")
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));
    if let Some(backend_dir) = backend_path.parent() {
        let mut paths = vec![backend_dir.to_path_buf()];
        if let Some(current_path) = std::env::var_os("PATH") {
            paths.extend(std::env::split_paths(&current_path));
        }
        if let Ok(runtime_path) = std::env::join_paths(paths) {
            command.env("PATH", runtime_path);
        }
    }

    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);

    #[cfg(target_os = "macos")]
    command.process_group(0);

    let mut child = command
        .spawn()
        .map_err(|error| format!("无法启动内置后端: {error}"))?;

    let actual_port = match read_port_file(&port_file, &mut child, STARTUP_TIMEOUT) {
        Ok(port) => port,
        Err(error) => {
            terminate_child(&mut child);
            return Err(format!("{}（详见 backend-console.log）", error));
        }
    };

    Ok(LaunchedBackend {
        child,
        url: format!("http://127.0.0.1:{}", actual_port),
    })
}

/// 等后端把实际监听端口写进端口文件。
///
/// 子进程提前退出时立刻返回错误，而不是把 90 秒超时白等完——「后端崩了」
/// 与「后端慢」在诊断上完全不同（R47）。
fn read_port_file(path: &Path, child: &mut Child, timeout: Duration) -> Result<u16, String> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!("后端在报告端口前退出（{status}）"));
        }
        if let Ok(content) = fs::read_to_string(path) {
            for line in content.lines() {
                if let Some(port_str) = line.strip_prefix("LISTEN_PORT=") {
                    if let Ok(port) = port_str.parse::<u16>() {
                        if port > 0 {
                            return Ok(port);
                        }
                    }
                }
            }
        }
        thread::sleep(Duration::from_millis(50));
    }
    Err(format!(
        "后端未在 {} 秒内上报监听端口（{}）",
        timeout.as_secs(),
        path.display()
    ))
}

pub fn wait_until_ready(base_url: &str) -> Result<(), String> {
    let address = base_url
        .strip_prefix("http://")
        .ok_or_else(|| format!("无效的本地服务地址: {base_url}"))?;
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    let mut last_error = String::new();

    while Instant::now() < deadline {
        match request_status(address) {
            Ok(status) if status == 200 => return Ok(()),
            Ok(status) => last_error = format!("状态接口返回 HTTP {status}"),
            Err(error) => last_error = error,
        }
        thread::sleep(Duration::from_millis(250));
    }

    Err(format!(
        "本地服务未在 {} 秒内就绪: {last_error}",
        STARTUP_TIMEOUT.as_secs()
    ))
}

fn request_status(address: &str) -> Result<u16, String> {
    let mut stream = TcpStream::connect_timeout(
        &address
            .parse()
            .map_err(|error| format!("无法解析本地服务地址: {error}"))?,
        Duration::from_secs(1),
    )
    .map_err(|error| error.to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .map_err(|error| error.to_string())?;
    stream
        .write_all(
            b"GET /api/system/status HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
        )
        .map_err(|error| error.to_string())?;

    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| error.to_string())?;
    let status = response
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or_else(|| "状态接口返回了无效响应".to_string())?;
    Ok(status)
}

fn resolve_backend_path(app: &AppHandle) -> Result<PathBuf, String> {
    if let Some(path) = std::env::var_os("DETERMINFLOW_DESKTOP_BACKEND") {
        return Ok(PathBuf::from(path));
    }
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| format!("无法解析安装资源目录: {error}"))?;
    let executable = if cfg!(target_os = "windows") {
        "determinflow-backend.exe"
    } else {
        "determinflow-backend"
    };
    Ok(resource_dir
        .join("runtime")
        .join("backend")
        .join(executable))
}

fn open_log(path: &Path) -> Result<std::fs::File, String> {
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| format!("无法打开后端日志 {}: {}", path.display(), error))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spawn_long_running_child() -> Child {
        #[cfg(target_os = "windows")]
        {
            let mut command = Command::new("cmd");
            command
                .args(["/C", "ping 127.0.0.1 -n 30 > nul"])
                .creation_flags(CREATE_NO_WINDOW)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null());
            return command.spawn().expect("test child should start");
        }

        #[cfg(not(target_os = "windows"))]
        {
            let mut command = Command::new("sh");
            command
                .args(["-c", "sleep 30"])
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null());
            #[cfg(target_os = "macos")]
            command.process_group(0);
            command.spawn().expect("test child should start")
        }
    }

    #[cfg(target_os = "macos")]
    fn spawn_process_group_with_child() -> (Child, u32) {
        use std::io::{BufRead, BufReader};
        let mut command = Command::new("sh");
        command
            .args(["-c", "sleep 30 & echo $!; wait"])
            .process_group(0)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        let mut child = command.spawn().expect("process group should start");
        let stdout = child.stdout.take().expect("child stdout should be piped");
        let mut line = String::new();
        BufReader::new(stdout)
            .read_line(&mut line)
            .expect("grandchild pid should be reported");
        let grandchild = line
            .trim()
            .parse::<u32>()
            .expect("grandchild pid should be numeric");
        (child, grandchild)
    }

    #[test]
    fn read_port_file_parses_listen_port_line() {
        let dir = std::env::temp_dir().join("determinflow-port-test");
        let _ = fs::create_dir_all(&dir);
        let path = dir.join("backend-port");
        let _ = fs::remove_file(&path);
        fs::write(&path, b"LISTEN_PORT=54321\n").unwrap();

        let mut child = spawn_long_running_child();
        let port = read_port_file(&path, &mut child, Duration::from_secs(2))
            .expect("should read port");
        assert_eq!(port, 54321);
        terminate_child(&mut child);
    }

    #[test]
    fn read_port_file_rejects_zero_and_garbage() {
        let dir = std::env::temp_dir().join("determinflow-port-test-bad");
        let _ = fs::create_dir_all(&dir);
        let path = dir.join("backend-port");
        let _ = fs::remove_file(&path);
        let mut child = spawn_long_running_child();

        // zero is rejected
        fs::write(&path, b"LISTEN_PORT=0\n").unwrap();
        let result = read_port_file(&path, &mut child, Duration::from_millis(200));
        assert!(result.is_err(), "zero port should be rejected");

        // garbage is ignored
        fs::write(&path, b"hello world\n").unwrap();
        let result = read_port_file(&path, &mut child, Duration::from_millis(200));
        assert!(result.is_err(), "garbage should be ignored");
        terminate_child(&mut child);
    }

    #[test]
    fn read_port_file_reports_early_child_exit() {
        let dir = std::env::temp_dir().join("determinflow-port-test-exit");
        let _ = fs::create_dir_all(&dir);
        let path = dir.join("backend-port");
        let _ = fs::remove_file(&path);

        #[cfg(target_os = "windows")]
        let mut command = {
            let mut command = Command::new("cmd");
            command.args(["/C", "exit 3"]).creation_flags(CREATE_NO_WINDOW);
            command
        };
        #[cfg(not(target_os = "windows"))]
        let mut command = {
            let mut command = Command::new("sh");
            command.args(["-c", "exit 3"]);
            command
        };
        let mut child = command
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("short-lived child should start");

        let started = Instant::now();
        let error = read_port_file(&path, &mut child, Duration::from_secs(30))
            .expect_err("exited child should be reported");
        assert!(
            error.contains("退出"),
            "错误信息应说明进程已退出，实得: {error}"
        );
        assert!(
            started.elapsed() < Duration::from_secs(10),
            "进程退出应立即返回，而不是等满 30 秒超时"
        );
    }

    #[test]
    fn rejects_non_http_backend_urls() {
        let error = wait_until_ready("https://127.0.0.1:1").unwrap_err();
        assert!(error.contains("无效的本地服务地址"));
    }

    #[test]
    fn stops_the_tracked_backend_once() {
        let state = BackendState::new();
        state
            .track(spawn_long_running_child())
            .expect("backend should be tracked");

        assert!(state.stop());
        assert!(!state.stop());
    }

    #[test]
    fn rejects_and_terminates_a_second_tracked_backend() {
        let state = BackendState::new();
        state
            .track(spawn_long_running_child())
            .expect("first backend should be tracked");

        let error = state
            .track(spawn_long_running_child())
            .expect_err("second backend should be rejected");
        assert!(error.contains("已经启动"));
        assert!(state.stop());
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn stops_macos_backend_process_group_including_children() {
        let state = BackendState::new();
        let (child, grandchild) = spawn_process_group_with_child();
        let backend_pid = child.id();
        assert!(pid_is_alive(grandchild), "grandchild should start");
        state
            .track(child)
            .expect("backend process group should be tracked");

        assert!(state.stop());
        let deadline = Instant::now() + Duration::from_secs(3);
        while pid_is_alive(grandchild) && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(25));
        }
        assert!(
            !pid_is_alive(backend_pid),
            "backend process group leader should exit"
        );
        assert!(
            !pid_is_alive(grandchild),
            "backend process group child should exit"
        );
        assert!(!state.stop());
    }
}
