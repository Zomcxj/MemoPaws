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
assert.ok(panelCss && !/right: 16px/.test(panelCss[0]) && /position: absolute/.test(panelCss[0]), "the panel position must be driven by the selection");
const panelSource = overlaySource.match(/const panelStyle =[\s\S]*?return \{[\s\S]*?\};/);
assert.ok(
  panelSource && /preferredLeft = rectStyle\.left \+ rectStyle\.width \+ GAP/.test(panelSource[0]),
  "the result panel must hug the right edge of the selection like the Python version",
);
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

const recognizeCss = fs.readFileSync(path.join(__dirname, "..", "src", "pages", "RecognizePage.css"), "utf8");
assert.match(
  recognizeCss,
  /\.recognize-panel\.result-panel\.is-running \{[\s\S]*?animation: result-glow/,
  "the OCR/translate panels must run the glow animation only while recognizing or translating",
);
assert.match(recognizeCss, /@keyframes result-glow/, "the result-glow keyframes must exist");
assert.match(
  recognizeSource,
  /\+\s*\(loading \? " is-running" : ""\)/,
  "the is-running class must be driven by the loading state",
);

console.log("settings key promotion and capture overlay contracts passed");