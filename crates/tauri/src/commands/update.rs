use std::cmp::Ordering;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering as AtomicOrder};

use tauri::Emitter;

pub(crate) const RELEASE_API: &str =
    "https://api.github.com/repos/Zomcxj/MemoPaws/releases/latest";
pub(crate) const USER_AGENT: &str = concat!("MemoPaws/", env!("CARGO_PKG_VERSION"));

/// 发布页解析结果：版本号与两类资产的 (url, size)。资产缺失时为 None，
/// 允许只提供其一。
#[derive(Debug, PartialEq)]
pub(crate) struct LatestRelease {
    pub version: String,
    pub installer: Option<(String, u64)>,
    pub offline: Option<(String, u64)>,
}

/// 按点分数字段比较版本（"0.0.10" > "0.0.9"），忽略可选的 v 前缀。
/// 缺失字段按 0 处理；任一段非数字（含预发布后缀、超范围整数）时整串视为无法比较，
/// 按相等处理——宁可漏报升级也不误报。
pub(crate) fn compare_versions(current: &str, latest: &str) -> Ordering {
    fn segments(value: &str) -> Option<Vec<u64>> {
        value
            .trim()
            .trim_start_matches('v')
            .split('.')
            .map(|part| part.trim().parse().ok())
            .collect()
    }
    // 出现非数字字段时无法判断大小，按相等处理以免误报升级。
    let (Some(current), Some(latest)) = (segments(current), segments(latest)) else {
        return Ordering::Equal;
    };
    let width = current.len().max(latest.len());
    for index in 0..width {
        let left = current.get(index).copied().unwrap_or(0);
        let right = latest.get(index).copied().unwrap_or(0);
        match left.cmp(&right) {
            Ordering::Equal => {}
            other => return other,
        }
    }
    Ordering::Equal
}

/// 只接受 GitHub 发行页与其 CDN 域名的 https 下载地址。
pub(crate) fn safe_download_url(url: &str) -> bool {
    url.starts_with("https://github.com/")
        || url.starts_with("https://objects.githubusercontent.com/")
}

/// 替换正在运行的 exe：Windows 允许改名运行中的文件，先把当前 exe 改名为
/// `.bak` 再把新 exe 写到原路径。复制失败或写入字节数与源文件不符时回滚，
/// 避免应用变成不可运行。
pub(crate) fn replace_executable(current_exe: &Path, downloaded: &Path) -> std::io::Result<PathBuf> {
    let backup = backup_path(current_exe);
    std::fs::rename(current_exe, &backup)?;
    let installed = std::fs::copy(downloaded, current_exe).and_then(|copied| {
        let expected = std::fs::metadata(downloaded)?.len();
        if copied == expected {
            Ok(())
        } else {
            Err(std::io::Error::new(
                std::io::ErrorKind::UnexpectedEof,
                format!("复制字节数不符：写入 {copied} 字节，源文件 {expected} 字节"),
            ))
        }
    });
    match installed {
        Ok(()) => Ok(backup),
        Err(error) => Err(rollback(&backup, current_exe, error)),
    }
}

/// 把 `.bak` 改名回原位，回滚本身也失败时两个错误一起带出去。没有 logging 依赖，
/// 错误字符串是唯一通道：丢掉回滚错误会让调用方把"半个新 exe 挡在原位、旧程序躺在
/// `.bak` 里"误报成下载失败，用户重试多少次都是坏的。
fn rollback(backup: &Path, current_exe: &Path, error: std::io::Error) -> std::io::Error {
    match std::fs::rename(backup, current_exe) {
        Ok(()) => error,
        Err(rollback_error) => std::io::Error::new(
            error.kind(),
            format!(
                "替换失败且回滚失败，旧程序在 {}：{rollback_error}",
                backup.display()
            ),
        ),
    }
}

/// 上次更新遗留的 .bak 必须在启动时清掉，否则磁盘上永远留一份旧程序。
///
/// 只能在**下一个进程**里调用：`.bak` 是上一个进程正在运行的映像，进程存活期间
/// Windows 拒绝删除它（实测 AccessDenied），而下面的 `let _ =` 会让这个失败永久
/// 静默，磁盘上就永远留一份旧程序。
pub(crate) fn remove_stale_backup(current_exe: &Path) {
    let backup = backup_path(current_exe);
    if backup.exists() {
        let _ = std::fs::remove_file(backup);
    }
}

fn backup_path(current_exe: &Path) -> PathBuf {
    current_exe.with_extension("exe.bak")
}

pub(crate) fn parse_latest_release(body: &str) -> Option<LatestRelease> {
    let value: serde_json::Value = serde_json::from_str(body).ok()?;
    let tag = value.get("tag_name")?.as_str()?;
    let mut installer = None;
    let mut offline = None;
    if let Some(assets) = value.get("assets").and_then(|value| value.as_array()) {
        for asset in assets {
            let name = asset.get("name").and_then(|value| value.as_str()).unwrap_or_default();
            let Some(url) = asset.get("browser_download_url").and_then(|value| value.as_str()) else { continue };
            if !safe_download_url(url) {
                continue;
            }
            let size = asset.get("size").and_then(|value| value.as_u64()).unwrap_or(0);
            if name.ends_with("-setup.exe") {
                installer = Some((url.to_string(), size));
            } else if name.ends_with("_x64.exe") {
                offline = Some((url.to_string(), size));
            }
        }
    }
    Some(LatestRelease {
        version: tag.trim().trim_start_matches('v').to_string(),
        installer,
        offline,
    })
}

pub(crate) const POLL_INTERVAL: std::time::Duration = std::time::Duration::from_secs(3600);
pub(crate) const FIRST_CHECK_DELAY: std::time::Duration = std::time::Duration::from_secs(15);

/// 直连优先，失败再走系统代理。开发者环境里 GitHub 常需代理，
/// 但直连成功时不应多绕一跳。reqwest 默认自动读取环境变量与 Windows
/// 注册表中的系统代理（system-proxy feature），所以代理 client 就是默认构造。
///
/// API 检查与文件下载必须分开设超时：reqwest 的 client 级 `timeout` 覆盖
/// "从建连到响应体读完"全程，29MB 离线包走 20s 总超时需要 ≥12Mbps，慢速用户的
/// 应用内更新会永远失败。所以：
/// - API 路径传 `Some(20s)`——JSON 只有几 KB，20s 足够；
/// - 下载路径传 `None`——不设总超时，只靠 connect_timeout(20s) 挡死连接。
///   不设 3600s 兜底是因为真正的 56kbps 边缘用户下 29MB 要 70 分钟；下载线程
///   卡在 read 上时 TCP 重传/保活最终会报错释放线程，代价只是 DOWNLOADING 互斥
///   多占一会儿，可接受。
fn client(proxy: bool, total_timeout: Option<std::time::Duration>) -> Option<reqwest::blocking::Client> {
    let builder = reqwest::blocking::Client::builder()
        .user_agent(USER_AGENT)
        .connect_timeout(std::time::Duration::from_secs(20));
    let builder = match total_timeout {
        Some(timeout) => builder.timeout(timeout),
        None => builder,
    };
    let builder = if proxy { builder } else { builder.no_proxy() };
    builder.build().ok()
}

fn fetch_response(url: &str, total_timeout: Option<std::time::Duration>) -> Option<reqwest::blocking::Response> {
    for proxy in [false, true] {
        let Some(client) = client(proxy, total_timeout) else { continue };
        let Ok(response) = client
            .get(url)
            .header("Accept", "application/vnd.github+json")
            .send()
        else {
            continue;
        };
        // 只有传输层失败才值得换出口重试；服务器已经答复（4xx/5xx）时换代理
        // 只会重复同一个答案并白等一个超时。
        return response.status().is_success().then_some(response);
    }
    None
}

fn fetch_latest_release() -> Option<LatestRelease> {
    parse_latest_release(&fetch_response(RELEASE_API, Some(std::time::Duration::from_secs(20)))?.text().ok()?)
}

/// latest 比 current 新时返回 latest，否则 None。调用方传进来的 latest 应是已剥掉
/// v 前缀的版本号（parse_latest_release 的输出），本函数原样返回。
/// 版本号无法比较时返回 None：宁可漏报也不误报升级。
pub(crate) fn newer_version(current: &str, latest: &str) -> Option<String> {
    (compare_versions(current, latest) == Ordering::Less).then(|| latest.to_string())
}

/// 后台轮询：新版本比当前版本新时向窗口推一次事件。窗口关到托盘时前端不运行，
/// 所以轮询必须在后端。
pub(crate) fn spawn_update_poller(app: tauri::AppHandle) {
    std::thread::spawn(move || {
        if let Ok(current_exe) = std::env::current_exe() {
            remove_stale_backup(&current_exe);
        }
        std::thread::sleep(FIRST_CHECK_DELAY);
        let mut notified: Option<String> = None;
        loop {
            if let Some(release) = fetch_latest_release() {
                let current_version = app.package_info().version.to_string();
                if let Some(version) = newer_version(&current_version, &release.version) {
                    if notified.as_deref() != Some(version.as_str()) {
                        notified = Some(version.clone());
                        let _ = app.emit(
                            "update-available",
                            serde_json::json!({
                                "version": version,
                                "currentVersion": current_version,
                            }),
                        );
                    }
                }
            }
            std::thread::sleep(POLL_INTERVAL);
        }
    });
}

/// 供前端主动拉取：轮询事件可能在监听器注册前就被丢弃，挂载时必须能问一次。
/// 返回 None 表示检查失败（无网络、被限流、仓库不可访问）或没有新版本，前端静默即可。
///
/// `async` 是必需的：函数体是同步 HTTP（直连失败再走代理，两个 20s 超时），而 Tauri 的
/// 同步 command 直接跑在 WebView2 的 IPC 协议线程上，也就是 UI 线程——GitHub 不通时
/// 窗口会无响应约 40s。宏属性把整个函数体丢进 async_runtime，不再占住 UI 线程。
/// 函数体保持同步 `fn`：里面用的是 reqwest blocking client，改 `async fn` 反而要重写
/// 整个网络层（blocking client 在 async 上下文里只是阻塞一个 worker，不会 panic）。
#[tauri::command(async)]
pub fn latest_release_version(app: tauri::AppHandle) -> Option<String> {
    let release = fetch_latest_release()?;
    let current_version = app.package_info().version.to_string();
    newer_version(&current_version, &release.version)
}

/// 下载临时目录：每次落盘前清空，避免失败残留占磁盘。
fn download_dir() -> std::io::Result<PathBuf> {
    let dir = std::env::temp_dir().join("memopaws-update");
    if dir.exists() {
        let _ = std::fs::remove_dir_all(&dir);
    }
    std::fs::create_dir_all(&dir)?;
    Ok(dir)
}

/// 下载互斥。临时目录是固定路径且落盘前清空，两个下载并发就会互删对方的 setup.exe：
/// Windows 拒绝删除正在运行的映像，删除失败被吞掉后目录没清，后一个再写同名文件就撞上
/// 运行中映像报 AccessDenied——用户看到"更新失败"，而第一次其实已经装好了。
/// 命令层必须自己挡：devtools invoke、快捷键、渲染竞态都能绕过前端的按钮禁用。
static DOWNLOADING: AtomicBool = AtomicBool::new(false);

/// 抢到互斥才允许开线程。Drop 放行，下载失败/线程 panic 都不会把更新永久锁死。
struct DownloadGuard;

impl DownloadGuard {
    fn acquire() -> Option<Self> {
        DOWNLOADING
            .compare_exchange(false, true, AtomicOrder::AcqRel, AtomicOrder::Acquire)
            .ok()
            .map(|_| Self)
    }
}

impl Drop for DownloadGuard {
    fn drop(&mut self) {
        DOWNLOADING.store(false, AtomicOrder::Release);
    }
}

#[tauri::command]
pub fn download_update(app: tauri::AppHandle, kind: String) -> Result<(), String> {
    match kind.as_str() {
        "installer" | "offline" => {}
        other => return Err(format!("未知的下载类型: {other}")),
    }
    let Some(guard) = DownloadGuard::acquire() else {
        return Err("已有更新正在下载，请稍候".to_string());
    };
    // 下载 8-30MB 不能占住命令线程，交给独立线程，进度用事件回报。
    std::thread::spawn(move || run_download(app, &kind, guard));
    Ok(())
}

fn run_download(app: tauri::AppHandle, kind: &str, _guard: DownloadGuard) {
    let result = download_and_apply(&app, kind);
    if let Err(message) = result {
        let _ = app.emit("update-download-error", serde_json::json!({ "message": message }));
    }
}

fn download_and_apply(app: &tauri::AppHandle, kind: &str) -> Result<(), String> {
    let release = fetch_latest_release().ok_or("无法获取最新版本信息")?;
    let (url, expected_size) = match kind {
        "installer" => release.installer.ok_or("该版本没有安装包")?,
        _ => release.offline.ok_or("该版本没有离线包")?,
    };
    if !safe_download_url(&url) {
        return Err("下载地址不受信任".to_string());
    }
    let bytes = download_with_progress(app, &url, expected_size)?;
    // rsplit 在 URL 以 / 结尾时给出空串而不是 None，空名字会拼成目录本身（"Is a directory"）。
    let file_name = url
        .rsplit('/')
        .find(|part| !part.is_empty())
        .unwrap_or("update.exe");
    let target = download_dir().map_err(|error| error.to_string())?.join(file_name);
    std::fs::write(&target, &bytes).map_err(|error| error.to_string())?;
    match kind {
        "installer" => run_installer(app, &target),
        _ => apply_offline(app, &target),
    }
}

/// 进度事件的节流间隔（毫秒）。按时间而非字节节流：快网下 256KB 一跳显得卡顿，
/// 100ms 一帧就是肉眼流畅的实时进度；慢网下 64KB 读块本来就远小于 256KB，
/// 按字节节流可能几十秒才跳一格。
const PROGRESS_INTERVAL_MS: u128 = 100;

/// 该不该上报进度。抽成纯函数是为了能离线测：网络读循环里的判断没法在测试里驱动。
///
/// - `total == 0`（既没有 Content-Length 也没有 API 的 size）一律不上报：字节阈值
///   失效后 `received > last_reported` 恒真会把节流完全短路，而且 payload 的
///   `total: 0` 会让前端算出 NaN、永远等不到 100%。完成信号由末尾的 `update-ready` 承担。
/// - 其余情况：距上次上报满 `PROGRESS_INTERVAL_MS` 且有新字节就报一次；
///   已读满 `total` 时无条件补报，保证末尾一定有一条 100%。
fn progress_event(total: u64, received: u64, last_reported: u64, elapsed_ms: u128) -> Option<(u64, u64)> {
    if total == 0 {
        return None;
    }
    let due = elapsed_ms >= PROGRESS_INTERVAL_MS && received > last_reported;
    (due || received >= total).then_some((received, total))
}

fn download_with_progress(
    app: &tauri::AppHandle,
    url: &str,
    expected_size: u64,
) -> Result<Vec<u8>, String> {
    // blocking 的 Response 没有 chunk()（那是 async 的 API），它实现的是 std::io::Read。
    // 下载 client 不设总超时（理由见 client 的注释），只靠 connect_timeout 挡死连接。
    let mut response = fetch_response(url, None).ok_or("下载请求失败")?;
    let total = response.content_length().unwrap_or(expected_size);
    let mut bytes: Vec<u8> = Vec::with_capacity(total.min(64 * 1024 * 1024) as usize);
    let mut buffer = [0u8; 64 * 1024];
    let mut last_reported = 0u64;
    let mut last_emit = std::time::Instant::now();
    loop {
        let read = response
            .read(&mut buffer)
            .map_err(|error| error.to_string())?;
        if read == 0 {
            break;
        }
        bytes.extend_from_slice(&buffer[..read]);
        if let Some((received, total)) =
            progress_event(total, bytes.len() as u64, last_reported, last_emit.elapsed().as_millis())
        {
            last_reported = received;
            last_emit = std::time::Instant::now();
            let _ = app.emit(
                "update-download-progress",
                serde_json::json!({ "received": received, "total": total }),
            );
        }
    }
    // with_capacity 只封顶预分配，extend_from_slice 是无条件追加：错配的 CDN 端点能在
    // 20 秒内灌进几百 MB 直到 OOM。总量已知时直接拒收超量数据（不另设上限体系）。
    if total > 0 && bytes.len() as u64 > total {
        return Err(format!("下载字节数超出预期: {} / {} 字节", bytes.len(), total));
    }
    if expected_size > 0 && bytes.len() as u64 != expected_size {
        return Err(format!("下载不完整: {} / {} 字节", bytes.len(), expected_size));
    }
    Ok(bytes)
}

/// 安装包：NSIS 静默安装（/S）。安装器必须能覆写 memopaws.exe，所以当前进程
/// 必须在安装器完成前退出——先启动安装器再退出。
/// （app.exit(0) 会结束本进程，因此不能像离线包那样"等安装完再自己启动"。）
///
/// 以下事实取证自本仓库自己生成的安装器脚本 `target/release/nsis/x64/installer.nsi`，
/// 改动这里之前请先读它，不要靠推测：
///
/// 1. 脚本里没有任何拉起主程序的 `Exec`（只有卸载器与 WebView2 的 `ExecWait`），
///    所以 `/S` 静默装完**不会**自动拉起新版程序。
/// 2. `installer.nsi:635` 插入的 `CheckIfAppIsRunning` 在静默模式下
///    （`utils.nsh:40` 的 `IfSilent kill_${UniqueID} 0`）会直接 KillProcess 掉
///    memopaws.exe，不必等弹窗确认。因此本进程**立即 exit(0) 是正确且更快的**：
///    早退只是把"被杀"提前，装完结果一样。
/// 3. 自动拉起新版是待办。真要做时注意卸载项的键是 `...\Uninstall\MemoPaws`
///    （`installer.nsi:60`，`UNINSTKEY` 用的是 `${PRODUCTNAME}`，不是 BUNDLEID），
///    且 `installer.nsi:675` 写入的 `InstallLocation` 值自带一对引号
///    （`"$\"$INSTDIR$\""`），必须先剥掉再拼 `memopaws.exe`，然后轮询等新 exe 出现再 spawn。
fn run_installer(app: &tauri::AppHandle, setup: &Path) -> Result<(), String> {
    let spawned = std::process::Command::new(setup)
        .arg("/S")
        .spawn()
        .map_err(|error| format!("无法启动安装程序: {error}"));
    match spawned {
        Ok(_) => {
            // 见上方第 2 条：安装器自己会杀本进程，这里立即退出即可。
            app.exit(0);
            Ok(())
        }
        // 启动失败时不能退出，否则用户连旧版本都用不了。
        Err(error) => Err(error.to_string()),
    }
}

/// 离线包：替换 exe 后由前端调用既有 restart_app 完成切换。
/// 错误文本取 io::Error 的完整 Display——回滚失败时它带着"旧程序在 <路径>"，
/// 只取 ErrorKind 会让用户看到毫不相干的"磁盘空间不足"。
fn apply_offline(app: &tauri::AppHandle, downloaded: &Path) -> Result<(), String> {
    let current_exe = std::env::current_exe().map_err(|error| error.to_string())?;
    replace_executable(&current_exe, downloaded)
        .map_err(|error| format!("替换程序文件失败: {error}"))?;
    let _ = app.emit("update-ready", serde_json::json!({}));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compare_versions_orders_numerically_per_segment() {
        assert_eq!(compare_versions("0.0.3", "0.0.4"), Ordering::Less);
        assert_eq!(compare_versions("0.0.3", "0.0.3"), Ordering::Equal);
        assert_eq!(compare_versions("0.1.0", "0.0.9"), Ordering::Greater);
        assert_eq!(compare_versions("0.0.9", "0.0.10"), Ordering::Less);
    }

    #[test]
    fn compare_versions_tolerates_prefix_and_missing_segments() {
        assert_eq!(compare_versions("0.0.3", "v0.0.4"), Ordering::Less);
        assert_eq!(compare_versions("0.0.3", "v0.0.3"), Ordering::Equal);
        assert_eq!(compare_versions("0.0", "0.0.1"), Ordering::Less);
        assert_eq!(compare_versions("0.0.3", "0.0.x"), Ordering::Equal);
    }

    const SAMPLE: &str = r#"{
        "tag_name": "v0.0.4",
        "assets": [
            { "name": "MemoPaws_0.0.4_x64-setup.exe", "browser_download_url": "https://github.com/Zomcxj/MemoPaws/releases/download/v0.0.4/MemoPaws_0.0.4_x64-setup.exe", "size": 8281957 },
            { "name": "MemoPaws_0.0.4_x64.exe", "browser_download_url": "https://github.com/Zomcxj/MemoPaws/releases/download/v0.0.4/MemoPaws_0.0.4_x64.exe", "size": 29167616 },
            { "name": "sources.zip", "browser_download_url": "https://codeload.github.com/x/sources.zip", "size": 1 }
        ]
    }"#;

    #[test]
    fn parse_latest_release_reads_tag_and_splits_assets_by_name() {
        let parsed = parse_latest_release(SAMPLE).expect("sample must parse");
        assert_eq!(parsed.version, "0.0.4");
        assert_eq!(
            parsed.installer,
            Some(("https://github.com/Zomcxj/MemoPaws/releases/download/v0.0.4/MemoPaws_0.0.4_x64-setup.exe".to_string(), 8281957))
        );
        assert_eq!(
            parsed.offline,
            Some(("https://github.com/Zomcxj/MemoPaws/releases/download/v0.0.4/MemoPaws_0.0.4_x64.exe".to_string(), 29167616))
        );
    }

    #[test]
    fn parse_latest_release_rejects_untrusted_urls_and_bad_json() {
        let hostile = r#"{"tag_name":"v9.9.9","assets":[{"name":"x_x64.exe","browser_download_url":"https://evil.example/x_x64.exe","size":1}]}"#;
        let parsed = parse_latest_release(hostile).expect("json must parse");
        assert!(parsed.offline.is_none(), "非 GitHub 域名的资产必须被丢弃");

        let no_assets = r#"{"tag_name":"v0.0.4"}"#;
        assert_eq!(parse_latest_release(no_assets).unwrap().installer, None);

        assert!(parse_latest_release("not json").is_none());
        assert!(parse_latest_release("{}").is_none());
    }

    #[test]
    fn safe_download_url_only_allows_github_hosts() {
        assert!(safe_download_url("https://github.com/a/b_x64.exe"));
        assert!(safe_download_url("https://objects.githubusercontent.com/x"));
        assert!(!safe_download_url("http://github.com/a"));
        assert!(!safe_download_url("https://github.com.evil.test/a"));
        assert!(!safe_download_url("https://evil.test/github.com/a"));
        // 尾斜杠挡住 userinfo 绕过与后缀欺骗，删掉尾斜杠这两条会挂。
        assert!(!safe_download_url("https://github.com@evil.test/a"));
        assert!(!safe_download_url("https://github.com.evil.test"));
        // 路径段里的 @ 不是 userinfo，主机确实是 github.com
        assert!(safe_download_url("https://github.com/@evil.test/"));
        // GitHub 永不返回大写 URL，大小写敏感是刻意的 fail-closed
        assert!(!safe_download_url("HTTPS://GITHUB.COM/a"));
    }

    #[test]
    fn newer_version_reports_only_a_strictly_newer_release() {
        // 原样返回入参：真实调用方传的是 parse_latest_release 已剥掉 v 前缀的版本号。
        assert_eq!(newer_version("0.0.9", "0.0.10"), Some("0.0.10".to_string()));
        assert_eq!(newer_version("0.0.9", "v0.0.10"), Some("v0.0.10".to_string()));
        assert_eq!(newer_version("0.0.10", "0.0.10"), None);
        assert_eq!(newer_version("0.0.10", "0.0.9"), None);
    }

    #[test]
    fn newer_version_refuses_to_guess_on_unparsable_versions() {
        assert_eq!(newer_version("0.0.10", "0.1.x"), None);
        assert_eq!(newer_version("nightly", "0.0.1"), None);
    }

    #[test]
    fn the_two_asset_kinds_are_selected_by_name() {
        let parsed = parse_latest_release(SAMPLE).expect("sample must parse");
        assert!(parsed.installer.as_ref().unwrap().0.ends_with("-setup.exe"));
        assert!(parsed.offline.as_ref().unwrap().0.ends_with("_x64.exe"));
        assert!(!parsed.offline.as_ref().unwrap().0.contains("-setup"));
    }

    fn temp_dir(tag: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "memopaws-update-test-{tag}-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn replace_executable_swaps_in_the_downloaded_binary() {
        use super::replace_executable;

        let dir = temp_dir("replace");
        let current = dir.join("memopaws.exe");
        let downloaded = dir.join("new.exe");
        std::fs::write(&current, b"old").unwrap();
        std::fs::write(&downloaded, b"new").unwrap();

        let backup = replace_executable(&current, &downloaded).unwrap();
        assert_eq!(backup, dir.join("memopaws.exe.bak"));
        assert_eq!(std::fs::read(&current).unwrap(), b"new");
        assert_eq!(std::fs::read(&backup).unwrap(), b"old");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn replace_executable_restores_the_old_binary_when_the_copy_fails() {
        use super::replace_executable;

        let dir = temp_dir("rollback");
        let current = dir.join("memopaws.exe");
        std::fs::write(&current, b"old").unwrap();

        let error = replace_executable(&current, &dir.join("missing.exe")).unwrap_err();
        assert!(error.kind() == std::io::ErrorKind::NotFound);
        assert_eq!(std::fs::read(&current).unwrap(), b"old", "复制失败必须把旧 exe 放回原位");
        // 回滚走的是 rename 而非 copy：备份名必须被搬空，不能留下第二份旧程序。
        assert!(!dir.join("memopaws.exe.bak").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// 按 64KB 分块喂一遍 progress_event，返回实际上报的 (received, total) 序列。
    /// 模拟 download_with_progress 的读循环，但不碰网络；每块之间经过的毫秒数
    /// 由 elapsed_ms 给出（默认每块都已满节流间隔，模拟慢速流）。
    fn drain_progress_timed(total: u64, chunk: u64, elapsed_ms: u128) -> Vec<(u64, u64)> {
        let mut events = Vec::new();
        let mut received = 0u64;
        let mut last_reported = 0u64;
        while received < total {
            received += chunk.min(total - received);
            if let Some(event) = progress_event(total, received, last_reported, elapsed_ms) {
                last_reported = received;
                events.push(event);
            }
        }
        events
    }

    fn drain_progress(total: u64, chunk: u64) -> Vec<(u64, u64)> {
        drain_progress_timed(total, chunk, PROGRESS_INTERVAL_MS)
    }

    #[test]
    fn progress_reports_every_chunk_once_the_interval_has_elapsed() {
        // 8MB 安装包按 64KB 读：128 块全部到点上报，末次 received == total
        let events = drain_progress(8 * 1024 * 1024, 64 * 1024);
        assert_eq!(events.len(), 128, "每 64KB 一报，不得合并");
        assert_eq!(events.last(), Some(&(8 * 1024 * 1024, 8 * 1024 * 1024)));
    }

    #[test]
    fn progress_reports_the_offline_package_stream_in_real_time() {
        // 29MB 离线包：445 个整块 + 4096 字节余块 = 446 次上报，末尾恰好报满
        let total = 29_167_616u64;
        let events = drain_progress(total, 64 * 1024);
        assert_eq!(events.len(), total.div_ceil(64 * 1024) as usize);
        assert_eq!(events.last(), Some(&(total, total)), "末尾必须报满");
    }

    #[test]
    fn progress_stays_quiet_between_intervals_and_reports_the_end_unconditionally() {
        // 读取快于节流间隔（elapsed < 100ms）时中间不上报，只有末尾 100% 必报
        let events = drain_progress_timed(300 * 1024, 64 * 1024, 0);
        assert_eq!(events, vec![(300 * 1024, 300 * 1024)]);
    }

    #[test]
    fn progress_reports_a_small_file_exactly_once() {
        // 100KB 小文件两个 64KB 块，到点即报：两次都发
        let events = drain_progress(100 * 1024, 64 * 1024);
        assert_eq!(events, vec![(64 * 1024, 100 * 1024), (100 * 1024, 100 * 1024)]);
    }

    #[test]
    fn progress_stays_silent_when_the_total_is_unknown() {
        // total == 0 时前端会算出 NaN，0/0 对 UI 没有信息量
        assert_eq!(progress_event(0, 0, 0, PROGRESS_INTERVAL_MS), None);
        assert_eq!(progress_event(0, 64 * 1024, 0, PROGRESS_INTERVAL_MS), None);
        assert_eq!(progress_event(0, u64::MAX, 0, PROGRESS_INTERVAL_MS), None);
        assert!(drain_progress(0, 64 * 1024).is_empty());
    }

    #[test]
    fn download_guard_blocks_a_second_download_until_the_first_releases_it() {
        let first = DownloadGuard::acquire().expect("首次下载必须拿到互斥");
        assert!(DownloadGuard::acquire().is_none(), "并发下载必须被挡在门外");
        drop(first);
        assert!(DownloadGuard::acquire().is_some(), "释放后必须能再次下载");
    }

    #[test]
    fn remove_stale_backup_deletes_a_previous_backup() {
        use super::remove_stale_backup;

        let dir = temp_dir("cleanup");
        let current = dir.join("memopaws.exe");
        std::fs::write(&current, b"new").unwrap();
        std::fs::write(dir.join("memopaws.exe.bak"), b"old").unwrap();

        remove_stale_backup(&current);
        assert!(!dir.join("memopaws.exe.bak").exists());
        assert!(current.exists());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
