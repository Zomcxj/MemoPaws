// Focused browser regression test for editable capture selections.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE_URL = "http://localhost:1420";
const MOCK_SCRIPT = fs.readFileSync(path.join(__dirname, "mock-tauri.js"), "utf-8");

async function drag(page, from, to) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y);
  await page.mouse.up();
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await context.newPage();
  await page.addInitScript(MOCK_SCRIPT);
  await page.goto(BASE_URL, { waitUntil: "networkidle" });

  await page.getByRole("combobox", { name: "显示器" }).selectOption("1");
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("memopaws-capture")));
  const overlay = page.locator(".capture-overlay");
  await overlay.waitFor();
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
  await overlay.waitFor({ state: "detached" });
  windowCalls = await page.evaluate(() => window.__MOCK_TAURI_WINDOW_CALLS__);
  const overlayPosition = windowCalls.find((call) => call.command === "plugin:window|set_position" && call.value?.position?.x === 1280);
  const restoredPosition = windowCalls.find((call) => call.command === "plugin:window|set_position" && call.value?.position?.x === 0 && call.value?.position?.y === 0);
  if (!overlayPosition || !restoredPosition) throw new Error(`Capture window geometry was not set then restored: ${JSON.stringify(windowCalls)}`);

  await page.getByRole("button", { name: "截图" }).click();
  await overlay.waitFor();
  await drag(page, { x: 100, y: 100 }, { x: 400, y: 300 });

  const selection = page.locator(".capture-overlay-rect");
  await selection.waitFor();
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

  const callsBefore = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === "image_crop").length);
  await overlay.getByRole("button", { name: "AI识别" }).click();
  const callsAfterOverlayAction = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === "image_crop").length);
  if (callsAfterOverlayAction !== callsBefore + 1) throw new Error("Overlay action did not crop its selected region");
  if (await page.locator(".capture-overlay").count() !== 1) throw new Error("Non-confirm overlay action closed the overlay");
  if (await page.locator(".image-canvas").count() !== 0) throw new Error("Non-confirm overlay action changed the canvas");

  await page.keyboard.press("Escape");
  await overlay.waitFor({ state: "detached" });
  await page.evaluate(() => { window.__MOCK_TAURI_SET_FULLSCREEN__(true); window.__MOCK_TAURI_WINDOW_CALLS__.length = 0; });
  await page.getByRole("button", { name: "截图" }).click();
  await overlay.waitFor();
  windowCalls = await page.evaluate(() => window.__MOCK_TAURI_WINDOW_CALLS__);
  const fullscreenCheck = windowCalls.findIndex((call) => call.command === "plugin:window|is_fullscreen");
  const exitFullscreen = windowCalls.findIndex((call) => call.command === "plugin:window|set_fullscreen" && call.value === false);
  const firstGeometryWrite = windowCalls.findIndex((call) => call.command === "plugin:window|set_position" || call.command === "plugin:window|set_size");
  if (fullscreenCheck < 0 || exitFullscreen < 0 || firstGeometryWrite < 0 || !(fullscreenCheck < exitFullscreen && exitFullscreen < firstGeometryWrite)) {
    throw new Error(`Fullscreen was not exited before capture geometry writes: ${JSON.stringify(windowCalls)}`);
  }
  await page.keyboard.press("Escape");
  await overlay.waitFor({ state: "detached" });
  const restoredFullscreen = await page.evaluate(() => window.__MOCK_TAURI_WINDOW_CALLS__.some((call) => call.command === "plugin:window|set_fullscreen" && call.value === true));
  if (!restoredFullscreen) throw new Error("Fullscreen state was not restored after cancelling capture");

  await page.getByRole("button", { name: "截图" }).click();
  await overlay.waitFor();
  await drag(page, { x: 100, y: 100 }, { x: 1600, y: 800 });
  box = await selection.boundingBox();
  if (!box || Math.round(box.x) !== 100 || Math.round(box.y) !== 100 || Math.round(box.x + box.width) !== 1280 || Math.round(box.y + box.height) !== 720) {
    throw new Error(`Stored selection was not clamped to screenshot bounds: ${JSON.stringify(box)}`);
  }
  await page.keyboard.press("Escape");
  await overlay.waitFor({ state: "detached" });
  await page.getByRole("button", { name: "截图" }).click();
  await overlay.waitFor();
  await drag(page, { x: 400, y: 300 }, { x: 100, y: 100 });
  box = await selection.boundingBox();
  if (!box || Math.round(box.x) !== 100 || Math.round(box.y) !== 100 || Math.round(box.width) !== 300 || Math.round(box.height) !== 200) {
    throw new Error(`New selection was not clamped to screenshot bounds: ${JSON.stringify(box)}`);
  }
  await drag(page, { x: 250, y: 200 }, { x: 300, y: 250 });
  box = await selection.boundingBox();
  if (!box || Math.round(box.x) !== 150 || Math.round(box.y) !== 150) throw new Error(`Reverse selection did not move by the drag delta: ${JSON.stringify(box)}`);

  await overlay.getByRole("button", { name: "确认" }).click();
  await overlay.waitFor({ state: "detached" });
  windowCalls = await page.evaluate(() => window.__MOCK_TAURI_WINDOW_CALLS__);
  const restoreAfterConfirm = windowCalls.filter((call) => call.command === "plugin:window|set_position" && call.value?.position?.x === 0 && call.value?.position?.y === 0).length;
  if (restoreAfterConfirm < 2) throw new Error(`Capture confirmation did not restore the original geometry: ${JSON.stringify(windowCalls)}`);

  await browser.close();
}

run().catch((error) => { console.error(error); process.exit(1); });
