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
  /restoreCaptureWindow = async \(\) => \{[\s\S]*?await window\.hide\(\)/,
  "capture restore must hide the window before restoring geometry (no flicker)",
);

const overlayCss = fs.readFileSync(path.join(__dirname, "..", "src", "components", "CaptureOverlay.css"), "utf8");
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

console.log("settings key promotion and capture overlay contracts passed");