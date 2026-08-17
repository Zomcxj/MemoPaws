const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const recognizeSource = fs.readFileSync(path.join(__dirname, "..", "src", "pages", "RecognizePage.tsx"), "utf8");
assert.match(
  recognizeSource,
  /keyEntryId: null/,
  "RecognizePage must always use the settings key (null entry id)",
);

const keysSource = fs.readFileSync(path.join(__dirname, "..", "src", "pages", "KeysPage.tsx"), "utf8");
assert.match(
  keysSource,
  /invoke\("set_settings_key", \{ entryId: entry\.id \}\)/,
  "KeysPage must promote a selected key into the settings key",
);
assert.match(
  keysSource,
  /onSetSettings/,
  "LlmCard must expose a set-as-settings action",
);
assert.match(
  keysSource,
  /t\.setAsSettings/,
  "the set-as-settings action must be labelled",
);

assert.match(
  recognizeSource,
  /setFullscreen\(true\)/,
  "capture must go fullscreen so the overlay covers the whole display",
);
assert.match(
  recognizeSource,
  /window\.isFullscreen\(\)/,
  "capture restore must detect the current fullscreen state",
);

assert.match(
  keysSource,
  /name !== "settings_api_key"/,
  "KeysPage must hide the internal settings key entry",
);
assert.match(
  recognizeSource,
  /const capture = async \(\) => \{[\s\S]*?await window\.hide\(\)[\s\S]*?await window\.setFullscreen\(true\)/,
  "capture must hide the window before going fullscreen (no resize flicker)",
);
assert.match(
  recognizeSource,
  /requestAnimationFrame\(\(\) => requestAnimationFrame\(resolve\)\)/,
  "capture must wait for the overlay to mount before showing the window",
);
assert.match(
  recognizeSource,
  /restoreCaptureWindow = async \(\) => \{[\s\S]*?await window\.hide\(\)[\s\S]*?setOverlay\(false\)/,
  "capture restore must unmount the overlay while hidden (no shrink flicker)",
);

const overlayCss = fs.readFileSync(path.join(__dirname, "..", "src", "components", "CaptureOverlay.css"), "utf8");
const overlaySource = fs.readFileSync(path.join(__dirname, "..", "src", "components", "CaptureOverlay.tsx"), "utf8");
const overlayBlock = overlayCss.match(/\.capture-overlay \{[\s\S]*?\}/);
assert.ok(overlayBlock, "capture-overlay rule must exist");
assert.ok(
  !/rgba\(0, 0, 0, 0\.55\)/.test(overlayBlock[0]),
  "capture overlay must not dim the whole screen with a dark glass mask",
);
assert.match(
  overlayBlock[0],
  /background: #000/,
  "capture overlay must be opaque so the app UI never shows through",
);

const panelCss = overlayCss.match(/\.capture-overlay-panel \{[\s\S]*?\}/);
assert.ok(panelCss && /right: 16px/.test(panelCss[0]), "results must render in a right-side panel like the Python version");
assert.match(overlayCss, /@keyframes capture-glow[\s\S]*?\}/, "selection must have a glow animation");
assert.match(overlayCss, /\.capture-overlay-rect \{[\s\S]*?animation: capture-glow/, "the selection rect must run the glow animation");
assert.match(
  overlaySource,
  /onClearResult\?:\s*\(\) => void/,
  "the result panel must support a clear action",
);
assert.match(
  recognizeSource,
  /onClearResult=\{\(\) => setCaptureResult\(""\)\}/,
  "RecognizePage must wire the result panel clear button",
);

console.log("settings key promotion and capture overlay contracts passed");