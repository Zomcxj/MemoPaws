use std::cmp::Ordering;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering as AtomicOrder};

use tauri::Emitter;

pub(crate) const RELEASE_API: &str =
    "https://api.github.com/repos/Zomcxj/MemoPaws/releases/latest";
pub(crate) const USER_AGENT: &str = concat!("MemoPaws/", env!("CARGO_PKG_VERSION"));

/// Parsed release page: the version plus (url, size) for two asset kinds. `None` when an asset is
/// missing; either one alone is allowed.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct LatestRelease {
    pub version: String,
    pub installer: Option<(String, u64)>,
    pub offline: Option<(String, u64)>,
}

/// Compares versions by dot-separated numeric fields ("0.0.10" > "0.0.9"), ignoring an optional `v`
/// prefix. Missing fields count as 0; if any field is non-numeric (prerelease suffix, out-of-range
/// integer) the whole string counts as incomparable and is handled as equal — better to miss an
/// upgrade than to report a false one.
pub(crate) fn compare_versions(current: &str, latest: &str) -> Ordering {
    fn segments(value: &str) -> Option<Vec<u64>> {
        value
            .trim()
            .trim_start_matches('v')
            .split('.')
            .map(|part| part.trim().parse().ok())
            .collect()
    }
    // A non-numeric field makes ordering undecidable; treat as equal to avoid false upgrade reports.
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

/// Accepts only https download URLs from GitHub release pages and their CDN domains.
pub(crate) fn safe_download_url(url: &str) -> bool {
    url.starts_with("https://github.com/")
        || url.starts_with("https://objects.githubusercontent.com/")
}

/// Replaces the running exe: Windows allows renaming a running file, so the current exe is renamed to
/// `.bak` first and the new exe is written to the original path. Rolls back when the copy fails or the
/// written byte count does not match the source, so the app never ends up unrunnable.
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

/// Renames `.bak` back to its original place; when the rollback itself fails, both errors are carried
/// along. There is no logging dependency and the error string is the only channel: dropping the
/// rollback error would let callers misreport "half of the new exe blocking the original path while
/// the old program sits in `.bak`" as a plain download failure, and every retry stays broken.
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

/// A `.bak` left behind by the previous update must be cleaned up at startup, otherwise an old copy of
/// the program stays on disk forever.
///
/// Must only be called from the **next process**: `.bak` is the image the previous process was running
/// from, and while that process is alive Windows refuses to delete it (observed AccessDenied); the
/// `let _ =` below would silence that failure forever, leaving an old copy on disk forever.
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

/// The starting exit is decided by the PREFER_PROXY sticky state (see fetch_response); on failure the
/// next one is tried. GitHub often needs a proxy in developer environments, but direct connections
/// should not pay an extra hop when they work. reqwest reads proxies from environment variables and
/// the Windows registry (system-proxy feature) by default, so the proxy client is the default build.
///
/// API checks and file downloads need separate timeouts: reqwest's client-level `timeout` covers
/// everything from connection setup to the end of the response body; a 29MB offline package over a
/// 20s total timeout requires ≥12Mbps, so in-app updates would fail forever for slow users.
/// Therefore:
/// - the API path passes `Some(20s)` — the JSON is a few KB, 20s is plenty;
/// - the download path passes `None` — no total timeout, only connect_timeout(20s) cuts dead
///   connections. No 3600s fallback because a real 56kbps edge user needs 70 minutes for 29MB; when
///   the download thread is stuck in read, TCP retransmission/keepalive eventually errors out and
///   releases the thread — the cost is only the DOWNLOADING mutex being held a bit longer, which is
///   acceptable.
fn client(exit: Exit, total_timeout: Option<std::time::Duration>) -> Option<reqwest::blocking::Client> {
    let mut builder = reqwest::blocking::Client::builder()
        .user_agent(USER_AGENT)
        .connect_timeout(std::time::Duration::from_secs(20));
    if let Some(timeout) = total_timeout {
        builder = builder.timeout(timeout);
    }
    builder = match exit {
        Exit::Direct => builder.no_proxy(),
        Exit::System => builder,
        Exit::Local(port) => match reqwest::Proxy::http(&format!("http://127.0.0.1:{port}")) {
            Ok(proxy) => builder.proxy(proxy),
            Err(_) => builder,
        },
    };
    builder.build().ok()
}

/// Network exits available to update requests.
#[derive(Clone, Copy, PartialEq, Debug)]
enum Exit {
    /// No proxy at all (reqwest no_proxy)
    Direct,
    /// System proxy (only applies when ProxyEnable is on in the registry; on real machines it is
    /// commonly off, in which case this equals Direct)
    System,
    /// HTTP proxy on a common local proxy port. System proxy off while Clash/v2rayN runs is the norm;
    /// probing the port proactively is more reliable than hoping the system proxy is on (a refused
    /// port fails in milliseconds, with no timeout cost)
    Local(u16),
}

/// Local HTTP proxy probe list: Clash 7890 / Clash Verge 7897 / v2rayN 10809
const LOCAL_PROXY_PORTS: [u16; 3] = [7890, 7897, 10809];
const EXIT_COUNT: usize = 2 + LOCAL_PROXY_PORTS.len();

/// Fixed exit order, tried in sequence per request: local proxy ports first (refused connections fail
/// in milliseconds, nearly zero cost), then direct, then the system proxy last (without a system
/// proxy enabled it equals direct and would waste a timeout, so it goes last).
const EXITS: [Exit; EXIT_COUNT] = [
    Exit::Local(7890),
    Exit::Local(7897),
    Exit::Local(10809),
    Exit::Direct,
    Exit::System,
];

fn fetch_response(url: &str, total_timeout: Option<std::time::Duration>) -> Option<reqwest::blocking::Response> {
    for exit in EXITS {
        let Some(client) = client(exit, total_timeout) else { continue };
        let Ok(response) = client
            .get(url)
            .header("Accept", "application/vnd.github+json")
            .send()
        else {
            continue;
        };
        if response.status().is_success() {
            return Some(response);
        }
        // Non-2xx: try the next exit. Different exits (direct hitting a blocked page / a rate-limited
        // proxy exit) give different answers; "the server answered, so it is final" only holds per exit.
    }
    None
}

/// The latest successful release fetch and its timestamp. Observed on a real machine: the card had
/// just shown the new version, but re-hitting the API on download ran into failure/rate limiting
/// (the 60 requests/hour quota of a shared proxy exit IP) and blocked the download for nothing.
/// Successful results are cached for 10 minutes and shared between download and manual checks; the
/// cost is that a manual check may see the old cache for up to 10 minutes after a new release, which
/// is acceptable.
fn fetch_latest_release() -> Option<LatestRelease> {
    const CACHE_TTL: std::time::Duration = std::time::Duration::from_secs(600);
    static CACHE: std::sync::Mutex<Option<(std::time::Instant, LatestRelease)>> =
        std::sync::Mutex::new(None);
    if let Ok(guard) = CACHE.lock() {
        if let Some((fetched_at, release)) = guard.as_ref() {
            if fetched_at.elapsed() < CACHE_TTL {
                return Some(release.clone());
            }
        }
    }
    let release =
        parse_latest_release(&fetch_response(RELEASE_API, Some(std::time::Duration::from_secs(20)))?.text().ok()?)?;
    if let Ok(mut guard) = CACHE.lock() {
        *guard = Some((std::time::Instant::now(), release.clone()));
    }
    Some(release)
}

/// Returns latest when it is newer than current, otherwise None. The caller passes latest already
/// stripped of the v prefix (parse_latest_release output) and this returns it as-is.
/// Returns None when versions cannot be compared: better to miss an upgrade than to misreport one.
pub(crate) fn newer_version(current: &str, latest: &str) -> Option<String> {
    (compare_versions(current, latest) == Ordering::Less).then(|| latest.to_string())
}

/// Background polling: pushes one event to the window when a newer version exists. The frontend does
/// not run while the window is closed to tray, so polling must happen in the backend.
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

/// Check result for manual/mount queries. Mirrors the reference implementation's (agent2api
/// update-panel) UpdateInfo: the detected latest version is returned as-is even when it is not newer
/// than current — otherwise the frontend has nothing to show for "already on the latest version
/// (x.y.z)" and could only say a vague "no new version found".
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateCheck {
    /// Latest release version of the GitHub repo; None when the repo has no releases
    pub latest_version: Option<String>,
    pub current_version: String,
    pub has_update: bool,
}

/// For the frontend to pull actively: poll events can be dropped before a listener registers, so the
/// mount must be able to ask once. `Ok(_)` means "checked"; check failures (no network, rate-limited,
/// repo unreachable) come back as `Err` — callers must be able to tell the two apart, otherwise a
/// manual check would falsely report "no new version found" while the card is already showing one
/// (hit on a real machine).
///
/// `async` is required: the body is synchronous HTTP (direct first, then proxy, two 20s timeouts), and
/// Tauri's synchronous commands run directly on WebView2's IPC handler thread — the UI thread — so an
/// unreachable GitHub would freeze the window for ~40s. The macro attribute moves the whole body onto
/// async_runtime instead of the UI thread. The body stays a synchronous `fn`: it uses reqwest's
/// blocking client; converting to `async fn` would mean rewriting the whole network layer (a blocking
/// client in an async context just parks one worker, it does not panic).
#[tauri::command(async)]
pub fn latest_release_version(app: tauri::AppHandle) -> Result<UpdateCheck, String> {
    let release = fetch_latest_release().ok_or_else(|| "检查更新失败，请稍后再试".to_string())?;
    let current_version = app.package_info().version.to_string();
    let has_update = newer_version(&current_version, &release.version).is_some();
    Ok(UpdateCheck {
        latest_version: Some(release.version),
        current_version,
        has_update,
    })
}

/// Download temp directory: emptied before every write so failed leftovers do not pile up on disk.
fn download_dir() -> std::io::Result<PathBuf> {
    let dir = std::env::temp_dir().join("memopaws-update");
    if dir.exists() {
        let _ = std::fs::remove_dir_all(&dir);
    }
    std::fs::create_dir_all(&dir)?;
    Ok(dir)
}

/// Download mutex. The temp dir is a fixed path emptied before each write, so two concurrent
/// downloads would delete each other's setup.exe: Windows refuses to delete a running image, the
/// swallowed deletion failure leaves the dir uncleaned, and the next download writing the same name
/// hits the running image with AccessDenied — the user sees "update failed" although the first one
/// actually installed. The command layer must guard this itself: devtools invoke, shortcuts and
/// render races all bypass the frontend's button disabling.
static DOWNLOADING: AtomicBool = AtomicBool::new(false);

/// The thread may only start after acquiring the mutex. Drop releases it; download failure or a
/// thread panic never permanently locks updates.
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
    // An 8-30MB download must not occupy the command thread; run it on a dedicated thread and report progress via events.
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
    // rsplit yields empty strings (not None) when the URL ends with /; an empty name would join into the directory itself ("Is a directory").
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

/// Progress event throttle interval (milliseconds). Throttled by time, not bytes: on fast connections
/// a 256KB jump feels choppy, and 100ms frames look like smooth real-time progress; on slow ones the
/// 64KB read blocks are far below 256KB anyway, so byte throttling could jump once every tens of
/// seconds.
const PROGRESS_INTERVAL_MS: u128 = 100;

/// Whether progress should be reported. Extracted as a pure function so it can be tested offline: the
/// checks inside the network read loop cannot be driven from tests.
///
/// - `total == 0` (no Content-Length and no API size) never reports: with the byte threshold broken,
///   `received > last_reported` is always true and would bypass throttling entirely, and a payload
///   `total: 0` makes the frontend compute NaN and never reach 100%. The trailing `update-ready`
///   event carries the completion signal.
/// - Otherwise: report when `PROGRESS_INTERVAL_MS` has elapsed since the last report and there are
///   new bytes; when `total` has been read, report unconditionally so the stream always ends at 100%.
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
    // blocking Response has no chunk() (that is the async API); it implements std::io::Read.
    // The download client has no total timeout (see the client() comment); only connect_timeout cuts dead connections.
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
    // with_capacity only caps the preallocation; extend_from_slice appends unconditionally: a
    // mismatched CDN endpoint could push hundreds of MB in 20 seconds until OOM. When the total is
    // known, oversized data is rejected outright (no separate limit system).
    if total > 0 && bytes.len() as u64 > total {
        return Err(format!("下载字节数超出预期: {} / {} 字节", bytes.len(), total));
    }
    if expected_size > 0 && bytes.len() as u64 != expected_size {
        return Err(format!("下载不完整: {} / {} 字节", bytes.len(), expected_size));
    }
    Ok(bytes)
}

/// Installer package: NSIS silent install (/S). The installer must be able to overwrite memopaws.exe,
/// so the current process must exit before the installer finishes — start the installer, then exit.
/// (app.exit(0) ends this process, so unlike the offline package we cannot "wait for the install and
/// then start it ourselves".)
///
/// The facts below are taken from this repo's own generated installer script
/// `target/release/nsis/x64/installer.nsi`; read it before changing anything here, do not guess:
///
/// 1. The script has no `Exec` that launches the main program (only the uninstaller and WebView2 use
///    `ExecWait`), so a `/S` silent install does **not** auto-start the new version.
/// 2. `CheckIfAppIsRunning`, inserted at `installer.nsi:635`, in silent mode
///    (`utils.nsh:40`'s `IfSilent kill_${UniqueID} 0`) KillProcesses memopaws.exe directly without
///    waiting for a dialog. Therefore exiting this process **immediately via exit(0) is correct and
///    faster**: exiting early just moves the "being killed" moment up; the install result is the same.
/// 3. Auto-starting the new version is a TODO. If it is ever done, note the uninstall registry key is
///    `...\Uninstall\MemoPaws` (`installer.nsi:60`; `UNINSTKEY` uses `${PRODUCTNAME}`, not
///    BUNDLEID), and the `InstallLocation` value written at `installer.nsi:675` comes wrapped in a
///    pair of quotes (`"$\"$INSTDIR$\""`), which must be stripped before joining `memopaws.exe`; then
///    poll for the new exe to appear before spawning it.
fn run_installer(app: &tauri::AppHandle, setup: &Path) -> Result<(), String> {
    let spawned = std::process::Command::new(setup)
        .arg("/S")
        .spawn()
        .map_err(|error| format!("无法启动安装程序: {error}"));
    match spawned {
        Ok(_) => {
            // See fact 2 above: the installer kills this process itself, so exiting here is fine.
            app.exit(0);
            Ok(())
        }
        // Do not exit when spawning fails, otherwise the user loses even the old version.
        Err(error) => Err(error.to_string()),
    }
}

/// Offline package: after replacing the exe the frontend calls the existing restart_app to finish the
/// switch. The error text uses io::Error's full Display — when the rollback fails it carries "old
/// program at <path>"; taking only ErrorKind would show users an unrelated "disk full".
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
        // The trailing slash blocks userinfo bypass and suffix spoofing; removing the slash breaks these two.
        assert!(!safe_download_url("https://github.com@evil.test/a"));
        assert!(!safe_download_url("https://github.com.evil.test"));
        // The @ inside a path segment is not userinfo; the host really is github.com
        assert!(safe_download_url("https://github.com/@evil.test/"));
        // GitHub never returns uppercase URLs; case sensitivity is deliberate fail-closed
        assert!(!safe_download_url("HTTPS://GITHUB.COM/a"));
    }

    #[test]
    fn newer_version_reports_only_a_strictly_newer_release() {
        // Returns the input as-is: the real caller passes versions already stripped of the v prefix by parse_latest_release.
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
        // Rollback uses rename, not copy: the backup name must be moved away, never leaving a second old copy.
        assert!(!dir.join("memopaws.exe.bak").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// Feeds progress_event in 64KB chunks and returns the (received, total) sequence actually reported.
    /// Simulates download_with_progress's read loop without touching the network; the milliseconds
    /// elapsed between chunks are given by elapsed_ms (defaults to a full throttle interval per chunk,
    /// simulating a slow stream).
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
        // 8MB installer read in 64KB chunks: all 128 chunks report on time, last received == total
        let events = drain_progress(8 * 1024 * 1024, 64 * 1024);
        assert_eq!(events.len(), 128, "每 64KB 一报，不得合并");
        assert_eq!(events.last(), Some(&(8 * 1024 * 1024, 8 * 1024 * 1024)));
    }

    #[test]
    fn progress_reports_the_offline_package_stream_in_real_time() {
        // 29MB offline package: 445 full chunks + a 4096-byte remainder = 446 reports, ending exactly at total
        let total = 29_167_616u64;
        let events = drain_progress(total, 64 * 1024);
        assert_eq!(events.len(), total.div_ceil(64 * 1024) as usize);
        assert_eq!(events.last(), Some(&(total, total)), "末尾必须报满");
    }

    #[test]
    fn progress_stays_quiet_between_intervals_and_reports_the_end_unconditionally() {
        // Reads faster than the throttle interval (elapsed < 100ms) skip interim reports; only the trailing 100% is mandatory
        let events = drain_progress_timed(300 * 1024, 64 * 1024, 0);
        assert_eq!(events, vec![(300 * 1024, 300 * 1024)]);
    }

    #[test]
    fn progress_reports_a_small_file_exactly_once() {
        // A 100KB file is two 64KB chunks, both due on time: both are sent
        let events = drain_progress(100 * 1024, 64 * 1024);
        assert_eq!(events, vec![(64 * 1024, 100 * 1024), (100 * 1024, 100 * 1024)]);
    }

    #[test]
    fn progress_stays_silent_when_the_total_is_unknown() {
        // With total == 0 the frontend would compute NaN; 0/0 carries no information for the UI
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
