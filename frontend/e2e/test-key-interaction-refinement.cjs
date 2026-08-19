const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "..", "src", "pages", "KeysPage.tsx"), "utf8");
for (const category of ["unauthorized", "not_found", "timeout", "connect", "request_timeout", "bad_request", "server_error", "bad_gateway", "http_error"]) {
  assert.match(source, new RegExp(`${category}:`), `KeysPage must localize ${category}`);
}
assert.match(source, /typeof localized === "string"/, "speed errors must render localized text instead of raw categories");

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

assert.doesNotMatch(
  source.match(/for \(const entry of llm\) \{[\s\S]*?\n  \};/)?.[0] || "",
  /vision_result|vision:\s*Boolean/,
  "key-list speed probes must not consume or display a vision probe result",
);

for (const kind of ["forbidden", "rate_limit", "service_unavailable"]) {
  assert.match(source, new RegExp(`${kind}:`), `key-list speed tests must localize ${kind}`);
}

console.log("KeysPage interaction refinement contract passed");
