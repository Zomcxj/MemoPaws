// Focused static regression contracts for final-review and key reordering fixes.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const keys = read("src", "pages", "KeysPage.tsx");
const keyStyles = read("src", "pages", "KeysPage.css");
const config = read("..", "crates", "memopaws-tauri", "tauri.conf.json");
const commands = read("..", "crates", "memopaws-tauri", "src", "commands.rs");
const lib = read("..", "crates", "memopaws-tauri", "src", "lib.rs");

assert.deepEqual(JSON.parse(config).app.windows.map((window) => window.label), ["main"]);
assert.doesNotMatch(commands, /floating|show_floating_widget/);
assert.doesNotMatch(lib, /floating|show_floating_widget/);

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
