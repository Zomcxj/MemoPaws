// Focused static regression contracts for final-review floating and key reordering fixes.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const app = read("src", "App.tsx");
const recognize = read("src", "pages", "RecognizePage.tsx");
const keys = read("src", "pages", "KeysPage.tsx");
const keyStyles = read("src", "pages", "KeysPage.css");
const config = read("..", "crates", "memopaws-tauri", "tauri.conf.json");
const commands = read("..", "crates", "memopaws-tauri", "src", "commands.rs");
const lib = read("..", "crates", "memopaws-tauri", "src", "lib.rs");

for (const [intent, page] of [["paste_ocr", "recognize"], ["keys", "keys"], ["settings", "settings"]]) {
  assert.match(app, new RegExp(`case "${intent}":[\\s\\S]*?navigateRef\\.current\\("${page}"\\)`),
    `floating ${intent} intent must navigate to ${page}`);
}
assert.match(app, /case "paste_ocr":[\s\S]*?setPasteOcrRequest\(\(request\) => request \+ 1\)/,
  "paste OCR intent must request the recognition paste workflow after navigation");
assert.match(recognize, /useEffect\(\(\) => \{ if \(pasteOcrRequest\) contextPasteImage\(\); \}, \[pasteOcrRequest\]\)/,
  "the recognition page must consume the paste OCR request after it mounts");

const floatingConfig = JSON.parse(config).app.windows.find((window) => window.label === "floating");
assert.ok(floatingConfig, "native floating window must be configured");
assert.ok(floatingConfig.width >= 242 + 16,
  "native floating window must fit the 242px launcher-and-left-menu minimum plus outer padding");
assert.doesNotMatch(commands, /WebviewWindowBuilder::new\(&app, "floating"/,
  "visibility toggling must use the configured native floating window, not a fallback builder");
assert.match(lib, /if config\.show_floating_widget\.unwrap_or\(true\) \{[\s\S]*?set_floating_widget_visible\(true, app\.handle\(\)\.clone\(\)\)/,
  "startup must show the configured default floating widget after initialization");

assert.match(keys, /aria-label=\{t\.dragHandle\}/,
  "each keyboard drag handle must have an accessible label");
assert.match(keys, /dragHandle:\s*"拖动以重新排序；按上箭头或下箭头可立即调整顺序"/,
  "the Chinese drag-handle label must disclose immediate ArrowUp/ArrowDown reordering");
assert.match(keys, /dragHandle:\s*"Drag to reorder; press ArrowUp or ArrowDown to move immediately"/,
  "the English drag-handle label must disclose immediate ArrowUp/ArrowDown reordering");
assert.match(keys, /if \(event\.key === "ArrowDown" \|\| event\.key === "ArrowUp"\) \{[\s\S]*?if \(!drag \|\| !drag\.started \|\| drag\.id !== entry\.id\) \{[\s\S]*?pointerDrag\.current = \{ id: entry\.id, type: entry\.type, x: 0, y: 0, started: true/,
  "an arrow key must start keyboard reordering without holding Space or Enter");
assert.doesNotMatch(keys, /const handleDragKeyUp[\s\S]*?commitDrag\(finished\)/,
  "reordering must not depend on releasing the Space or Enter key");
assert.match(keyStyles, /\.key-drag-handle[\s\S]*?min-width:\s*18px[\s\S]*?min-height:\s*18px/s,
  "the dedicated pointer drag handle must retain its 18px target rules");

console.log("Final review fix contracts passed.");
