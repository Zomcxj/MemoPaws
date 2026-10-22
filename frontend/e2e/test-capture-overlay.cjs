// Focused browser regression test for editable capture selections and for the
// save/pin flows that fan out of the capture overlay.
//
// Contract under test: capture_screen answers with the raw PNG bytes of the
// screen (Tauri ipc Response), the frontend decodes them once into the overlay
// background and crops on a native canvas — so no overlay action may call
// image_crop, and a pending save hides the window until it settles.
//
// Usage: keep `npm --prefix frontend run dev` running on http://localhost:1420, then
//   node frontend/e2e/test-capture-overlay.cjs
//
// Each flow runs in its own browser context and is reported separately, so a red
// baseline lists every expected failure instead of stopping at the first one.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE_URL = process.env.MEMOPAWS_BASE_URL || "http://localhost:1420";
const MOCK_SCRIPT = fs.readFileSync(path.join(__dirname, "mock-tauri.js"), "utf-8");

// A real, fully opaque PNG generated in the page, served for get_pinned_image so
// PinPage renders an <img> the transparency checks can inspect. image_crop is
// already answered with a decodable PNG by mock-tauri.js.
const PIN_IMAGE_SCRIPT = `
  (function () {
    let cached = null;
    function png() {
      if (!cached) {
        const canvas = document.createElement("canvas");
        canvas.width = 128;
        canvas.height = 96;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "rgb(18,52,86)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        const binary = atob(canvas.toDataURL("image/png").split(",")[1]);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        cached = bytes;
      }
      return cached;
    }
    const original = window.__TAURI_INTERNALS__.invoke;
    window.__TAURI_INTERNALS__.invoke = function (command, payload) {
      if (command === "get_pinned_image") {
        window.__MOCK_TAURI_COMMAND_CALLS__.push({ command: command, args: payload || null, visible: true });
        return Promise.resolve([Array.from(png()), 16]);
      }
      return original.call(this, command, payload);
    };
  })();
`;

// save_image_as stays pending until the test settles it, so the overlay's
// in-flight state can be observed instead of racing a 10ms mock reply.
// settle() reports "nothing pending" instead of throwing so a flow can still
// report every problem it found in one message. The three outcomes mirror the
// real dialog: reject (fs error), cancel (Ok(None)), success (a path).
const CONTROLLED_SAVE_SCRIPT = `
  (function () {
    const original = window.__TAURI_INTERNALS__.invoke;
    const pending = [];
    window.__TEST_SAVE_SETTLE__ = function (outcome, message) {
      const next = pending.shift();
      if (!next) return false;
      if (outcome === "reject") next.reject(new Error(message || "Mock save failed"));
      else if (outcome === "success") next.resolve("C:/mock/saved.png");
      else next.resolve(null);
      return true;
    };
    window.__TAURI_INTERNALS__.invoke = function (command, payload) {
      if (command === "save_image_as") {
        window.__MOCK_TAURI_COMMAND_CALLS__.push({ command: command, args: payload || null, visible: window.__MOCK_TAURI_IS_VISIBLE__() });
        return new Promise(function (resolve, reject) { pending.push({ resolve: resolve, reject: reject }); });
      }
      return original.call(this, command, payload);
    };
  })();
`;

// Tauri's postMessage fallback answers capture_screen with a plain number[]
// array instead of an ArrayBuffer (the same bytes, JSON-serialized). Production
// has to decode that shape too, or the first screenshot after the fallback dies
// with a decode error and the overlay never opens.
const NUMBER_ARRAY_CAPTURE_SCRIPT = `
  (function () {
    const original = window.__TAURI_INTERNALS__.invoke;
    window.__TAURI_INTERNALS__.invoke = function (command, payload) {
      const result = original.call(this, command, payload);
      if (command !== "capture_screen") return result;
      return Promise.resolve(result).then(function (bytes) { return Array.from(new Uint8Array(bytes)); });
    };
  })();
`;

// Every flow opens the overlay the same way. A capture_screen that does not
// hand over raw PNG bytes leaves the frontend with no background to decode, so
// the crop and save assertions below it would silently never run.
async function waitForOverlay(page) {
  const overlay = page.locator(".capture-overlay");
  const shown = await overlay.waitFor({ state: "visible", timeout: 10000 }).then(() => true).catch(() => false);
  if (!shown) throw new Error("capture overlay never rendered: capture_screen must resolve raw PNG bytes instead of {image, preview}, so this flow's crop and save assertions never ran");
  const natural = await page.evaluate(() => {
    const image = document.querySelector(".capture-overlay img");
    return image ? [image.naturalWidth, image.naturalHeight] : null;
  });
  if (!natural || natural[0] !== 1280 || natural[1] !== 720) {
    throw new Error(`overlay background must decode to the full 1280x720 screenshot, saw ${JSON.stringify(natural)}`);
  }
  return overlay;
}

const imageCropCalls = (page) =>
  page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === "image_crop").length);

// Decodes the exact PNG handed to ai_ocr so the assertions below can tell a
// real crop of the selection apart from any bytes at all.
async function readOcrImage(page) {
  await page.waitForFunction(
    () => window.__MOCK_TAURI_COMMAND_CALLS__.some((call) => call.command === "ai_ocr"),
    null,
    { timeout: 5000 },
  ).catch(() => {});
  return page.evaluate(async () => {
    const call = window.__MOCK_TAURI_COMMAND_CALLS__.filter((entry) => entry.command === "ai_ocr").at(-1);
    const image = call && call.args && call.args.image;
    if (!Array.isArray(image)) return { error: "ai_ocr was never invoked with image bytes" };
    let bitmap;
    try {
      bitmap = await createImageBitmap(new Blob([new Uint8Array(image)], { type: "image/png" }));
    } catch (reason) {
      return { error: `ai_ocr bytes are not a decodable PNG (${reason && reason.message})` };
    }
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d");
    context.drawImage(bitmap, 0, 0);
    const pixel = context.getImageData(bitmap.width >> 1, bitmap.height >> 1, 1, 1).data;
    const size = { width: bitmap.width, height: bitmap.height, pixel: [pixel[0], pixel[1], pixel[2], pixel[3]] };
    bitmap.close();
    return size;
  });
}

async function withPage(browser, initScripts, flow) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await context.newPage();
  try {
    for (const script of initScripts) await page.addInitScript(script);
    await flow(page);
  } finally {
    await context.close();
  }
}

async function drag(page, from, to) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y);
  await page.mouse.up();
}

// Reports the overlay's live state and the exact call site when a cancel/confirm
// fails to dismiss it, so a regression names its step instead of a bare timeout.
async function waitForDetach(page) {
  try {
    await page.locator(".capture-overlay").waitFor({ state: "detached", timeout: 30000 });
  } catch (error) {
    const callSite = String(error.stack || "").split("\n")[2] || "unknown";
    const state = await page.evaluate(() => ({
      live: document.querySelector(".capture-overlay .capture-overlay-live")?.textContent || "",
      resultError: document.querySelector(".capture-overlay [role=alert]")?.textContent || "",
      busyButton: Array.from(document.querySelectorAll(".capture-overlay button")).some((button) => button.disabled),
      windowCalls: window.__MOCK_TAURI_WINDOW_CALLS__.slice(-8).map((call) => call.command),
    })).catch(() => null);
    throw new Error(`overlay did not detach (called from ${callSite.trim()}): ${JSON.stringify(state)}`);
  }
}

async function captureOverlayFlow(browser) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await context.newPage();
  await page.addInitScript(MOCK_SCRIPT);
  await page.goto(BASE_URL, { waitUntil: "networkidle" });

  await page.getByRole("combobox", { name: "显示器" }).selectOption("1");
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("memopaws-capture")));
  const overlay = await waitForOverlay(page);
  let captureCall = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === "capture_screen").at(-1));
  if (!captureCall || captureCall.args.displayIndex !== 1) throw new Error(`Global capture event used a stale display selection: ${JSON.stringify(captureCall)}`);
  let windowCalls = await page.evaluate(() => window.__MOCK_TAURI_WINDOW_CALLS__);
  const hideBeforeCapture = windowCalls.findIndex((call) => call.command === "plugin:window|hide");
  const captureDuringHide = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__.find((call) => call.command === "capture_screen"));
  const showAfterCapture = windowCalls.findIndex((call) => call.command === "plugin:window|show");
  if (hideBeforeCapture < 0 || !captureDuringHide || captureDuringHide.visible || showAfterCapture < 0) {
    throw new Error(`Main window was visible during capture or not shown for the overlay: ${JSON.stringify({ windowCalls, captureDuringHide })}`);
  }
  await page.keyboard.press("Escape");
  await waitForDetach(page);
  windowCalls = await page.evaluate(() => window.__MOCK_TAURI_WINDOW_CALLS__);
  const overlayPosition = windowCalls.find((call) => call.command === "plugin:window|set_position" && call.value?.position?.x === 1280);
  const restoredPosition = windowCalls.find((call) => call.command === "plugin:window|set_position" && call.value?.position?.x === 0 && call.value?.position?.y === 0);
  if (!overlayPosition || !restoredPosition) throw new Error(`Capture window geometry was not set then restored: ${JSON.stringify(windowCalls)}`);

  await page.getByRole("button", { name: "截图" }).click();
  await waitForOverlay(page);
  await drag(page, { x: 100, y: 100 }, { x: 400, y: 300 });

  const selection = page.locator(".capture-overlay-rect");
  await selection.waitFor();
  if (await page.locator(".capture-overlay-handle").count() !== 8) throw new Error("Expected all eight selection resize handles");
  await drag(page, { x: 250, y: 200 }, { x: 300, y: 250 });
  let box = await selection.boundingBox();
  if (!box || Math.round(box.x) !== 150 || Math.round(box.y) !== 150) throw new Error(`Selection did not move by the drag delta: ${JSON.stringify(box)}`);

  const eastHandle = page.locator(".capture-overlay-handle--e");
  if (await eastHandle.count() !== 1) throw new Error("Expected east resize handle");
  const eastBox = await eastHandle.boundingBox();
  if (!eastBox) throw new Error("East resize handle has no box");
  await drag(page, { x: eastBox.x + eastBox.width / 2, y: eastBox.y + eastBox.height / 2 }, { x: 1600, y: eastBox.y + eastBox.height / 2 });
  box = await selection.boundingBox();
  if (!box || Math.round(box.x + box.width) !== 1280) throw new Error("Resize was not clamped to image bounds");

  await overlay.getByRole("button", { name: "AI识别" }).click();
  const resultWindow = page.locator(".capture-result-window");
  await resultWindow.waitFor();
  // The crop must happen on the frontend: ai_ocr receives exactly the live
  // selection cut out of the screenshot, and image_crop stays silent.
  box = await selection.boundingBox();
  if (!box) throw new Error("Selection has no box");
  const cropWidth = Math.round(box.width);
  const cropHeight = Math.round(box.height);
  const ocrImage = await readOcrImage(page);
  if (ocrImage.error) throw new Error(ocrImage.error);
  if (ocrImage.width !== cropWidth || ocrImage.height !== cropHeight) {
    throw new Error(`ai_ocr must receive the ${cropWidth}x${cropHeight} selection, saw ${ocrImage.width}x${ocrImage.height}`);
  }
  // mock-tauri.js paints capture_screen with rgb(x%256, y%256, 64).
  const source = [Math.round(box.x) + (cropWidth >> 1), Math.round(box.y) + (cropHeight >> 1)];
  const expectedPixel = [source[0] % 256, source[1] % 256, 64, 255];
  if (ocrImage.pixel.some((value, index) => value !== expectedPixel[index])) {
    throw new Error(`ai_ocr pixel must come from the selected region, expected ${JSON.stringify(expectedPixel)}, saw ${JSON.stringify(ocrImage.pixel)}`);
  }
  if (await imageCropCalls(page)) throw new Error("AI识别 must crop on the frontend, the image_crop IPC was invoked");
  if (await page.locator(".capture-overlay").count() !== 1) throw new Error("Non-confirm overlay action closed the overlay");
  if (await page.locator(".image-canvas").count() !== 0) throw new Error("Non-confirm overlay action changed the canvas");
  if (await resultWindow.locator("textarea").count() !== 2) throw new Error("Expected vertical OCR and translation result fields");
  const initialResultBox = await resultWindow.boundingBox();
  if (!initialResultBox || Math.round(initialResultBox.width) !== 450 || Math.round(initialResultBox.height) !== 533) {
    throw new Error(`Result window did not start at the Python minimum size: ${JSON.stringify(initialResultBox)}`);
  }
  const titleBox = await resultWindow.locator(".capture-result-window-title").boundingBox();
  if (!titleBox) throw new Error("Result window title bar has no box");
  await drag(page, { x: titleBox.x + 80, y: titleBox.y + 12 }, { x: titleBox.x + 120, y: titleBox.y + 42 });
  const movedResultBox = await resultWindow.boundingBox();
  if (!movedResultBox || Math.round(movedResultBox.x - initialResultBox.x) !== 40 || Math.round(movedResultBox.y - initialResultBox.y) !== 30) {
    throw new Error(`Result window title bar did not move the window: ${JSON.stringify({ initialResultBox, movedResultBox })}`);
  }
  const resultGrip = resultWindow.locator(".capture-result-window-resize");
  const gripBox = await resultGrip.boundingBox();
  if (!gripBox) throw new Error("Result window resize grip has no box");
  await drag(page, { x: gripBox.x + gripBox.width / 2, y: gripBox.y + gripBox.height / 2 }, { x: gripBox.x + 100, y: gripBox.y + 70 });
  const resizedResultBox = await resultWindow.boundingBox();
  if (!resizedResultBox || resizedResultBox.width <= initialResultBox.width || resizedResultBox.height <= initialResultBox.height || resizedResultBox.width > 900 || resizedResultBox.height > 800) {
    throw new Error(`Result window bottom-right resize did not update its size: ${JSON.stringify(resizedResultBox)}`);
  }

  await page.keyboard.press("Escape");
  await waitForDetach(page);
  await page.evaluate(() => { window.__MOCK_TAURI_SET_FULLSCREEN__(true); window.__MOCK_TAURI_WINDOW_CALLS__.length = 0; });
  await page.getByRole("button", { name: "截图" }).click();
  await waitForOverlay(page);
  windowCalls = await page.evaluate(() => window.__MOCK_TAURI_WINDOW_CALLS__);
  const fullscreenCheck = windowCalls.findIndex((call) => call.command === "plugin:window|is_fullscreen");
  const exitFullscreen = windowCalls.findIndex((call) => call.command === "plugin:window|set_fullscreen" && call.value === false);
  const firstGeometryWrite = windowCalls.findIndex((call) => call.command === "plugin:window|set_position" || call.command === "plugin:window|set_size");
  if (fullscreenCheck < 0 || exitFullscreen < 0 || firstGeometryWrite < 0 || !(fullscreenCheck < exitFullscreen && exitFullscreen < firstGeometryWrite)) {
    throw new Error(`Fullscreen was not exited before capture geometry writes: ${JSON.stringify(windowCalls)}`);
  }
  await page.keyboard.press("Escape");
  await waitForDetach(page);
  const restoredFullscreen = await page.evaluate(() => window.__MOCK_TAURI_WINDOW_CALLS__.some((call) => call.command === "plugin:window|set_fullscreen" && call.value === true));
  if (!restoredFullscreen) throw new Error("Fullscreen state was not restored after cancelling capture");

  await page.getByRole("button", { name: "截图" }).click();
  await waitForOverlay(page);
  await drag(page, { x: 100, y: 100 }, { x: 1600, y: 800 });
  box = await selection.boundingBox();
  if (!box || Math.round(box.x) !== 100 || Math.round(box.y) !== 100 || Math.round(box.x + box.width) !== 1280 || Math.round(box.y + box.height) !== 720) {
    throw new Error(`Stored selection was not clamped to screenshot bounds: ${JSON.stringify(box)}`);
  }
  await page.keyboard.press("Escape");
  await waitForDetach(page);
  await page.getByRole("button", { name: "截图" }).click();
  await waitForOverlay(page);
  await drag(page, { x: 400, y: 300 }, { x: 100, y: 100 });
  box = await selection.boundingBox();
  if (!box || Math.round(box.x) !== 100 || Math.round(box.y) !== 100 || Math.round(box.width) !== 300 || Math.round(box.height) !== 200) {
    throw new Error(`New selection was not clamped to screenshot bounds: ${JSON.stringify(box)}`);
  }
  await drag(page, { x: 250, y: 200 }, { x: 300, y: 250 });
  box = await selection.boundingBox();
  if (!box || Math.round(box.x) !== 150 || Math.round(box.y) !== 150) throw new Error(`Reverse selection did not move by the drag delta: ${JSON.stringify(box)}`);

  await overlay.getByRole("button", { name: "确认" }).click();
  await waitForDetach(page);
  if (await imageCropCalls(page)) throw new Error("确认 must crop on the frontend, the image_crop IPC was invoked");
  windowCalls = await page.evaluate(() => window.__MOCK_TAURI_WINDOW_CALLS__);
  const restoreAfterConfirm = windowCalls.filter((call) => call.command === "plugin:window|set_position" && call.value?.position?.x === 0 && call.value?.position?.y === 0).length;
  if (restoreAfterConfirm < 2) throw new Error(`Capture confirmation did not restore the original geometry: ${JSON.stringify(windowCalls)}`);

  // OCR/translate text flow: mock text must reach the result window, and Enter must
  // confirm the latest OCR/translation state rather than a stale closure.
  await page.getByRole("button", { name: "截图" }).click();
  await waitForOverlay(page);
  await drag(page, { x: 100, y: 100 }, { x: 400, y: 300 });
  await overlay.getByRole("button", { name: "AI识别" }).click();
  await page.waitForFunction(() => document.querySelector(".capture-result-window textarea")?.value?.length > 0);
  const ocrField = resultWindow.locator("textarea").first();
  const translateField = resultWindow.locator("textarea").nth(1);
  if ((await ocrField.inputValue()) !== "Mock OCR text") throw new Error(`OCR text did not reach the result window: ${JSON.stringify(await ocrField.inputValue())}`);
  await overlay.getByRole("button", { name: "AI翻译" }).click();
  await page.waitForFunction(() => { const fields = document.querySelectorAll(".capture-result-window textarea"); return fields.length === 2 && Boolean(fields[1].value); });
  if ((await translateField.inputValue()) !== "Mock translation") throw new Error(`Translation text did not reach the result window: ${JSON.stringify(await translateField.inputValue())}`);
  await page.keyboard.press("Enter");
  await waitForDetach(page);
  let mainOcr = await page.locator("textarea[aria-label='AI识别']").inputValue();
  let mainTranslate = await page.locator("textarea[aria-label='AI翻译']").inputValue();
  if (mainOcr !== "Mock OCR text" || mainTranslate !== "Mock translation") throw new Error(`Enter confirmed stale OCR/translation text: ${JSON.stringify({ mainOcr, mainTranslate })}`);

  // A new selection must clear the previous result window and text so a new image
  // cannot be confirmed with old text.
  await page.getByRole("button", { name: "截图" }).click();
  await waitForOverlay(page);
  await drag(page, { x: 100, y: 100 }, { x: 400, y: 300 });
  await overlay.getByRole("button", { name: "AI识别" }).click();
  await page.waitForFunction(() => document.querySelector(".capture-result-window textarea")?.value?.length > 0);
  await drag(page, { x: 900, y: 650 }, { x: 950, y: 690 });
  if (await page.locator(".capture-result-window").count() !== 0) throw new Error("New selection did not clear the previous result window");
  await page.keyboard.press("Enter");
  await waitForDetach(page);
  mainOcr = await page.locator("textarea[aria-label='AI识别']").inputValue();
  mainTranslate = await page.locator("textarea[aria-label='AI翻译']").inputValue();
  if (mainOcr !== "" || mainTranslate !== "") throw new Error(`New selection confirmed with stale OCR/translation text: ${JSON.stringify({ mainOcr, mainTranslate })}`);
  if (await imageCropCalls(page)) throw new Error("No overlay action may call the image_crop IPC");

  await context.close();
}

// The toolbar "保存图片" button and the canvas context menu must both hand the
// bytes to the native save dialog. `anchor.download` never opens a dialog in
// WebView2, so a save that only triggers a browser download is a regression.
async function nativeSaveFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT], async (page) => {
    const sample = fs.readFileSync(path.join(__dirname, "screenshots", "01-recognize.png"));
    const downloads = [];
    page.on("download", () => { downloads.push(Date.now()); });
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.locator(".recognize-toolbar input[type=\"file\"]").setInputFiles({ name: "sample.png", mimeType: "image/png", buffer: sample });
    await page.locator(".image-canvas img").waitFor();
    const saveCalls = () => page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === "save_image_as"));
    const waitForSaveCount = async (count) => {
      await page.waitForFunction(
        (expected) => window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === "save_image_as").length >= expected,
        count,
        { timeout: 3000 },
      ).catch(() => {});
    };

    const problems = [];
    await page.locator(".recognize-toolbar").getByRole("button", { name: "保存图片" }).click();
    await waitForSaveCount(1);
    let calls = await saveCalls();
    if (calls.length !== 1) problems.push(`toolbar save must invoke save_image_as once, saw ${calls.length} call(s)`);
    else if (!Array.isArray(calls[0].args?.image) || calls[0].args.image.length !== sample.length) {
      problems.push(`toolbar save_image_as must carry the imported PNG (${sample.length} bytes), saw ${calls[0].args?.image?.length}`);
    }

    await page.locator(".image-panel").click({ button: "right" });
    await page.locator(".context-menu").waitFor();
    await page.locator(".context-menu").getByRole("menuitem", { name: "保存图片" }).click();
    await waitForSaveCount(2);
    calls = await saveCalls();
    if (calls.length !== 2) problems.push(`context save must invoke save_image_as once, saw ${calls.length} call(s) in total`);
    else if (!Array.isArray(calls[1].args?.image) || calls[1].args.image.length !== sample.length) {
      problems.push(`context save_image_as must carry the imported PNG (${sample.length} bytes), saw ${calls[1].args?.image?.length}`);
    }
    if (downloads.length) problems.push(`save must not fall back to anchor.download, the browser started ${downloads.length} download(s)`);
    if (problems.length) throw new Error(problems.join("; "));
  });
}

// The overlay save has to await save_image_as: show busy while the dialog is
// pending, and render the rejection on the overlay itself (the overlay covers
// the whole screen, so a page-level error bar behind it is invisible).
async function overlaySaveFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT, CONTROLLED_SAVE_SCRIPT], async (page) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "截图" }).click();
    const overlay = await waitForOverlay(page);
    await drag(page, { x: 100, y: 100 }, { x: 400, y: 300 });
    await page.locator(".capture-overlay-rect").waitFor();

    await overlay.getByRole("button", { name: "保存图片" }).click();
    const invoked = await page.waitForFunction(
      () => window.__MOCK_TAURI_COMMAND_CALLS__.some((call) => call.command === "save_image_as"),
      null,
      { timeout: 3000 },
    ).then(() => true).catch(() => false);
    const busySeen = await page.waitForFunction(() => {
      const box = document.querySelector(".capture-overlay");
      if (!box) return false;
      const live = box.querySelector(".capture-overlay-live");
      if (live && live.textContent.includes("处理中")) return true;
      const save = box.querySelector('button[aria-label="保存图片"]');
      return Boolean(save && save.disabled);
    }, null, { timeout: 3000 }).then(() => true).catch(() => false);

    const problems = [];
    if (!invoked) problems.push("overlay save never invoked save_image_as");
    if (!busySeen) problems.push("overlay save showed no busy state while save_image_as was pending");
    if (await imageCropCalls(page)) problems.push("overlay save must crop on the frontend, the image_crop IPC was invoked");

    const settled = await page.evaluate(() => window.__TEST_SAVE_SETTLE__("reject", "Mock save dialog failed"));
    if (!settled) problems.push("overlay save never reached save_image_as, so there was nothing to reject");
    const errorSeen = await page.waitForFunction(() => {
      const box = document.querySelector(".capture-overlay");
      return Boolean(box && box.getClientRects().length && box.textContent.includes("Mock save dialog failed"));
    }, null, { timeout: 3000 }).then(() => true).catch(() => false);
    if (!errorSeen) problems.push("save_image_as rejection was not shown on the overlay");
    if (await overlay.count() !== 1) problems.push("overlay closed after a failed save");
    const busyCleared = await page.waitForFunction(() => {
      const box = document.querySelector(".capture-overlay");
      if (!box) return false;
      const live = box.querySelector(".capture-overlay-live");
      const save = box.querySelector('button[aria-label="保存图片"]');
      const liveBusy = Boolean(live && live.textContent.includes("处理中"));
      return !liveBusy && Boolean(save) && !save.disabled;
    }, null, { timeout: 3000 }).then(() => true).catch(() => false);
    if (!busyCleared) problems.push("overlay stayed busy after save_image_as rejected");

    if (problems.length) throw new Error(problems.join("; "));
  });
}

// The native Save As dialog is modal over its owner (the main window), so it
// renders above the fullscreen overlay while the window itself stays visible.
// Every outcome must keep the overlay mounted, keep the selection, and clear
// the busy state so a rejected or cancelled save can be retried.
async function overlaySaveVisibilityFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT, CONTROLLED_SAVE_SCRIPT], async (page) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "截图" }).click();
    const overlay = await waitForOverlay(page);
    await drag(page, { x: 100, y: 100 }, { x: 400, y: 300 });
    const selection = page.locator(".capture-overlay-rect");
    await selection.waitFor();
    const before = await selection.boundingBox();

    const problems = [];
    for (const outcome of ["reject", "cancel", "success"]) {
      const mark = await page.evaluate(() => ({
        commands: window.__MOCK_TAURI_COMMAND_CALLS__.length,
        windows: window.__MOCK_TAURI_WINDOW_CALLS__.length,
      }));
      await overlay.getByRole("button", { name: "保存图片" }).click();
      const invoked = await page.waitForFunction(
        (from) => window.__MOCK_TAURI_COMMAND_CALLS__.slice(from).some((call) => call.command === "save_image_as"),
        mark.commands,
        { timeout: 3000 },
      ).then(() => true).catch(() => false);
      if (!invoked) {
        problems.push(`${outcome}: save_image_as was never invoked`);
        break;
      }
      const during = await page.evaluate((from) => ({
        save: window.__MOCK_TAURI_COMMAND_CALLS__.slice(from.commands).find((call) => call.command === "save_image_as"),
        windows: window.__MOCK_TAURI_WINDOW_CALLS__.slice(from.windows),
      }), mark);
      if (!during.save || during.save.visible !== true) {
        problems.push(`${outcome}: the window must stay visible so the modal dialog sits above the overlay, saw visible=${during.save && during.save.visible}`);
      }
      if (during.windows.some((call) => call.command === "plugin:window|hide")) {
        problems.push(`${outcome}: the window must not be hidden while the save dialog is open`);
      }

      const settled = await page.evaluate((value) => window.__TEST_SAVE_SETTLE__(value), outcome);
      if (!settled) {
        problems.push(`${outcome}: save_image_as had nothing left to settle`);
        continue;
      }
      const stillVisible = await page.waitForFunction(() => window.__MOCK_TAURI_IS_VISIBLE__(), null, { timeout: 3000 }).then(() => true).catch(() => false);
      if (!stillVisible) problems.push(`${outcome}: the window must stay visible after the save settled`);
      if (await overlay.count() !== 1) problems.push(`${outcome}: the overlay disappeared after the save settled`);
      const after = await selection.boundingBox();
      const geometry = ["x", "y", "width", "height"];
      if (!before || !after || geometry.some((key) => Math.round(after[key]) !== Math.round(before[key]))) {
        problems.push(`${outcome}: the selection was lost after the save settled: ${JSON.stringify({ before, after })}`);
      }
      const retryable = await page.waitForFunction(() => {
        const save = document.querySelector('.capture-overlay button[aria-label="保存图片"]');
        return Boolean(save) && !save.disabled;
      }, null, { timeout: 3000 }).then(() => true).catch(() => false);
      if (!retryable) problems.push(`${outcome}: the save button stayed busy after the save settled`);
    }

    if (problems.length) throw new Error(problems.join("; "));
  });
}

// A pinned selection keeps its rounded corners transparent in the exact bytes
// handed to pin_image; the pin window cannot round a corner that is opaque.
async function pinAlphaFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT, PIN_IMAGE_SCRIPT], async (page) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "截图" }).click();
    const overlay = await waitForOverlay(page);
    await drag(page, { x: 120, y: 120 }, { x: 520, y: 400 });
    await page.locator(".capture-overlay-rect").waitFor();

    const radiusInput = page.locator(".capture-overlay-rect-radius input[type=\"range\"]");
    await radiusInput.evaluate((element) => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(element, "16");
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const radius = Number(await radiusInput.inputValue());
    if (!Number.isFinite(radius) || radius <= 0) throw new Error(`corner radius must be positive before pinning, saw ${radius}`);

    await overlay.getByRole("button", { name: "Pin image" }).click();
    await page.waitForFunction(
      () => window.__MOCK_TAURI_COMMAND_CALLS__.some((call) => call.command === "pin_image"),
      null,
      { timeout: 5000 },
    ).catch(() => {});
    if (await imageCropCalls(page)) throw new Error("钉图 must crop on the frontend, the image_crop IPC was invoked");

    const probe = await page.evaluate(async () => {
      const calls = window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === "pin_image");
      const last = calls[calls.length - 1];
      if (!last || !Array.isArray(last.args?.image)) return { error: "pin_image was never invoked with image bytes" };
      const bytes = new Uint8Array(last.args.image);
      let bitmap;
      try {
        bitmap = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
      } catch (reason) {
        return { error: `pinned bytes are not a decodable PNG (${reason && reason.message})` };
      }
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(bitmap, 0, 0);
      const corner = ctx.getImageData(0, 0, 1, 1).data;
      const centre = ctx.getImageData(bitmap.width >> 1, bitmap.height >> 1, 1, 1).data;
      return { cornerAlpha: corner[3], centreAlpha: centre[3], radius: last.args.radius };
    });

    const problems = [];
    if (probe.error) problems.push(probe.error);
    else {
      if (probe.centreAlpha !== 255) problems.push(`pinned image centre must stay opaque, saw alpha ${probe.centreAlpha}`);
      if (probe.cornerAlpha !== 0) problems.push(`pinned image corner must be transparent after a ${radius}px radius crop, saw alpha ${probe.cornerAlpha}`);
      if (Number(probe.radius) !== 16) problems.push(`pin_image must receive the selection radius, saw ${probe.radius}`);
    }
    if (problems.length) throw new Error(problems.join("; "));

    // 钉图后主窗口必须保持隐藏（"不要出现主界面"），关闭钉图窗口再恢复。
    const hiddenAgain = await page.waitForFunction(() => !window.__MOCK_TAURI_IS_VISIBLE__(), null, { timeout: 5000 }).then(() => true).catch(() => false);
    if (!hiddenAgain) problems.push("main window must stay hidden while the pin is up (no main UI during pin)");
    // 新会话模型：销毁由 __MOCK_TAURI_CLOSE_PIN__ 模拟原生 destroyed 钩子恢复主窗。
    await page.evaluate(() => window.__MOCK_TAURI_CLOSE_PIN__(window.__MOCK_TAURI_PIN_LABELS__()[0]));
    const mainRestored = await page.waitForFunction(() => window.__MOCK_TAURI_IS_VISIBLE__(), null, { timeout: 3000 }).then(() => true).catch(() => false);
    if (!mainRestored) problems.push("main window did not come back after the pin was closed");
    if (problems.length) throw new Error(problems.join("; "));
  });
}

// The pin window renders only PinPage, so no element may paint an opaque page
// background over the transparent webview, and main-window startup work
// (showing the main window, acrylic, update polling, config) must not run.
async function pinWindowFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT, PIN_IMAGE_SCRIPT], async (page) => {
    await page.goto(`${BASE_URL}/#pin`, { waitUntil: "networkidle" });
    await page.locator("img[alt=\"pinned\"]").waitFor({ timeout: 5000 });

    const backgrounds = await page.evaluate(() => {
      const read = (element) => {
        if (!element) return null;
        const style = window.getComputedStyle(element);
        return { backgroundColor: style.backgroundColor, backgroundImage: style.backgroundImage };
      };
      return {
        html: read(document.documentElement),
        body: read(document.body),
        root: read(document.getElementById("root")),
      };
    });
    const alphaOf = (value) => {
      const match = /rgba?\(\s*([\d.]+)\s*[, ]\s*([\d.]+)\s*[, ]\s*([\d.]+)\s*(?:[,/]\s*([\d.]+))?/.exec(value || "");
      if (!match) return null;
      return match[4] === undefined ? 1 : Number(match[4]);
    };
    const problems = [];
    for (const name of ["html", "body", "root"]) {
      const entry = backgrounds[name];
      if (!entry) { problems.push(`${name} element is missing`); continue; }
      const alpha = alphaOf(entry.backgroundColor);
      if (alpha === null) problems.push(`${name} has an unparsable background: ${entry.backgroundColor}`);
      else if (alpha !== 0) problems.push(`${name} background must be transparent, saw ${entry.backgroundColor}`);
      if (entry.backgroundImage && entry.backgroundImage !== "none") problems.push(`${name} paints a background image: ${entry.backgroundImage}`);
    }

    const commands = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__.map((call) => call.command));
    if (!commands.includes("get_pinned_image")) problems.push("pin window never asked for its image");
    for (const forbidden of ["show_main_window_when_ready", "set_glass_effect", "latest_release_version", "get_config"]) {
      if (commands.includes(forbidden)) problems.push(`pin window must not run the main-only startup command ${forbidden}`);
    }
    if (problems.length) throw new Error(problems.join("; "));
  });
}

// The postMessage IPC fallback hands capture_screen back as number[] instead of
// an ArrayBuffer. The overlay must still open on that shape; when it does not,
// the failure reports the exact decode error production hit.
async function captureFallbackFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT, NUMBER_ARRAY_CAPTURE_SCRIPT], async (page) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "截图" }).click();
    const opened = await page.locator(".capture-overlay")
      .waitFor({ state: "visible", timeout: 10000 })
      .then(() => true)
      .catch(() => false);
    if (!opened) {
      const probe = await page.evaluate(async () => {
        const bytes = await window.__TAURI_INTERNALS__.invoke("capture_screen", {});
        let decode;
        try {
          await createImageBitmap(new Blob([bytes], { type: "image/png" }));
          decode = "ok";
        } catch (reason) {
          decode = String((reason && reason.message) || reason);
        }
        return {
          isArray: Array.isArray(bytes),
          decode,
          uiError: Array.from(document.querySelectorAll("[role=alert]"))
            .map((node) => node.textContent)
            .filter(Boolean)
            .join(" | "),
        };
      });
      throw new Error(`capture_screen number[] fallback must still open the overlay, production failed to decode it: ${JSON.stringify(probe)}`);
    }
    await waitForOverlay(page);
    await page.keyboard.press("Escape");
    await waitForDetach(page);
  });
}

// Multi-pin session rules: pins taken while the main window was visible keep
// that origin; closing a non-last pin never restores, the last close does, and
// a close that lands during a pending capture only settles at session finish.
async function multiPinSessionFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT, PIN_IMAGE_SCRIPT], async (page) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    const isVisible = () => page.evaluate(() => window.__MOCK_TAURI_IS_VISIBLE__());
    const labels = () => page.evaluate(() => window.__MOCK_TAURI_PIN_LABELS__());
    const closePin = (label) => page.evaluate((target) => window.__MOCK_TAURI_CLOSE_PIN__(target), label);
    const capture = () => page.evaluate(() => window.dispatchEvent(new CustomEvent("memopaws-capture")));
    const pinSelection = async (from, to) => {
      await drag(page, from, to);
      const overlay = page.locator(".capture-overlay");
      await overlay.getByRole("button", { name: "Pin image" }).click();
      await page.locator(".capture-overlay").waitFor({ state: "detached", timeout: 30000 });
    };
    const problems = [];

    // Scenario A: visible origin — hidden stays hidden until the last pin closes.
    await page.getByRole("button", { name: "截图" }).click();
    await waitForOverlay(page);
    await pinSelection({ x: 100, y: 100 }, { x: 400, y: 300 });
    if (await isVisible()) problems.push("A: main window must stay hidden after the first pin");
    await capture();
    await waitForOverlay(page);
    await pinSelection({ x: 500, y: 120 }, { x: 800, y: 400 });
    if ((await labels()).length !== 2) problems.push(`A: expected two independent pins, saw ${JSON.stringify(await labels())}`);
    await closePin("pin-1");
    if (await isVisible()) problems.push("A: closing a non-last pin must not restore the main window");
    await closePin("pin-2");
    if (!(await isVisible())) problems.push("A: closing the last pin must restore the main window");

    // Scenario B: hidden origin — even the last close must stay hidden.
    await page.evaluate(() => window.__TAURI_INTERNALS__.invoke("plugin:window|hide"));
    await page.getByRole("button", { name: "截图" }).click();
    await waitForOverlay(page);
    await pinSelection({ x: 100, y: 100 }, { x: 400, y: 300 });
    await closePin("pin-3");
    if (await isVisible()) problems.push("B: a hidden-origin pin must stay hidden after its last close");

    // Scenario C: closing the last pin during a pending capture must not fire a
    // stale restore; only the capture session finish settles visibility.
    await page.getByRole("button", { name: "截图" }).click();
    await waitForOverlay(page);
    await closePin("pin-3");
    if ((await labels()).length !== 0) problems.push("C: pin registry must be empty after the last close");
    await page.keyboard.press("Escape");
    await waitForDetach(page);
    if (!(await isVisible())) problems.push("C: cancel finish must settle the pending restoration");
    if (problems.length) throw new Error(problems.join("; "));
  });
}

const FLOWS = [
  ["capture overlay selection flow", captureOverlayFlow],
  ["multi-pin session visibility rules", multiPinSessionFlow],
  ["toolbar/context save uses native save_image_as", nativeSaveFlow],
  ["overlay save busy and error on the overlay", overlaySaveFlow],
  ["overlay save hides the window and restores it", overlaySaveVisibilityFlow],
  ["pinned image keeps transparent corners", pinAlphaFlow],
  ["#pin window transparency and startup", pinWindowFlow],
  ["capture_screen number[] fallback still decodes", captureFallbackFlow],
];

async function run() {
  const browser = await chromium.launch({ headless: true });
  const failures = [];
  for (const [name, flow] of FLOWS) {
    try {
      await flow(browser);
      console.log(`PASS ${name}`);
    } catch (error) {
      failures.push(name);
      console.error(`FAIL ${name}: ${error.message}`);
    }
  }
  await browser.close();
  if (failures.length) {
    console.error(`${failures.length} of ${FLOWS.length} flows failed: ${failures.join(", ")}`);
    process.exit(1);
  }
  console.log(`all ${FLOWS.length} flows passed`);
}

run().catch((error) => { console.error(error); process.exit(1); });
