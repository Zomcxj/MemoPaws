// Focused static layout contract for clipboard rows and key testing feedback.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const clipboardPage = read("src", "pages", "ClipboardPage.tsx");
const clipboardCss = read("src", "pages", "ClipboardPage.css");
const memoPage = read("src", "pages", "MemoPage.tsx");
const memoRenderer = fs.readFileSync(path.join(root, "..", "crates", "memopaws-memo", "src", "renderer.rs"), "utf8");
const keysPage = read("src", "pages", "KeysPage.tsx");
const keysCss = read("src", "pages", "KeysPage.css");

assert.match(clipboardPage, /<div className="clipboard-item-body">/);
assert.equal((clipboardPage.match(/className="clipboard-item-actions"/g) || []).length, 1,
  "clipboard rows must share one dedicated action rail");
for (const action of ["clipboard-edit", "clipboard-preview-action", "clipboard-copy", "clipboard-lock", "clipboard-delete"]) {
  assert.match(clipboardPage, new RegExp(`clipboard-action clipboard-icon-action ${action}`));
}

assert.match(clipboardCss, /\.clipboard-item-body\s*\{[^}]*min-width:\s*0[^}]*overflow:\s*hidden[^}]*\}/s,
  "clipboard content must shrink and hide overflow before expanding a row");
assert.match(clipboardCss, /\.clipboard-items\.list \.clipboard-item-actions\s*\{[^}]*flex-direction:\s*row[^}]*\}/s,
  "list rows must keep their action rail horizontal");
assert.match(clipboardCss, /\.clipboard-items\.grid \.clipboard-item-actions\s*\{[^}]*flex-direction:\s*column[^}]*\}/s,
  "grid cards must stack their actions vertically");
assert.match(clipboardCss, /\.clipboard-item-actions\s*\{[^}]*flex-direction:\s*row[^}]*\}/s,
  "common actions must default to a horizontal direction");
assert.match(clipboardCss, /\.clipboard-items\.list \.clipboard-item\s*\{[^}]*grid-template-columns:\s*auto minmax\(0, 1fr\) auto[^}]*\}/s);
assert.match(clipboardCss, /\.clipboard-items\.list \.clipboard-item\s*\{[^}]*height:\s*40px[^}]*\}/s,
  "list rows must have a stable single-row height");
assert.ok(clipboardPage.includes('view === "list" ? (')
  && clipboardPage.includes('className="clipboard-list-summary"')
  && clipboardPage.includes('{formatClipboardLine(item)}'),
  "list view must render the summary instead of a grid preview");
assert.match(clipboardPage, /if \(view !== "grid"\) return;/,
  "images must only load automatically in grid view");
assert.match(clipboardPage, /const openPreview = async \(id: number\) => \{[\s\S]*await loadImage\(id\)[\s\S]*setPreviewId\(id\);/,
  "preview must load an image on demand before opening it");
assert.equal((clipboardPage.match(/onClick=\{\(\) => void openPreview\(item\.id\)\}/g) || []).length, 2,
  "both image preview actions must await on-demand loading");
assert.match(clipboardPage, /return \(item\.text \|\| ""\)\.split\(\/\\r\?\\n\/, 1\)\[0\];/,
  "text summaries must use only the first line");
assert.ok(clipboardPage.includes('return item.image_path?.split(/[\\\\/]/).pop() || "image.png";'),
  "image summaries must use only the filename");
assert.match(clipboardCss, /\.clipboard-page \.clipboard-icon-action\s*\{[^}]*width:\s*26px[^}]*height:\s*26px[^}]*box-sizing:\s*border-box[^}]*padding:\s*0[^}]*\}/s,
  "icon actions must override the page button padding and remain 26px squares");
assert.match(clipboardCss, /\.clipboard-items\.list \.clipboard-select\s*\{[^}]*max-width:\s*180px[^}]*overflow:\s*hidden[^}]*\}/s,
  "list metadata must be bounded and clipped rather than expanding its grid column");
assert.match(clipboardCss, /\.clipboard-items\.grid \.clipboard-image-wrap\s*\{[^}]*min-height:\s*0[^}]*overflow:\s*hidden[^}]*\}/s,
  "grid image wrappers must clip content within the card");
assert.match(clipboardCss, /\.clipboard-items\.grid \.clipboard-image-open,\s*\.clipboard-items\.grid \.clipboard-image-open img\s*\{[^}]*max-width:\s*100%[^}]*max-height:\s*100%[^}]*object-fit:\s*contain[^}]*\}/s,
  "grid images must remain contained by their wrapper");
assert.match(clipboardCss, /\.clipboard-image-name\s*\{[^}]*width:\s*100%[^}]*overflow:\s*hidden[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap[^}]*\}/s,
  "long image filenames must be ellipsized");
assert.match(clipboardCss, /\.clipboard-edit-dialog\s*\{[^}]*max-height:\s*min\(620px, 92vh\)[^}]*\}/s);
assert.match(keysCss, /\.key-latency\.is-testing\s*\{[^}]*color:\s*#3d9a5f[^}]*\}/s);
assert.match(keysCss, /\.keys-dialog,\s*\.keys-popover\s*\{[^}]*max-height:\s*min\(620px, 92vh\)[^}]*\}/s);
assert.match(keysPage, /const dragThreshold = entry\.type === "llm" \? 8 : 18;/,
  "LLM dragging must wait for an 8px threshold and secret dragging for an 18px threshold");
assert.match(keysPage, /event\.clientX >= rect\.left \+ rect\.width \/ 4[\s\S]*event\.clientX <= rect\.right - rect\.width \/ 4[\s\S]*event\.clientY >= rect\.top \+ rect\.height \/ 4[\s\S]*event\.clientY <= rect\.bottom - rect\.height \/ 4/,
  "LLM swap targets must use a card's central 50 percent on both axes");
assert.match(keysPage, /event\.clientY >= rect\.top \+ rect\.height \/ 4[\s\S]*event\.clientY <= rect\.bottom - rect\.height \/ 4/,
  "secret reorder targets must use a row's central 50 percent vertically");
assert.equal((keysPage.match(/className="key-drag-handle"/g) || []).length, 2,
  "each key layout must expose exactly one dedicated drag handle");
assert.doesNotMatch(keysPage, /<article\s+[^>]*onPointerDown=/,
  "key containers must not begin a drag themselves");
assert.match(keysPage, /className="key-drag-handle"[\s\S]*onPointerDown=\{onPointerDown\}[\s\S]*onPointerMove=\{onPointerMove\}[\s\S]*onPointerUp=\{onPointerUp\}/,
  "only drag handles must own pointer drag handlers");
assert.match(keysCss, /\.key-drag-handle\s*\{[^}]*cursor:\s*grab[^}]*\}/s,
  "only drag handles must advertise the grab cursor");
assert.doesNotMatch(keysCss, /\.key-card-llm\[data-key-id\],[\s\S]*\.key-row-secret\[data-key-id\]\s*\{[^}]*cursor:\s*grab/s,
  "whole cards and rows must not advertise drag affordance");
assert.match(keysCss, /\.key-card-llm\.is-dragging,[\s\S]*\.key-row-secret\.is-dragging\s*\{[^}]*border-color:\s*var\(--accent\)[^}]*box-shadow:[^}]*cursor:\s*grabbing/s,
  "active drags must retain an accent outline, shadow, and grabbing cursor");
assert.match(keysCss, /\.key-card-llm\.is-drop-target,[\s\S]*\.key-row-secret\.is-drop-target\s*\{[^}]*outline:/s,
  "drop targets must have a distinct visible outline");
assert.match(keysCss, /\.key-drag-handle\s*\{[^}]*touch-action:\s*none[^}]*\}/s,
  "drag handles must declare touch-action none up front so pointer streams survive their drag thresholds");
assert.equal((keysPage.match(/if \(id === drag\.id\) continue;/g) || []).length, 2,
  "target scanning must skip the actively dragged row for both LLM swaps and secret reorders");
assert.match(keysPage, /<span[\s\S]*?className="key-drag-handle"/,
  "drag handles must be non-submitting spans rather than buttons");
assert.match(keysPage, /role="button"[\s\S]*tabIndex=\{0\}/,
  "drag handles must be focusable with a button role");
assert.match(keysPage, /onKeyDown=\{onHandleKeyDown\}[\s\S]*onKeyUp=\{onHandleKeyUp\}/,
  "drag handles must be keyboard operable");
assert.match(keysPage, /event\.key === "ArrowDown" \|\| event\.key === "ArrowUp"/,
  "keyboard drags must move targets with arrow keys");
assert.match(keysPage, /event\.key === "Escape"/,
  "keyboard drags must be cancellable with Escape");
assert.match(keysPage, /started:\s*true[\s\S]*setDragging\(\{ id: entry\.id, type: entry\.type \}\)/,
  "keyboard activation must start dragging immediately without a movement threshold");
assert.match(memoPage, /button\[data-memo-code-copy\]/,
  "memo preview must delegate copy clicks from the safe renderer marker");
assert.match(memoPage, /block\?\.querySelector\("pre"\)\?\.textContent/,
  "memo copy must extract only the matching fenced code block text");
assert.match(memoPage, /navigator\.clipboard\.writeText\(code\)/,
  "memo code copy must use the Clipboard API");
assert.doesNotMatch(memoRenderer, /onclick=/i,
  "renderer markup must not include inline JavaScript");

console.log("Clipboard and key layout contracts passed.");
