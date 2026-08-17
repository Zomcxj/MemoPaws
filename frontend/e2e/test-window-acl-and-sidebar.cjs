const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const capabilityPath = path.join(__dirname, "..", "..", "crates", "memopaws-tauri", "capabilities", "default.json");
const capability = JSON.parse(fs.readFileSync(capabilityPath, "utf8"));
for (const perm of ["core:window:allow-hide", "core:window:allow-show", "core:window:allow-minimize"]) {
  assert.ok(capability.permissions.includes(perm), `capability must include ${perm}`);
}

const keysSource = fs.readFileSync(path.join(__dirname, "..", "src", "pages", "KeysPage.tsx"), "utf8");
assert.match(
  keysSource,
  /if \(overlapArea <= dragArea \/ 2\) continue;[\s\S]*if \(overlapArea <= dragArea \/ 2\) continue;/,
  "swap must require overlap exceeding half of the dragged item's own area",
);

const sidebarCss = fs.readFileSync(path.join(__dirname, "..", "src", "components", "Sidebar.css"), "utf8");
const toggleBlock = sidebarCss.match(/\.sidebar-toggle \{[\s\S]*?\}/);
assert.ok(toggleBlock, "sidebar-toggle rule must exist");
assert.ok(
  !/background:\s*var\(--bg-active\)/.test(toggleBlock[0]),
  "sidebar-toggle must not render a background box in its default state",
);

console.log("window ACL, overlap-swap and sidebar-toggle contracts passed");