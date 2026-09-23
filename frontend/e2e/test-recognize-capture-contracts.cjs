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

const panelCss = overlayCss.match(/\.capture-result-window \{[\s\S]*?\}/);
assert.ok(panelCss && /position: absolute/.test(panelCss[0]), "the result window must be positioned relative to the selection");
const panelSource = overlaySource.match(/const defaultResultWindow =[\s\S]*?return \{[\s\S]*?\};/);
assert.ok(
  panelSource && /rectStyle\.left \+ rectStyle\.width \+ RESULT_WINDOW_GAP/.test(panelSource[0]),
  "the result window must hug the selection with the Python gap",
);

const recognizeCss = fs.readFileSync(path.join(__dirname, "..", "src", "pages", "RecognizePage.css"), "utf8");
assert.match(recognizeSource, /const \[recognizing, setRecognizing\]/, "OCR must have its own running state");
assert.match(recognizeSource, /const \[translating, setTranslating\]/, "translation must have its own running state");
assert.match(recognizeSource, /result-panel" \+ \(recognizing \? " is-running" : ""\)/, "only the OCR panel may glow during OCR");
assert.match(recognizeSource, /result-panel" \+ \(translating \? " is-running" : ""\)/, "only the translation panel may glow during translation");
assert.doesNotMatch(recognizeSource, /result-panel" \+ \(loading \? " is-running" : ""\)/, "a shared loading state must not animate both result panels");
assert.match(recognizeSource, /history_list/, "recognition page must load the operation history");
assert.match(recognizeSource, /history_delete|history_clear/, "recognition page must support deleting and clearing history");
assert.match(recognizeSource, /recognize-history/, "recognition page must render the history panel");

assert.match(
  overlaySource,
  /onConfirm: \(result: \{ image: Uint8Array; ocrText: string; translation: string \}\)/,
  "CaptureOverlay confirmation must return the selected image and both result fields",
);
assert.match(overlaySource, /\["n", "ne", "e", "se", "s", "sw", "w", "nw"\]/);
for (const handle of ["n", "ne", "e", "se", "s", "sw", "w", "nw"]) {
  assert.match(overlayCss, new RegExp(`\\.capture-overlay-handle--${handle}`));
}
assert.match(overlaySource, /capture-result-window/);
assert.match(overlaySource, /capture-result-window-title/);
assert.match(overlaySource, /draggingResultWindow/);
assert.match(overlaySource, /resizingResultWindow/);
assert.match(overlaySource, /capture-result-window-resize/);
assert.match(overlaySource, /RESULT_WINDOW_MIN_WIDTH = 450/);
assert.match(overlaySource, /RESULT_WINDOW_MIN_HEIGHT = 533/);
assert.match(overlaySource, /RESULT_WINDOW_MAX_WIDTH = 900/);
assert.match(overlaySource, /RESULT_WINDOW_MAX_HEIGHT = 800/);
assert.match(overlaySource, /RESULT_WINDOW_GAP = 16/);
assert.match(overlaySource, /ocrText/);
assert.match(overlaySource, /translation/);
assert.ok(!overlaySource.includes("capture-overlay-bar"), "the capsule action bar must be removed");
assert.match(overlayCss, /\.capture-overlay-action \{[\s\S]*?width: 28px[\s\S]*?height: 28px[\s\S]*?border-radius: var\(--radius-3\)/);
assert.match(overlayCss, /\.capture-overlay-action--label \{[\s\S]*?width: auto[\s\S]*?min-width: 48px/, "localized screenshot actions must have room for full labels");
assert.match(overlayCss, /min-width: 450px/);
assert.match(overlayCss, /min-height: 533px/);
assert.match(overlayCss, /max-width: 900px/);
assert.match(overlayCss, /max-height: 800px/);
assert.match(
  recognizeSource,
  /setOriginal\(image\)[\s\S]*?setBytes\(image, false\)[\s\S]*?setOcrText\(confirmedOcr\)[\s\S]*?setTranslation\(confirmedTranslation\)[\s\S]*?restoreCaptureWindow\(\)/,
  "confirmation must update image, OCR, translation, and restore the capture window",
);
assert.match(recognizeSource, /windowGeometryRef\.current = geometry/, "failed restore must retain geometry for retry");
assert.match(recognizeSource, /if \(restoreSucceeded\)/, "capture restore must only clear geometry after every operation succeeds");
assert.match(overlaySource, /operationTokenRef/, "overlay async operations must use a generation token");
assert.match(overlaySource, /operationTokenRef\.current === operationToken/, "late overlay results must be rejected");
assert.match(overlaySource, />\{text\.recognize\}<\/button>/, "screenshot OCR action must render the localized full label");
assert.match(overlaySource, />\{text\.translate\}<\/button>/, "screenshot translate action must render the localized full label");
assert.match(overlaySource, />\{text\.copyImage\}<\/button>/, "screenshot copy action must render the localized full label");
assert.match(overlaySource, />\{text\.saveImage\}<\/button>/, "screenshot save action must render the localized full label");
assert.doesNotMatch(overlaySource, />R<\/button>|>T<\/button>|>C<\/button>|>S<\/button>/, "screenshot actions must not use English letter abbreviations");

console.log("settings key promotion and capture overlay contracts passed");
