use std::sync::OnceLock;

use pulldown_cmark::{html, CodeBlockKind, CowStr, Event, Options, Parser, Tag, TagEnd};
use serde::Deserialize;
use syntect::highlighting::ThemeSet;
use syntect::html::highlighted_html_for_string;
use syntect::parsing::SyntaxSet;

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RenderTheme {
    Dark,
    Light,
}

#[derive(Clone, Copy, PartialEq)]
enum SkipKind {
    Link,
    Image,
}

impl SkipKind {
    fn of_start(event: &Event) -> Self {
        match event {
            Event::Start(Tag::Link { .. }) => SkipKind::Link,
            _ => SkipKind::Image,
        }
    }
    fn of_end(event: &Event) -> Self {
        match event {
            Event::End(TagEnd::Link) => SkipKind::Link,
            _ => SkipKind::Image,
        }
    }
}

pub fn render_markdown(markdown: &str, theme: RenderTheme) -> String {
    let options = Options::ENABLE_TABLES
        | Options::ENABLE_STRIKETHROUGH
        | Options::ENABLE_TASKLISTS
        | Options::ENABLE_FOOTNOTES;
    let mut output = Vec::new();
    let mut events = Parser::new_ext(markdown, options);
    let mut skipped: Vec<SkipKind> = Vec::new();
    while let Some(event) = events.next() {
        if let Some(&skipping) = skipped.last() {
            match event {
                Event::Start(Tag::Link { .. }) | Event::Start(Tag::Image { .. }) => {
                    skipped.push(SkipKind::of_start(&event));
                }
                Event::End(TagEnd::Link) | Event::End(TagEnd::Image)
                    if SkipKind::of_end(&event) == skipping =>
                {
                    skipped.pop();
                }
                _ => {}
            }
            continue;
        }
        match event {
            Event::Start(Tag::CodeBlock(CodeBlockKind::Fenced(language))) => {
                let mut code = String::new();
                for code_event in events.by_ref() {
                    match code_event {
                        Event::Text(text) | Event::Code(text) => code.push_str(&text),
                        Event::End(TagEnd::CodeBlock) => break,
                        _ => {}
                    }
                }
                let language = normalize_language_token(&language);
                output.push(Event::Html(CowStr::Boxed(
                    highlight_code(&code, &language, theme).into_boxed_str(),
                )));
            }
            Event::Html(raw) | Event::InlineHtml(raw) => {
                output.push(Event::Html(CowStr::Boxed(escape_html(&raw).into_boxed_str())));
            }
            Event::Start(Tag::Link { ref dest_url, .. }) | Event::Start(Tag::Image { ref dest_url, .. })
                if !safe_destination(dest_url) =>
            {
                skipped.push(SkipKind::of_start(&event));
            }
            event => output.push(event),
        }
    }
    let mut body = String::new();
    html::push_html(&mut body, output.into_iter());
    body = body.replace("<li><input", "<li class=\"task-list-item\"><input");
    body = body.replace("<li>\n<input", "<li class=\"task-list-item\"><input");
    let theme_name = match theme {
        RenderTheme::Dark => "dark",
        RenderTheme::Light => "light",
    };
    format!(
        r#"<article class="memo-markdown {theme_name}"><style>{css}</style>{body}</article>"#,
        css = article_css(),
        body = body
    )
}

fn article_css() -> &'static str {
    r#"
.memo-markdown {
  --memo-text:14px;
  --memo-h1:32px;
  --memo-h2:28px;
  --memo-h3:24px;
  --memo-h4:20px;
  --memo-h5:16px;
  --memo-h6:16px;
  --memo-code-size:12px;
  --memo-space:14px;
  color: var(--memo-fg);
  background: var(--memo-bg);
  font-size: var(--memo-text);
   font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
   line-height: 1.6;
   padding: 1.5rem clamp(1rem, 4vw, 3rem);
  overflow-wrap: anywhere;
}
.memo-markdown.dark {
  --memo-fg:#d4d4d4;
  --memo-bg:#1e1e1e;
  --memo-border:#454545;
  --memo-code:#2b2b2b;
  --memo-inline-code:#ce9178;
  --memo-link:#3794ff;
}
.memo-markdown.light {
  --memo-fg:#24292f;
  --memo-bg:#fff;
  --memo-border:#d0d7de;
  --memo-code:#f6f8fa;
  --memo-inline-code:#a31515;
  --memo-link:#0969da;
}
.memo-markdown > * + * { margin-top: var(--memo-space); }
.memo-markdown h1 { font-size: var(--memo-h1); font-weight: 700; margin: 0; padding-bottom:.35em; border-bottom:1px solid var(--memo-border); }
.memo-markdown h2 { font-size: var(--memo-h2); font-weight: 700; margin: 0; padding-bottom:.3em; border-bottom:1px solid var(--memo-border); }
.memo-markdown h3 { font-size: var(--memo-h3); font-weight: 650; margin: 0; }
.memo-markdown h4 { font-size: var(--memo-h4); font-weight: 650; margin: 0; }
.memo-markdown h5 { font-size: var(--memo-h5); font-weight: 600; margin: 0; }
.memo-markdown h6 { font-size: var(--memo-h6); font-weight: 600; margin: 0; }
.memo-markdown p { margin: 0; }
.memo-markdown a { color: var(--memo-link); text-decoration: none; }
.memo-markdown a:hover { text-decoration: underline; }
.memo-markdown code {
  font-family: Consolas, Monaco, "Courier New", monospace;
  font-size: var(--memo-code-size);
  background: var(--memo-code);
  color: var(--memo-inline-code);
  padding: 0 4px;
  border-radius: 4px;
}
.memo-markdown pre.memo-code,
.memo-markdown pre {
  font-size: var(--memo-code-size);
  background: var(--memo-code);
   padding: 16px;
  overflow: auto;
  border-radius: 8px;
  margin: 0;
}
.memo-markdown pre code { background: transparent; color: inherit; padding: 0; border-radius: 0; }
.memo-markdown .memo-code-block { position: relative; overflow: hidden; border: 1px solid var(--memo-border); border-radius: 8px; }
.memo-markdown .memo-code-block pre { padding-top: 44px; }
.memo-markdown .memo-code-toolbar { position: absolute; z-index: 1; inset: 0 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 36px; padding: 4px 8px; background: var(--memo-code); color: var(--memo-fg); }
.memo-markdown .memo-code-language { color: var(--memo-fg); font: 600 11px/1 Consolas, Monaco, "Courier New", monospace; letter-spacing: .04em; opacity: .78; }
.memo-markdown .memo-code-copy {
  border: 1px solid var(--memo-border);
  border-radius: 4px;
  padding: 3px 7px;
  background: var(--memo-bg);
  color: var(--memo-fg);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.memo-markdown .memo-code-copy:focus-visible { outline: 2px solid var(--memo-link); outline-offset: 2px; }
.memo-markdown blockquote {
  margin: 0;
  padding-left: var(--memo-space);
  border-left: 3px solid var(--memo-border);
  color: var(--memo-fg);
}
.memo-markdown blockquote > :first-child { margin-top: 0; }
.memo-markdown blockquote > :last-child { margin-bottom: 0; }
.memo-markdown ul,
.memo-markdown ol { margin: 0; padding-left: 1.25rem; }
.memo-markdown li + li { margin-top: calc(var(--memo-space) * 0.45); }
.memo-markdown .task-list-item { list-style: none; margin-left: -0.5rem; }
.memo-markdown .task-list-item input { margin: 0 0.5rem 0 0; vertical-align: middle; accent-color: var(--memo-link); }
.memo-markdown table { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; width: 100%; }
.memo-markdown th,
.memo-markdown td {
  border: 1px solid var(--memo-border);
  padding: 0.4rem 0.6rem;
  white-space: nowrap;
}
.memo-markdown th { background:var(--memo-code); font-weight:600; }
.memo-markdown tr:nth-child(even) { background:color-mix(in srgb, var(--memo-code) 45%, transparent); }
.memo-markdown hr {
  border: 0;
  border-top: 1px solid var(--memo-border);
  margin: var(--memo-space) 0;
}
.memo-markdown img { display: block; max-width: 100%; height: auto; object-fit: contain; }
.memo-markdown .footnote-definition,
.memo-markdown .footnotes { font-size: 0.9em; color: var(--memo-fg); opacity: 0.9; }
.memo-markdown .footnote-definition a,
.memo-markdown .footnote-backref { color: var(--memo-link); font-size: .9em; }
"#
}

fn normalize_language_token(language: &str) -> String {
    language
        .split(|c: char| c == ',' || c.is_whitespace())
        .next()
        .unwrap_or("")
        .trim()
        .to_string()
}

fn highlight_code(code: &str, language: &str, render_theme: RenderTheme) -> String {
    static SYNTAXES: OnceLock<SyntaxSet> = OnceLock::new();
    static THEMES: OnceLock<ThemeSet> = OnceLock::new();
    let syntaxes = SYNTAXES.get_or_init(SyntaxSet::load_defaults_newlines);
    let themes = THEMES.get_or_init(ThemeSet::load_defaults);
    let token = language;
    let label = if token.is_empty() {
        "TEXT".to_string()
    } else {
        token.to_ascii_uppercase()
    };
    let Some(syntax) = syntaxes.find_syntax_by_token(token) else {
        return code_block_html(
            format!(
                r#"<pre class="memo-code"><code>{}</code></pre>"#,
                escape_html(code)
            ),
            &label,
        );
    };
    let theme_name = match render_theme {
        RenderTheme::Dark => "base16-ocean.dark",
        RenderTheme::Light => "InspiredGitHub",
    };
    match themes
        .themes
        .get(theme_name)
        .and_then(|theme| highlighted_html_for_string(code, syntaxes, syntax, theme).ok())
    {
        Some(html) => {
            let html = remove_pre_inline_style(html);
            let html = if html.contains("class=\"") {
                html.replacen("<pre ", r#"<pre class="memo-code" "#, 1)
                    .replacen("<pre>", r#"<pre class="memo-code">"#, 1)
            } else if let Some(rest) = html.strip_prefix("<pre") {
                format!(r#"<pre class="memo-code"{rest}"#)
            } else {
                format!(r#"<pre class="memo-code">{html}</pre>"#)
            };
            code_block_html(html, &label)
        }
        None => code_block_html(
            format!(
                r#"<pre class="memo-code"><code>{}</code></pre>"#,
                escape_html(code)
            ),
            &label,
        ),
    }
}

fn code_block_html(code: String, language: &str) -> String {
    format!(
        r#"<div class="memo-code-block"><div class="memo-code-toolbar"><span class="memo-code-language">{language}</span><button type="button" class="memo-code-copy" data-memo-code-copy aria-label="Copy code">Copy</button></div>{code}</div>"#,
        language = escape_html(language),
    )
}

fn remove_pre_inline_style(html: String) -> String {
    let Some(opening_end) = html.find('>') else {
        return html;
    };
    let Some(style_start) = html[..opening_end].find(" style=\"") else {
        return html;
    };
    let value_start = style_start + " style=\"".len();
    let Some(style_end) = html[value_start..opening_end].find('"') else {
        return html;
    };
    let style_end = value_start + style_end + 1;
    format!("{}{}", &html[..style_start], &html[style_end..])
}

fn escape_html(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

fn safe_destination(destination: &str) -> bool {
    let value = destination.trim();
    if value.is_empty() || value.starts_with("//") || value.starts_with('\\') {
        return false;
    }
    if value.starts_with('#')
        || value.starts_with('/')
        || value.starts_with("./")
        || value.starts_with("../")
    {
        return true;
    }
    let lower = value.to_ascii_lowercase();
    if lower.starts_with("http://") || lower.starts_with("https://") || lower.starts_with("mailto:")
    {
        return true;
    }
    !value.split(['/', '?', '#']).next().unwrap_or("").contains(':')
}
