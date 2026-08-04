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

pub fn render_markdown(markdown: &str, theme: RenderTheme) -> String {
    let options = Options::ENABLE_TABLES
        | Options::ENABLE_STRIKETHROUGH
        | Options::ENABLE_TASKLISTS
        | Options::ENABLE_FOOTNOTES;
    let mut output = Vec::new();
    let mut events = Parser::new_ext(markdown, options);
    let mut blocked_destination_depth = 0usize;
    while let Some(event) = events.next() {
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
                output.push(Event::Html(CowStr::Boxed(
                    highlight_code(&code, &language, theme).into_boxed_str(),
                )));
            }
            Event::Html(raw) | Event::InlineHtml(raw) => {
                output.push(Event::Html(CowStr::Boxed(escape_html(&raw).into_boxed_str())));
            }
            Event::Start(Tag::Link { dest_url, .. }) | Event::Start(Tag::Image { dest_url, .. })
                if !safe_destination(&dest_url) =>
            {
                blocked_destination_depth += 1;
            }
            Event::End(TagEnd::Link) | Event::End(TagEnd::Image) if blocked_destination_depth > 0 => {
                blocked_destination_depth -= 1;
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
  --memo-text:16px;
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
  line-height: 1.65;
  padding: 1rem;
  overflow-wrap: anywhere;
}
.memo-markdown.dark {
  --memo-fg:#e8e8ef;
  --memo-bg:#171725;
  --memo-border:#3a3a50;
  --memo-code:#232338;
  --memo-link:#D97757;
}
.memo-markdown.light {
  --memo-fg:#25252d;
  --memo-bg:#fff;
  --memo-border:#dedee8;
  --memo-code:#f3f3f7;
  --memo-link:#D97757;
}
.memo-markdown > * + * { margin-top: var(--memo-space); }
.memo-markdown h1 { font-size: var(--memo-h1); font-weight: 700; margin: 0; }
.memo-markdown h2 { font-size: var(--memo-h2); font-weight: 700; margin: 0; }
.memo-markdown h3 { font-size: var(--memo-h3); font-weight: 650; margin: 0; }
.memo-markdown h4 { font-size: var(--memo-h4); font-weight: 650; margin: 0; }
.memo-markdown h5 { font-size: var(--memo-h5); font-weight: 600; margin: 0; }
.memo-markdown h6 { font-size: var(--memo-h6); font-weight: 600; margin: 0; }
.memo-markdown p { margin: 0; }
.memo-markdown a { color: var(--memo-link); text-decoration: none; }
.memo-markdown a:hover { text-decoration: underline; }
.memo-markdown code {
  font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
  font-size: var(--memo-code-size);
  background: var(--memo-code);
  padding: 0 4px;
  border-radius: 4px;
}
.memo-markdown pre.memo-code,
.memo-markdown pre {
  font-size: var(--memo-code-size);
  background: var(--memo-code);
  padding: 12px;
  overflow: auto;
  border-radius: 8px;
  margin: 0;
}
.memo-markdown pre code { background: transparent; padding: 0; border-radius: 0; }
.memo-markdown blockquote {
  margin: 0;
  padding-left: var(--memo-space);
  border-left: 3px solid var(--memo-border);
  color: var(--memo-fg);
}
.memo-markdown ul,
.memo-markdown ol { margin: 0; padding-left: 1.25rem; }
.memo-markdown li + li { margin-top: calc(var(--memo-space) * 0.45); }
.memo-markdown .task-list-item { list-style: none; margin-left: -0.5rem; }
.memo-markdown .task-list-item input { margin-right: 0.5rem; }
.memo-markdown table { border-collapse: collapse; width: 100%; }
.memo-markdown th,
.memo-markdown td {
  border: 1px solid var(--memo-border);
  padding: 0.4rem 0.6rem;
}
.memo-markdown hr {
  border: 0;
  border-top: 1px solid var(--memo-border);
  margin: var(--memo-space) 0;
}
.memo-markdown img { max-width: 100%; }
.memo-markdown .footnote-definition,
.memo-markdown .footnotes { font-size: 0.9em; color: var(--memo-fg); opacity: 0.9; }
"#
}

fn highlight_code(code: &str, language: &str, render_theme: RenderTheme) -> String {
    static SYNTAXES: OnceLock<SyntaxSet> = OnceLock::new();
    static THEMES: OnceLock<ThemeSet> = OnceLock::new();
    let syntaxes = SYNTAXES.get_or_init(SyntaxSet::load_defaults_newlines);
    let themes = THEMES.get_or_init(ThemeSet::load_defaults);
    let token = language.split(|c: char| c == ',' || c.is_whitespace()).next().unwrap_or("");
    let Some(syntax) = syntaxes.find_syntax_by_token(token) else {
        return format!(
            r#"<pre class="memo-code"><code>{}</code></pre>"#,
            escape_html(code)
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
            if html.contains("class=\"") {
                html.replacen("<pre ", r#"<pre class="memo-code" "#, 1)
                    .replacen("<pre>", r#"<pre class="memo-code">"#, 1)
            } else if let Some(rest) = html.strip_prefix("<pre") {
                format!(r#"<pre class="memo-code"{rest}"#)
            } else {
                format!(r#"<pre class="memo-code">{html}</pre>"#)
            }
        }
        None => format!(
            r#"<pre class="memo-code"><code>{}</code></pre>"#,
            escape_html(code)
        ),
    }
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
