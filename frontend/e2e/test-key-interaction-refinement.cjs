const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "..", "src", "pages", "KeysPage.tsx"), "utf8");

assert.match(
  source,
  /const dragThreshold = entry\.type === "llm" \? 8 : 18;[\s\S]*Math\.hypot\(event\.clientX - drag\.x, event\.clientY - drag\.y\) < dragThreshold/,
  "LLM pointer drag must begin after 8px while secret drag remains 18px",
);

assert.match(
  source,
  /for \(const entry of llm\) \{[\s\S]*setTestingGlyphs\(\{ \[entry\.id\]: matrixFrame\(\) \}\);[\s\S]*await invoke<Record<string, unknown>>\("test_api_connection"/,
  "speed tests must invoke LLM cards in strict for...of order with only the current glyph active",
);

assert.match(
  source,
  /const waitForRender = \(\) => new Promise<void>\(\(resolve\) => window\.requestAnimationFrame\(\(\) => resolve\(\)\)\);/,
  "speed tests must expose a requestAnimationFrame render boundary without an arbitrary timeout",
);

assert.match(
  source,
  /setLatency\(\(current\) => \(\{ \.\.\.current, \[entry\.id\]: result \}\)\);[\s\S]*setTestingGlyphs\(\{\}\);[\s\S]*await waitForRender\(\);[\s\S]*\}/,
  "each result and glyph cleanup must cross a render boundary before the serial loop advances",
);

assert.match(
  source,
  /const ticker = window\.setInterval\([\s\S]*?try \{[\s\S]*?await invoke<Record<string, unknown>>\("test_api_connection"[\s\S]*?\} finally \{[\s\S]*?window\.clearInterval\(ticker\);[\s\S]*?\}[\s\S]*?setLatency[\s\S]*?setTestingGlyphs\(\{\}\);[\s\S]*?await waitForRender\(\);/,
  "each card must clear its own glyph ticker and render its terminal state before another request can start",
);

assert.match(
  source,
  /try \{[\s\S]*for \(const entry of llm\) \{[\s\S]*\} finally \{[\s\S]*window\.clearInterval\(ticker\);[\s\S]*setTestingGlyphs\(\{\}\);[\s\S]*setTesting\(false\);[\s\S]*\}/,
  "speed test cleanup must run when an invocation throws",
);

console.log("KeysPage interaction refinement contract passed");
