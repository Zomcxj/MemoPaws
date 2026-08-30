const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const MOCK_SCRIPT = fs.readFileSync(path.join(__dirname, "mock-tauri.js"), "utf-8");

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.addInitScript(MOCK_SCRIPT);
  await page.goto("http://localhost:1420/", { waitUntil: "networkidle" });
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("memopaws-capture")));
  await page.waitForSelector(".capture-overlay", { timeout: 5000 });
  // 模拟框选一块区域
  const overlay = await page.locator(".capture-overlay").boundingBox();
  await page.mouse.move(overlay.x + 300, overlay.y + 200);
  await page.mouse.down();
  await page.mouse.move(overlay.x + 700, overlay.y + 500, { steps: 10 });
  await page.mouse.up();
  await page.waitForSelector(".capture-overlay-handle--e", { timeout: 5000 });
  await page.screenshot({ path: "e2e/screenshots/handle-check.png" });
  // 单独放大截取手柄区域
  const handle = await page.locator(".capture-overlay-handle--ne").boundingBox();
  await page.screenshot({
    path: "e2e/screenshots/handle-zoom.png",
    clip: { x: handle.x - 40, y: handle.y - 40, width: 120, height: 120 },
  });
  await browser.close();
  console.log("done");
})().catch((error) => { console.error(error); process.exit(1); });
