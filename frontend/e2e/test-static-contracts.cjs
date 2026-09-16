// Static contracts that have no runtime behaviour to observe.
//
// Only two kinds of assertion belong here:
//
//   1. Data contracts — config files whose *values* are the contract
//      (tauri.conf.json window labels).
//   2. Removal guards — a feature was deleted on purpose, and "it is still
//      gone" cannot be asserted by driving a UI that no longer has it.
//
// Everything else (pixel sizes, constant values, ref names, regex snapshots of
// component internals) lives in test-interaction-behaviour.cjs as an observable
// assertion, or was deleted: restating a stylesheet in a test catches no bug
// and has to be edited every time the design changes.
//
// Two contracts moved to Rust, where they assert real output under `cargo test`
// instead of grepping source from a browser test:
//   - the single-window capability ACL (tauri/src/tray.rs)
//   - the renderer emitting no inline JavaScript (memo/src/renderer.rs)

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");

// --- Data contract: the app ships exactly one window ------------------------

const tauriConfig = JSON.parse(read("..", "crates", "tauri", "tauri.conf.json"));
assert.deepEqual(
  tauriConfig.app.windows.map((window) => window.label),
  ["main"],
  "the app must declare exactly one window labelled main",
);

// --- Removal guard: the floating widget is gone for good --------------------
//
// It was removed in favour of the fullscreen capture overlay. Re-adding any of
// these symbols would resurrect a second window, which the single-window
// capability ACL above no longer permits.

const floatingSymbols = {
  "src/App.tsx": /FloatingWidget|floating-intent|isFloatingWindow|setPasteOcrRequest/,
  "src/pages/SettingsPage.tsx": /show_floating_widget|set_floating_widget_visible|floating:/,
  "e2e/mock-tauri.js": /show_floating_widget|set_floating_widget_visible/,
  "../crates/config/src/config.rs": /show_floating_widget/,
  "../crates/tauri/src/commands.rs": /show_floating_widget|set_floating_widget_visible|floating-widget-visibility-changed/,
  "../crates/tauri/src/lib.rs": /show_floating_widget|set_floating_widget_visible/,
};

for (const [file, symbols] of Object.entries(floatingSymbols)) {
  assert.doesNotMatch(read(...file.split("/")), symbols, `${file} must not reference the removed floating widget`);
}

assert.ok(
  !fs.existsSync(path.join(root, "src", "components", "FloatingWidget.tsx")),
  "FloatingWidget.tsx must stay deleted",
);

// The renderer's "no inline JavaScript" contract used to be grepped here. It now
// lives in crates/memo/src/renderer.rs::code_blocks_expose_a_copy_marker_and_no_inline_javascript,
// which asserts it on actual rendered output rather than on the source text.

console.log("static contracts passed");
