const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const memoPage = read("src", "pages", "MemoPage.tsx");
const memoCss = read("src", "pages", "MemoPage.css");
const renderer = fs.readFileSync(path.join(root, "..", "crates", "memo", "src", "renderer.rs"), "utf8");

assert.match(memoPage, /previewScale/);
assert.match(memoPage, /PREVIEW_SCALE_STEP\s*=\s*0\.001/,
  "preview zoom step must stay at 0.001");
assert.match(memoPage, /0\.85/);
assert.match(memoPage, /1\.35/);
assert.match(memoPage, /Math\.min\(\s*MAX_PREVIEW_SCALE,[\s\S]*Math\.max\(MIN_PREVIEW_SCALE/,
  "preview scale must be clamped to the supported range");
assert.match(memoPage, /event\.ctrlKey/);
assert.match(memoPage, /event\.preventDefault\(\)/,
  "Ctrl+wheel must prevent the preview page from scrolling");
assert.match(memoPage, /selected\.content[\s\S]*theme[\s\S]*previewScale/,
  "preview cache keys must include content, theme, and scale");
assert.match(memoPage, /const \{ theme \} = useTheme\(\)/, "memo preview must derive application theme reactively");
assert.match(memoPage, /\[mode, selected\?\.content, selected\?\.id, previewScale, theme\]/, "theme changes must rerun preview rendering");
assert.match(memoPage, /new Map<string, string>\(\)/,
  "rendered preview HTML must be cached in memory");
assert.match(memoPage, /PREVIEW_CACHE_MAX\s*=\s*50/,
  "preview cache must be capped at 50 entries");
assert.match(memoPage, /previewCache\.current\.size\s*>\s*PREVIEW_CACHE_MAX/,
  "preview cache must evict when it exceeds the cap");
assert.match(memoPage, /button\[data-memo-code-copy\]/,
  "memo preview must retain delegated code-copy handling");
assert.match(memoPage, /navigator\.clipboard\.writeText\(code\)/);
assert.match(memoPage, /onWheel=\{handlePreviewWheel\}/);
assert.match(memoCss, /--memo-preview-scale/,
  "preview CSS must consume the bounded scale");
assert.match(memoCss, /transform-origin:\s*top left/,
  "scaled preview content must keep a stable top-left origin");
assert.match(renderer, /class=\"memo-code-language\"/);
assert.match(renderer, /data-memo-code-copy/);
assert.doesNotMatch(renderer, /onclick=/i);

console.log("Memo preview contracts passed.");
