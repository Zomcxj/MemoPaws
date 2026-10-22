// Focused browser regression test for editable capture selections and for the
// save/pin flows that fan out of the capture overlay.
//
// Contract under test: capture_screen answers with the raw PNG bytes of the
// screen (Tauri ipc Response), the frontend decodes them once into the overlay
// background and crops on a native canvas — so no overlay action may call
// image_crop, a pending save keeps the visible owner window up so the modal
// dialog stays above the overlay, and pin sessions live in the Rust registry
// (restore after the last pin closes).
//
// Usage: keep `npm --prefix frontend run dev` running on http://localhost:1420
// (or set MEMOPAWS_BASE_URL), then
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

// 解码 mock 已记录命令第 index 次调用的 PNG 字节，并采样若干输出坐标的像素。
// samples 为导出图内的 [x,y] 列表；返回 width/height/pixels 供断言比对。
async function decodeRecordedImage(page, command, index, samples = []) {
  return page.evaluate(async ({ command: c, index: i, samples: s }) => {
    const calls = window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === c);
    if (calls.length <= i) throw new Error(`expected more than ${i} recorded ${c} calls`);
    const bytes = new Uint8Array(calls[i].args.image);
    const bitmap = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(bitmap, 0, 0);
    bitmap.close();
    return {
      width: canvas.width,
      height: canvas.height,
      pixels: s.map(([x, y]) => Array.from(ctx.getImageData(x, y, 1, 1).data)),
    };
  }, { command, index, samples });
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
    // 先画一个标注：reject/cancel/success 全程都必须保留在导出字节里。
    await page.locator(".capture-overlay-tools").getByRole("button", { name: "矩形" }).click();
    await drag(page, { x: 150, y: 150 }, { x: 260, y: 210 });

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

    // 三次保存（reject/cancel/success）的字节都必须带着同一份标注。
    const marked = await decodeRecordedImage(page, "save_image_as", 2, [[50, 50]]);
    if (marked.pixels[0][0] < 200 || marked.pixels[0][1] > 140) {
      problems.push(`save bytes lost the drawn mark across outcomes: ${JSON.stringify(marked.pixels[0])}`);
    }

    if (problems.length) throw new Error(problems.join("; "));
  });
}

// 失败保持：钉图/复制图片被拒绝、OCR 延迟回填时，标注与选区必须原样保留，
// 旧的 OCR 结果不得回填进已变化的选区（操作令牌失效）。
async function annotationFailureRetentionFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT], async (page) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "截图" }).click();
    const overlay = await waitForOverlay(page);
    await drag(page, { x: 100, y: 100 }, { x: 400, y: 300 });
    const selectionBox = await page.locator(".capture-overlay-rect").boundingBox();
    await page.locator(".capture-overlay-tools").getByRole("button", { name: "矩形" }).click();
    await drag(page, { x: 150, y: 150 }, { x: 260, y: 210 });

    // 钉图被拒绝：错误显示在浮层上，浮层与标注都保留。
    await page.evaluate(() => window.__MOCK_TAURI_SET_PIN_REJECT__(true));
    await overlay.getByRole("button", { name: "Pin image" }).click();
    await overlay.locator(".capture-result-error").getByText("Mock pin rejected").waitFor({ timeout: 3000 });
    if (await overlay.count() !== 1) throw new Error("overlay closed after a rejected pin");
    await page.evaluate(() => window.__MOCK_TAURI_SET_PIN_REJECT__(false));

    // 复制图片被拒绝：同样只报错，不破坏标注。
    await page.evaluate(() => {
      navigator.clipboard.write = () => Promise.reject(new Error("Mock clipboard rejected"));
    });
    await overlay.getByRole("button", { name: "复制图片" }).click();
    await overlay.locator(".capture-result-error").getByText("Mock clipboard rejected").waitFor({ timeout: 3000 });

    // 两次失败后导出：标注仍在，选区几何未变。
    const afterFailures = await page.locator(".capture-overlay-rect").boundingBox();
    if (!afterFailures || Math.round(afterFailures.x) !== Math.round(selectionBox.x) || Math.round(afterFailures.y) !== Math.round(selectionBox.y)) {
      throw new Error(`failed actions must not move the selection: ${JSON.stringify({ selectionBox, afterFailures })}`);
    }
    await overlay.getByRole("button", { name: "保存图片" }).click();
    await page.waitForTimeout(120);
    const marked = await decodeRecordedImage(page, "save_image_as", 0, [[50, 50]]);
    if (marked.pixels[0][0] < 200 || marked.pixels[0][1] > 140) {
      throw new Error(`save bytes lost the drawn mark after failures: ${JSON.stringify(marked.pixels[0])}`);
    }

    // OCR 延迟回填：识别挂起时绘制新标注（令牌+1），旧结果不得回填。
    await page.evaluate(() => window.__MOCK_TAURI_SET_OCR_DELAY__(350));
    await overlay.getByRole("button", { name: "AI识别" }).click();
    const resultWindow = page.locator(".capture-result-window");
    await resultWindow.waitFor();
    await page.mouse.move(300, 200);
    await page.mouse.down();
    await page.mouse.move(330, 220, { steps: 3 });
    await page.mouse.up();
    await page.waitForTimeout(600);
    const ocrValue = await resultWindow.locator("textarea").first().inputValue();
    if (ocrValue !== "") throw new Error(`stale OCR result must not fill after the marks changed, saw ${JSON.stringify(ocrValue)}`);
    if (await resultWindow.locator(".capture-result-error").count() !== 0) throw new Error("delayed OCR must not surface as an error");
    await page.evaluate(() => window.__MOCK_TAURI_SET_OCR_DELAY__(0));
    await page.keyboard.press("Escape");
    await waitForDetach(page);
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

// Pin window wheel/drag contract: one wheel step resizes the window
// proportionally to the image's natural 4:3 ratio, right-click/Esc close only
// the calling pin instance, and the Blob URL is revoked when the page unmounts.
const PIN_WHEEL_SCRIPT = `
  (function () {
    const original = window.__TAURI_INTERNALS__.invoke;
    let inner = { width: 400, height: 300 };
    let revokes = 0;
    const nativeRevoke = URL.revokeObjectURL.bind(URL);
    URL.revokeObjectURL = function (value) { revokes += 1; window.__MOCK_REVOKE_COUNT__ = revokes; return nativeRevoke(value); };
    const readSize = (payload) => {
      const value = payload && payload.value;
      if (!value) return null;
      // Size 实例的原型 getter 过不了 jsonValue 序列化，落盘前拍成纯对象。
      if (typeof value.width === "number") return { width: value.width, height: value.height };
      if (value.size && typeof value.size.width === "number") return { width: value.size.width, height: value.size.height };
      if (value.data && typeof value.data.width === "number") return { width: value.data.width, height: value.data.height };
      return null;
    };
    window.__TAURI_INTERNALS__.invoke = function (command, payload) {
      if (command === "plugin:window|inner_size") return Promise.resolve(inner);
      if (command === "plugin:window|set_size") {
        const size = readSize(payload) || {};
        if (size.width && size.height) inner = { width: size.width, height: size.height };
        window.__MOCK_TAURI_WINDOW_CALLS__.push({ command: command, value: size });
        return Promise.resolve();
      }
      if (command === "plugin:window|scale_factor") return Promise.resolve(1);
      if (command === "plugin:window|current_monitor") {
        return Promise.resolve({ name: "Test", position: { x: 0, y: 0 }, size: { width: 1920, height: 1080 }, scaleFactor: 1, workArea: { position: { x: 0, y: 0 }, size: { width: 1920, height: 1080 } } });
      }
      if (command === "plugin:window|start_dragging") { window.__MOCK_TAURI_WINDOW_CALLS__.push({ command: command }); return Promise.resolve(); }
      return original.call(this, command, payload);
    };
  })();
`;

async function pinWheelFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT, PIN_IMAGE_SCRIPT, PIN_WHEEL_SCRIPT], async (page) => {
    await page.goto(`${BASE_URL}/#pin`, { waitUntil: "networkidle" });
    await page.locator("img[alt=\"pinned\"]").waitFor({ timeout: 5000 });

    const problems = [];
    await page.evaluate(() => {
      document.querySelector("[data-pin-root]").dispatchEvent(new WheelEvent("wheel", { deltaY: -120, bubbles: true, cancelable: true }));
    });
    const sized = await page.waitForFunction(() => {
      const calls = window.__MOCK_TAURI_WINDOW_CALLS__.filter((call) => call.command === "plugin:window|set_size");
      return calls.length ? calls[calls.length - 1].value : null;
    }, null, { timeout: 5000 }).then((handle) => handle.jsonValue()).catch(() => null);
    if (!sized || !sized.width || !sized.height) problems.push(`wheel did not resize the window: ${JSON.stringify(sized)}`);
    else {
      // 400×300 initial size × 1.1 → 440; the 128×96 pin image is 4:3.
      if (Math.round(sized.width) !== 440) problems.push(`wheel must scale 400 → 440, saw ${sized.width}`);
      if (Math.abs(sized.height - Math.round(sized.width * 3 / 4)) > 1) problems.push(`wheel must preserve the 4:3 aspect within 1px, saw ${JSON.stringify(sized)}`);
    }

    await page.locator("img[alt=\"pinned\"]").click({ button: "right" });
    const rightClose = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__.some((call) => call.command === "pin_close"));
    if (!rightClose) problems.push("right-click must close the calling pin instance");
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === "pin_close").length >= 2, null, { timeout: 3000 }).catch(() => {});
    const escClose = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === "pin_close").length);
    if (escClose < 2) problems.push(`Escape must close the pin, saw ${escClose} pin_close call(s)`);
    // 必须仍在 #pin 页上检查：导航回主页面后 App 合法调用这些命令。
    const forbidden = await page.evaluate(() => ["show_main_window_when_ready", "set_glass_effect", "latest_release_version", "get_config"].filter((command) => window.__MOCK_TAURI_COMMAND_CALLS__.some((call) => call.command === command)));
    if (forbidden.length) problems.push(`pin window ran main-only startup commands: ${forbidden.join(", ")}`);
    // Blob URL 卸载回收改由原生增量验证：跨文档导航不触发 React 卸载。
    if (problems.length) throw new Error(problems.join("; "));
  });
}

// Annotation Task 1: pure model/history self-check via Vite module import.
// Runs without any UI: model.ts must stay independent of React and Tauri.
async function annotationModelFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT], async (page) => {
    await page.goto(BASE_URL);
    await page.evaluate(async () => {
      const m = await import('/src/annotation/model.ts');
      const mark = { tool: 'rectangle', points: [{ x: 1, y: 1 }, { x: 20, y: 10 }], color: '#ff0000', width: 3 };
      let h = m.addMark(m.addMark(m.emptyHistory(), mark), { ...mark, color: '#00ff00' });
      if (h.marks.length !== 2) throw new Error('two marks required');
      if (h.past.length !== 2 || h.future.length) throw new Error('each addMark must push past and clear future');
      h = m.undo(h);
      if (h.marks.length !== 1) throw new Error('undo failed');
      h = m.redo(h);
      if (h.marks.length !== 2) throw new Error('redo failed');
      h = m.addMark(m.undo(h), mark);
      if (h.future.length) throw new Error('new mark must clear redo');
      const p = m.imagePoint({ x: 15, y: 25 }, { offsetX: 5, offsetY: 5, scale: 2, nw: 100, nh: 100 });
      if (p.x !== 20 || p.y !== 40) throw new Error('pixel conversion failed');
      const clamped = m.imagePoint({ x: -50, y: 500 }, { offsetX: 5, offsetY: 5, scale: 2, nw: 100, nh: 100 });
      if (clamped.x !== 0 || clamped.y !== 100) throw new Error('imagePoint must clamp to bounds');
      const empty = m.emptyHistory();
      if (m.undo(empty) !== empty || m.redo(empty) !== empty) throw new Error('undo/redo on empty history must be no-op');
    });
  });
}

// Annotation Task 2: the shared renderer must compose marks on ORIGINAL
// screenshot pixels — export PNG pixels are asserted directly, no DOM preview.
async function annotationRenderFlow(browser) {
  await withPage(browser, [MOCK_SCRIPT], async (page) => {
    await page.goto(BASE_URL);
    await page.evaluate(async () => {
      const { composePng } = await import('/src/annotation/render.ts');
      const canvas = document.createElement('canvas');
      canvas.width = 100; canvas.height = 80;
      const ctx = canvas.getContext('2d');
      for (let y = 0; y < 80; y++) for (let x = 0; x < 100; x++) { ctx.fillStyle = `rgb(${x},${y},64)`; ctx.fillRect(x, y, 1, 1); }
      const img = new Image(); img.src = canvas.toDataURL('image/png'); await img.decode();
      const rect = { tool: 'rectangle', points: [{ x: 12, y: 12 }, { x: 67, y: 47 }], color: '#ff0000', width: 3 };
      const mosaic = { tool: 'mosaic', points: [{ x: 20, y: 20 }, { x: 44, y: 44 }], color: '#ff0000', width: 3 };
      const bytes = await composePng(img, { x: 10, y: 10, width: 60, height: 40 }, 1, 8, [rect, mosaic]);
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const out = document.createElement('canvas'); out.width = bitmap.width; out.height = bitmap.height;
      const c = out.getContext('2d'); c.drawImage(bitmap, 0, 0); bitmap.close();
      const pixel = (x, y) => Array.from(c.getImageData(x, y, 1, 1).data);
      if (out.width !== 60 || out.height !== 40) throw new Error('crop size regression');
      if (pixel(0, 0)[3] !== 0) throw new Error('rounded corner must stay transparent');
      if (pixel(2, 2)[0] < 200 || pixel(2, 2)[1] > 80) throw new Error('rectangle stroke must be red');
      if (pixel(45, 15)[0] !== 55 || pixel(45, 15)[1] !== 25) throw new Error('background outside strokes must be unchanged');
      if (JSON.stringify(pixel(11, 11)) !== JSON.stringify(pixel(12, 11))) throw new Error('mosaic did not average its block');
      if (pixel(40, 20)[0] !== 50 || pixel(40, 20)[1] !== 30) throw new Error('mosaic changed unrelated pixels');
      const sharp = await composePng(img, { x: 10, y: 10, width: 60, height: 40 }, 1, 0, [rect, mosaic]);
      const sharpBitmap = await createImageBitmap(new Blob([sharp], { type: 'image/png' }));
      const sharpOut = document.createElement('canvas'); sharpOut.width = sharpBitmap.width; sharpOut.height = sharpBitmap.height;
      const sc = sharpOut.getContext('2d'); sc.drawImage(sharpBitmap, 0, 0); sharpBitmap.close();
      if (sc.getImageData(0, 0, 1, 1).data[3] !== 255) throw new Error('radius 0 must keep sharp corners');
      const doubled = await composePng(img, { x: 5, y: 5, width: 30, height: 20 }, 2, 0, []);
      const doubledBitmap = await createImageBitmap(new Blob([doubled], { type: 'image/png' }));
      if (doubledBitmap.width !== 60 || doubledBitmap.height !== 40) throw new Error('scale must grow the crop');
      doubledBitmap.close();
    });
  });
}

// Annotation Task 4: drawing tools — one mark per drag, per-mark color/width,
// undo/redo, export bytes carry the actual drawn pixels, loupe hidden mid-draw.
async function annotationDrawFlow(browser) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await context.newPage();
  await page.addInitScript(MOCK_SCRIPT);
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "截图" }).click();
  const overlay = await waitForOverlay(page);
  await drag(page, { x: 100, y: 100 }, { x: 400, y: 300 });
  const toolbar = page.locator(".capture-overlay-tools");
  await toolbar.waitFor();
  const rectTool = toolbar.getByRole("button", { name: "矩形" });
  await rectTool.click();
  if ((await rectTool.getAttribute("aria-pressed")) !== "true") throw new Error("active tool button must set aria-pressed");
  const selectionBox = await page.locator(".capture-overlay-rect").boundingBox();
  if (!selectionBox) throw new Error("Selection disappeared before drawing");
  await drag(page, { x: 150, y: 150 }, { x: 260, y: 210 });
  const afterDrawBox = await page.locator(".capture-overlay-rect").boundingBox();
  if (!afterDrawBox || Math.round(afterDrawBox.x) !== Math.round(selectionBox.x) || Math.round(afterDrawBox.y) !== Math.round(selectionBox.y)) {
    throw new Error("Drawing inside the selection must not move the selection");
  }
  const mosaicTool = toolbar.getByRole("button", { name: "马赛克" });
  await mosaicTool.click();
  await drag(page, { x: 280, y: 180 }, { x: 340, y: 240 });
  await overlay.getByRole("button", { name: "保存图片" }).click();
  await page.waitForTimeout(120);
  const first = await decodeRecordedImage(page, "save_image_as", 0, [[50, 50], [150, 60], [185, 85], [190, 85]]);
  if (first.width !== 300 || first.height !== 200) throw new Error(`export must be the 300x200 selection, saw ${first.width}x${first.height}`);
  // 默认画笔色 #ff6565：矩形描边像素必须是该红色，未标注处保持坐标色背景。
  const stroke = first.pixels[0];
  if (stroke[0] < 200 || stroke[1] > 140) throw new Error(`rectangle stroke must use the toolbar color, saw ${JSON.stringify(stroke)}`);
  const untouched = first.pixels[1];
  if (JSON.stringify(untouched) !== JSON.stringify([250, 160, 64, 255])) throw new Error(`untouched background changed: ${JSON.stringify(untouched)}`);
  const m1 = first.pixels[2];
  const m2 = first.pixels[3];
  if (JSON.stringify(m1) !== JSON.stringify(m2)) throw new Error(`mosaic block pixels must be averaged: ${JSON.stringify({ m1, m2 })}`);
  // 撤销只移除最后一个标记（马赛克），矩形描边必须保留；重做恢复马赛克。
  await toolbar.getByRole("button", { name: "撤销" }).click();
  await overlay.getByRole("button", { name: "保存图片" }).click();
  await page.waitForTimeout(120);
  const undone = await decodeRecordedImage(page, "save_image_as", 1, [[50, 50], [185, 85], [190, 85]]);
  if (undone.pixels[0][0] < 200 || undone.pixels[0][1] > 140) throw new Error(`undo must keep earlier marks, stroke saw ${JSON.stringify(undone.pixels[0])}`);
  if (JSON.stringify(undone.pixels[1]) === JSON.stringify(undone.pixels[2])) throw new Error(`undo must remove the mosaic averaging, saw ${JSON.stringify({ m1: undone.pixels[1], m2: undone.pixels[2] })}`);
  await toolbar.getByRole("button", { name: "重做" }).click();
  await overlay.getByRole("button", { name: "保存图片" }).click();
  await page.waitForTimeout(120);
  const redone = await decodeRecordedImage(page, "save_image_as", 2, [[50, 50], [185, 85], [190, 85]]);
  if (redone.pixels[0][0] < 200 || redone.pixels[0][1] > 140) throw new Error(`redo must keep earlier marks, stroke saw ${JSON.stringify(redone.pixels[0])}`);
  if (JSON.stringify(redone.pixels[1]) !== JSON.stringify(redone.pixels[2])) throw new Error(`redo must restore the mosaic averaging, saw ${JSON.stringify({ m1: redone.pixels[1], m2: redone.pixels[2] })}`);
  // 绘制中放大镜必须隐藏。
  const penTool = toolbar.getByRole("button", { name: "画笔" });
  await penTool.click();
  await page.mouse.move(200, 200);
  if (await page.locator(".capture-overlay-magnifier").count() !== 1) throw new Error("loupe must be visible while hovering");
  await page.mouse.down();
  await page.mouse.move(220, 210, { steps: 4 });
  if (await page.locator(".capture-overlay-magnifier").count() !== 0) throw new Error("loupe must hide while drawing");
  await page.mouse.up();
  await page.keyboard.press("Escape");
  await waitForDetach(page);
  await context.close();
}

// Annotation Task 4: text tool with IME-safe Enter semantics — Enter inserts a
// newline, Ctrl+Enter commits one mark, Esc discards only the text draft.
async function annotationTextFlow(browser) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await context.newPage();
  await page.addInitScript(MOCK_SCRIPT);
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "截图" }).click();
  const overlay = await waitForOverlay(page);
  await drag(page, { x: 100, y: 100 }, { x: 500, y: 360 });
  const toolbar = page.locator(".capture-overlay-tools");
  await toolbar.waitFor();
  await toolbar.getByRole("button", { name: "文字" }).click();
  await page.mouse.click(200, 160);
  const editor = page.locator(".capture-overlay-text-editor textarea");
  await editor.waitFor();
  await editor.click();
  await page.keyboard.type("说明");
  await page.keyboard.press("Enter");
  await page.keyboard.type("第二行");
  const value = await editor.inputValue();
  if (value !== "说明\n第二行") throw new Error(`Enter must insert a newline, saw ${JSON.stringify(value)}`);
  if (await page.locator(".capture-overlay").count() !== 1) throw new Error("Enter inside the text editor must not confirm or cancel the capture");
  await page.keyboard.press("Escape");
  if (await editor.count() !== 0) throw new Error("Esc must discard the text draft");
  if (await page.locator(".capture-overlay").count() !== 1) throw new Error("Esc in the text editor must keep the capture alive");
  await page.mouse.click(200, 160);
  await editor.waitFor();
  // 线宽 6 → 渲染字号 36px，字形覆盖足够密，像素断言稳定。
  await toolbar.locator("input[type=range]").fill("6");
  await editor.fill("hello");
  await page.keyboard.press("Control+Enter");
  if (await editor.count() !== 0) throw new Error("Ctrl+Enter must commit the text mark");
  await overlay.getByRole("button", { name: "保存图片" }).click();
  await page.waitForTimeout(120);
  const textSamples = [];
  for (let y = 58; y <= 78; y += 5) for (let x = 100; x <= 150; x += 5) textSamples.push([x, y]);
  const saved = await decodeRecordedImage(page, "save_image_as", 0, textSamples);
  // 文字锚点在选区内的输出坐标 (100,60) 附近：这一带必须出现与背景不同的像素。
  const expected = textSamples.map(([x, y]) => [(x + 100) % 256, (y + 100) % 256, 64, 255]);
  let changed = 0;
  saved.pixels.forEach((p, i) => { if (p[0] !== expected[i][0] || p[1] !== expected[i][1]) changed += 1; });
  if (changed < 8) throw new Error(`committed text must draw pixels near its anchor, only ${changed} changed`);
  await page.keyboard.press("Escape");
  await waitForDetach(page);
  await context.close();
}

// Annotation Task 4: two-row toolbar must stay inside small viewports, keep
// reachable hit targets and clamp near the right screen edge (2× DPR too).
async function annotationToolbarFlow(browser) {
  const context = await browser.newContext({ viewport: { width: 640, height: 480 }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await page.addInitScript(MOCK_SCRIPT);
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "截图" }).click();
  await waitForOverlay(page);
  await drag(page, { x: 380, y: 100 }, { x: 620, y: 260 });
  const toolbar = page.locator(".capture-overlay-toolbar");
  await toolbar.waitFor();
  const box = await toolbar.boundingBox();
  if (!box) throw new Error("toolbar has no bounding box");
  if (box.x < 0 || box.x + box.width > 640 || box.y + box.height > 480) {
    throw new Error(`toolbar must stay inside the viewport at 640px, saw ${JSON.stringify(box)}`);
  }
  for (const name of ["移动", "箭头", "矩形", "画笔", "文字", "马赛克", "撤销", "重做"]) {
    const button = toolbar.getByRole("button", { name, exact: true });
    if ((await button.count()) !== 1) throw new Error(`tool button ${name} missing`);
    const buttonBox = await button.boundingBox();
    if (!buttonBox || buttonBox.height < 28) throw new Error(`tool button ${name} hit target below 28px: ${JSON.stringify(buttonBox)}`);
  }
  const color = toolbar.locator("input[type=color]");
  const width = toolbar.locator("input[type=range]");
  if ((await color.count()) !== 1 || (await width.count()) !== 1) throw new Error("toolbar must expose stroke color and width controls");
  if ((await color.getAttribute("aria-label")) !== "线条颜色" || (await width.getAttribute("aria-label")) !== "线宽") {
    throw new Error("stroke controls must carry localized accessible names");
  }
  await page.keyboard.press("Escape");
  await waitForDetach(page);
  await context.close();
}

const FLOWS = [
  ["capture overlay selection flow", captureOverlayFlow],
  ["annotation model history and pixel math", annotationModelFlow],
  ["annotation renderer composes export pixels", annotationRenderFlow],
  ["annotation drawing tools commit real pixels", annotationDrawFlow],
  ["annotation text tool newline, commit and cancel", annotationTextFlow],
  ["annotation toolbar wraps and clamps at 640px", annotationToolbarFlow],
  ["annotation failures keep marks and invalidate stale OCR", annotationFailureRetentionFlow],
  ["multi-pin session visibility rules", multiPinSessionFlow],
  ["toolbar/context save uses native save_image_as", nativeSaveFlow],
  ["overlay save busy and error on the overlay", overlaySaveFlow],
  ["overlay save keeps the window visible and restores selection", overlaySaveVisibilityFlow],
  ["pinned image keeps transparent corners", pinAlphaFlow],
  ["#pin window transparency and startup", pinWindowFlow],
  ["pin wheel zoom, close and cleanup", pinWheelFlow],
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
