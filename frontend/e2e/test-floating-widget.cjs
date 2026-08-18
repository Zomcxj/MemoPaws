// Focused static contract test for the Python-style floating widget.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const widget = read("src", "components", "FloatingWidget.tsx");
const css = read("src", "components", "FloatingWidget.css");

// 1. Transparent 56px circular launcher surface.
assert.match(css, /\.floating-widget\s*\{[^}]*background:\s*transparent[^}]*\}/s,
  "the launcher surface must remain transparent");
assert.match(css, /\.floating-ball\s*\{[^}]*width:\s*56px[^}]*height:\s*56px[^}]*border-radius:\s*50%[^}]*\}/s,
  "the launcher must be a 56px circle");

// 2. Unicode pictographs are gone; actions use existing public SVG assets with empty alt.
for (const glyph of ["🐾", "◱", "✎", "❐", "⌕", "⌂", "×"]) {
  assert.doesNotMatch(widget, new RegExp(glyph), `unicode pictograph ${glyph} must be removed`);
}
const iconRefs = (widget.match(/\/assets\/icons\/[a-z0-9-]+\.svg/g) || []).length;
assert.equal(iconRefs, 8,
  `launcher plus the 7 menu actions must reference existing public SVG assets (found ${iconRefs})`);
for (const match of widget.matchAll(/\/assets\/icons\/([a-z0-9-]+\.svg)/g)) {
  assert.ok(fs.existsSync(path.join(root, "public", "assets", "icons", match[1])),
    `icon asset must exist on disk: ${match[1]}`);
}
const emptyAlts = (widget.match(/<img[^>]*alt="" /g) || []).length;
const imgTags = (widget.match(/<img/g) || []).length;
assert.equal(emptyAlts, imgTags,
  `every rendered icon must carry an empty alt text (found ${emptyAlts} alt="" <img> for ${imgTags} total <img> tags)`);
assert.match(widget, /\/assets\/icons\/menu\.svg/, "the launcher ball must reuse the public menu icon");

// 3. Python action set: screenshot OCR, paste OCR, clipboard, memo, keys, settings, hide.
const actionIds = ["capture", "paste_ocr", "clipboard", "memo", "keys", "settings"];
for (const id of actionIds) {
  assert.match(widget, new RegExp(`id: "${id}"`), `menu must expose the ${id} action`);
}
assert.match(widget, /title=\{action\.label\}/,
  "menu actions must retain title tooltips");
assert.match(widget, /className="floating-hide"[\s\S]*?title=\{t\.hide\}/,
  "the hide action must be a visually distinct menu entry with its own tooltip");
assert.match(widget, /floating-action-label/,
  "menu actions must retain textual labels");

// 4. Click opens an inward-facing menu centered against the launcher and never
//    captures launcher dragging. The 56px ball expands the window only while the menu is open.
assert.match(widget, /setOpen\(\(current\) => \{[\s\S]*?resizeForMenu\(next, edge\)[\s\S]*?return next;/,
  "a plain click on the launcher must toggle the menu and resize the window to fit it");
assert.match(widget, /const resizeForMenu = async \(menuOpen: boolean, currentEdge: Edge\) => \{/,
  "the launcher must expand the window only while the menu is open");
assert.match(css, /\.floating-anchor\s*\{[^}]*position:\s*relative[^}]*pointer-events:\s*none[^}]*\}/s,
  "the 56px launcher surface must be a positioned, non-interactive anchor");
assert.match(css, /\.floating-widget\s*\{[^}]*overflow:\s*visible[^}]*\}/s,
  "the floating window must not clip the menu extending left of its launcher");
assert.match(css, /\.floating-menu\s*\{[^}]*position:\s*absolute[^}]*right:\s*100%[^}]*top:\s*50%[^}]*transform:\s*translateY\(-50%\)[^}]*pointer-events:\s*auto[^}]*\}/s,
  "the menu must be an absolute panel on the launcher's left, vertically centered");
assert.match(css, /\.floating-widget\.is-right\s+\.floating-menu\s*\{[^}]*right:\s*100%[^}]*left:\s*auto[^}]*margin-right:\s*8px[^}]*margin-left:\s*0[^}]*\}/s,
  "a right-edge launcher must keep the menu inward on its left with 8px spacing");
assert.match(css, /\.floating-widget\.is-left\s+\.floating-menu\s*\{[^}]*left:\s*100%[^}]*right:\s*auto[^}]*margin-left:\s*8px[^}]*margin-right:\s*0[^}]*\}/s,
  "a left-edge launcher must open its menu inward on the right with 8px spacing");
assert.match(widget, /<nav className="floating-menu"[^>]*>/,
  "the menu panel must render as a plain nav without pointer drag handlers");

// 5. Native window drag, click-versus-drag delay and position persistence.
assert.match(widget, /const DRAG_THRESHOLD = 4;/, "click-versus-drag threshold must be preserved");
assert.match(widget, /onPointerDown=\{onPointerDown\}[\s\S]*?onPointerUp=\{onPointerUp\}[\s\S]*?onPointerCancel=\{onPointerUp\}/,
  "only the launcher ball must own the pointer handlers");
assert.match(widget, /startDragging\(\)/, "drag must use the native window drag");
assert.doesNotMatch(widget, /onPointerMove=\{onPointerMove\}/,
  "dragging must not depend on JS pointer moves");
assert.match(widget, /"floating-edge"/, "edge must persist under the floating-edge key");
assert.match(widget, /"floating-pos"/, "position must persist under the floating-pos key");
assert.match(widget, /writeStored\(POS_KEY, JSON\.stringify\(\{ x, y \}\)\)/,
  "release must persist the launcher position");
assert.match(widget, /persistAfterDrag\(\)/, "release must keep the launcher where it lands");
assert.doesNotMatch(widget, /snapToEdge/, "release must not force the launcher back to an edge");

// 6. The floating native window must be a 56px ball that expands to fit the menu.
const tauriConf = JSON.parse(read("..", "crates", "memopaws-tauri", "tauri.conf.json"));
const floatingWin = tauriConf.app.windows.find((w) => w.label === "floating");
assert.ok(floatingWin, "the floating window must be declared");
assert.equal(floatingWin.width, 56, "the floating window must start as a 56px ball");
assert.equal(floatingWin.height, 56, "the floating window must start as a 56px ball");
assert.equal(floatingWin.transparent, true, "the floating window must stay transparent");

// 7. Intent emission and hide command are preserved.
assert.match(widget, /emit\("floating-intent", intent\)/,
  "action clicks must keep emitting floating-intent events");
assert.match(widget, /invoke\("set_floating_widget_visible", \{ visible: false \}\)/,
  "the hide command must be preserved");

console.log("Floating widget contracts passed.");
