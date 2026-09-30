use std::cmp::Ordering;

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
}
