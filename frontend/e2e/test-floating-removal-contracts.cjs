const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const app = read("src", "App.tsx");
const recognize = read("src", "pages", "RecognizePage.tsx");
const settings = read("src", "pages", "SettingsPage.tsx");
const mock = read("e2e", "mock-tauri.js");
const config = read("..", "crates", "config", "src", "config.rs");
const commands = read("..", "crates", "tauri", "src", "commands.rs");
const tauriConfig = JSON.parse(read("..", "crates", "tauri", "tauri.conf.json"));
const capability = JSON.parse(read("..", "crates", "tauri", "capabilities", "default.json"));

assert.doesNotMatch(app, /FloatingWidget|floating-intent|isFloatingWindow|setPasteOcrRequest/);
assert.doesNotMatch(recognize, /pasteOcrRequest|contextPasteImage\(\); \}, \[pasteOcrRequest\]/);
assert.doesNotMatch(settings, /show_floating_widget|set_floating_widget_visible|floating:/);
assert.doesNotMatch(mock, /show_floating_widget|set_floating_widget_visible/);
assert.doesNotMatch(config, /show_floating_widget/);
assert.doesNotMatch(commands, /show_floating_widget|set_floating_widget_visible|floating-widget-visibility-changed/);
assert.deepEqual(tauriConfig.app.windows.map((window) => window.label), ["main"]);
assert.deepEqual(capability.windows, ["main"]);

console.log("floating removal contracts passed");
