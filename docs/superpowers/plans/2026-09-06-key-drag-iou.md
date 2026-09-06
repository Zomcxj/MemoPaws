# Key Drag IoU Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require IoU greater than 0.4 before highlighting or reordering a dragged key card, and reduce LLM card title size.

**Architecture:** Keep the existing pointer-drag state and reorder protocol. Replace the asymmetric overlap test in `movePointerDrag` with a symmetric rectangle IoU test for both key types; retain the existing nearest-target selection for LLM cards and directional insertion for secret rows.

**Tech Stack:** React, TypeScript, CSS, Tauri invoke reorder command.

## Global Constraints

- IoU threshold is strict: `IoU > 0.4`.
- No reorder is submitted when no target passes the threshold.
- LLM cards continue to swap positions; secret rows continue to insert by drag direction.
- Only the LLM card title such as `openai/gpt-4o` changes from `16px` to `13px`.
- Do not change key data or the backend reorder protocol.

---

### Task 1: IoU Drag Targeting and Title Size

**Files:**
- Modify: `frontend/src/pages/KeysPage.tsx:486-532` — replace overlap threshold with IoU calculation for each candidate.
- Modify: `frontend/src/pages/KeysPage.css:176-181` — reduce `.key-card-llm h3` font size.
- Test: existing frontend key interaction contracts under `frontend/e2e/`.

**Interfaces:**
- Consumes: existing `pointerDrag`, `dragging`, `overId`, `commitDrag`, and DOM rectangles.
- Produces: `targetId` only when the moved card and candidate card have `intersectionArea / unionArea > 0.4`; existing `commitDrag` consumes the unchanged drag shape.

- [ ] **Step 1: Replace both overlap checks with IoU checks**

For each candidate row, calculate its area and intersection area. Skip the candidate when the union is zero or the IoU is at most `0.4`:

```ts
const targetArea = rect.width * rect.height;
const overlapWidth = Math.max(0, Math.min(movedRect.right, rect.right) - Math.max(movedRect.left, rect.left));
const overlapHeight = Math.max(0, Math.min(movedRect.bottom, rect.bottom) - Math.max(movedRect.top, rect.top));
const overlapArea = overlapWidth * overlapHeight;
const unionArea = dragArea + targetArea - overlapArea;
if (unionArea === 0 || overlapArea / unionArea <= 0.4) continue;
```

Use the same calculation in the LLM and secret candidate loops. Keep the LLM distance comparison and secret `insertAfter` calculation unchanged.

- [ ] **Step 2: Reduce the LLM card title size**

Change only this declaration in `frontend/src/pages/KeysPage.css`:

```css
.key-card-llm h3 {
  font-size: 13px;
}
```

Keep the existing margin, weight, color, and wrapping rules.

- [ ] **Step 3: Verify the source contract**

Run:

```bash
cd frontend
npx tsc --noEmit
node e2e/test-key-interaction-refinement.cjs
```

Expected: TypeScript exits successfully; the key interaction contract passes and no old half-area threshold remains in `KeysPage.tsx`.

- [ ] **Step 4: Run the required test subagent**

Dispatch the `testing` agent to run the relevant frontend tests and report failures without modifying unrelated files. If it is interrupted, retry with the configured fallback testing agent according to the workspace rules.

- [ ] **Step 5: Commit the implementation**

```bash
git add frontend/src/pages/KeysPage.tsx frontend/src/pages/KeysPage.css
git commit -m "fix: require IoU threshold for key card dragging"
```

- [ ] **Step 6: Export the NSIS installer**

```bash
RUST_MIN_STACK=67108864 CARGO_BUILD_JOBS=2 npm --prefix frontend exec -- tauri build --bundles nsis
```

Expected: `target/release/bundle/nsis/MemoPaws_0.1.0_x64-setup.exe` is produced.
