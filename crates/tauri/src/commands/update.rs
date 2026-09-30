use std::cmp::Ordering;
use std::path::{Path, PathBuf};

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
fn client(proxy: bool) -> Option<reqwest::blocking::Client> {
    let builder = reqwest::blocking::Client::builder()
        .user_agent(USER_AGENT)
        .timeout(std::time::Duration::from_secs(20));
    let builder = if proxy { builder } else { builder.no_proxy() };
    builder.build().ok()
}

fn fetch_response(url: &str) -> Option<reqwest::blocking::Response> {
    for proxy in [false, true] {
        let Some(client) = client(proxy) else { continue };
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
    parse_latest_release(&fetch_response(RELEASE_API)?.text().ok()?)
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
                if compare_versions(&current_version, &release.version) == Ordering::Less
                    && notified.as_deref() != Some(release.version.as_str())
                {
                    notified = Some(release.version.clone());
                    let _ = app.emit(
                        "update-available",
                        serde_json::json!({
                            "version": release.version,
                            "currentVersion": current_version,
                        }),
                    );
                }
            }
            std::thread::sleep(POLL_INTERVAL);
        }
    });
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
