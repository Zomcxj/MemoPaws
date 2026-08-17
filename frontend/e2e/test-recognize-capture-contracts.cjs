const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const recognizeSource = fs.readFileSync(path.join(__dirname, "..", "src", "pages", "RecognizePage.tsx"), "utf8");
assert.match(
  recognizeSource,
  /llmKeys\.map\(\(entry\) => <option key=\{entry\.id\} value=\{entry\.id\}>\{entry\.name\}<\/option>\)/,
  "RecognizePage must expose an LLM key picker listing every LLM key by name",
);
assert.match(
  recognizeSource,
  /<option value=\{0\}>\{t\.settingsKey\}<\/option>/,
  "the key picker must lead with a settings-key option (value 0)",
);
assert.match(
  recognizeSource,
  /keyEntryId: keyId === 0 \? null : keyId/,
  "settings mode must pass null so the backend uses the saved settings config",
);
assert.match(
  recognizeSource,
  /invoke\("set_settings_key", \{ entryId: keyId \}\)/,
  "selecting a key must offer promoting it into the settings config",
);
assert.match(
  recognizeSource,
  /<select className="tool-button" aria-label=\{t\.key\}/,
  "the key picker must be a toolbar select labelled by the key text",
);

const overlayCss = fs.readFileSync(path.join(__dirname, "..", "src", "components", "CaptureOverlay.css"), "utf8");
const overlayBlock = overlayCss.match(/\.capture-overlay \{[\s\S]*?\}/);
assert.ok(overlayBlock, "capture-overlay rule must exist");
assert.ok(
  !/rgba\(0, 0, 0, 0\.55\)/.test(overlayBlock[0]),
  "capture overlay must not dim the whole screen with a dark glass mask",
);

console.log("recognize key picker and capture overlay contracts passed");