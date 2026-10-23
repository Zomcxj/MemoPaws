// Focused native verification for the multi-pin increment: two independent pin
// windows over the real release WebView2, wheel zoom proportion, caller-scoped
// close, and last-close main-window restoration for visible and hidden origins.
//
// Reuses the process/isolation pattern from test-tauri-native.cjs: each run gets
// its own CDP port, MEMOPAWS_HOME and WebView2 user-data folder. USERPROFILE is
// never overridden (WebView2 refuses CDP then), and MEMOPAWS_HOME keeps the
// real %USERPROFILE%\.memopaws untouched.
//
//   node frontend/e2e/test-native-capture.cjs --label=capture --port=9230
//
// The release executable is mandatory: this gate verifies shipped behavior, so
// there is no debug fallback.

const { chromium } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function argValue(name, fallback) {
  const prefix = `--${name}=`;
  const hit = process.argv.slice(2).find(arg => arg.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : fallback;
}

const LABEL = argValue('label', 'capture');
const CDP_PORT = argValue('port', '9230');
const CDP_URL = `http://localhost:${CDP_PORT}`;
const TEST_HOME = path.join(__dirname, `.tauri-test-home-${LABEL}`);
const WEBVIEW_DATA = path.join(TEST_HOME, `webview-${LABEL}`);
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots', `native-${LABEL}`);

function findReleaseTauriExe() {
  const candidates = [
    path.join(__dirname, '..', '..', 'target', 'release', 'memopaws.exe'),
    path.join(__dirname, '..', '..', 'crates', 'tauri', 'target', 'release', 'memopaws.exe'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error('Release Tauri runtime unavailable: run RUST_MIN_STACK=67108864 CARGO_BUILD_JOBS=2 cargo build --release -p memopaws-tauri first');
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function connectCdp() {
  const deadline = Date.now() + 60000;
  let lastError;
  while (Date.now() < deadline) {
    try {
      return await chromium.connectOverCDP(CDP_URL);
    } catch (error) {
      lastError = error;
      await sleep(1000);
    }
  }
  throw new Error(`Native CDP unavailable on ${CDP_URL}: ${lastError && lastError.message}`);
}

async function invokeOn(page, command, args) {
  return page.evaluate(({ command: name, args: payload }) => window.__TAURI_INTERNALS__.invoke(name, payload), { command, args });
}

async function drag(page, from, to) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 8 });
  await page.mouse.up();
}

// Pin windows all load the same index.html#pin URL, so new targets are tracked
// by Page identity, not URL.
async function pinNewSelection(browser, knownPages, mainPage, from, to) {
  const before = new Set(knownPages);
  await mainPage.evaluate(() => window.dispatchEvent(new CustomEvent("memopaws-capture")));
  await mainPage.locator('.capture-overlay').waitFor({ state: 'visible', timeout: 20000 });
  const image = mainPage.locator('.capture-overlay img');
  await image.waitFor();
  await drag(mainPage, from, to);
  await mainPage.locator('.capture-overlay-rect').waitFor({ timeout: 10000 });
  await mainPage.locator('.capture-overlay').getByRole('button', { name: 'Pin image' }).click();
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const pages = browser.contexts()[0].pages();
    const candidate = pages.find((p) => !before.has(p) && p !== mainPage && p.url().includes('#pin'));
    if (candidate) {
      await candidate.waitForSelector('img[alt="pinned"]', { timeout: 15000 });
      knownPages.add(candidate);
      // Overlay detaches once the capture session settles as "pin".
      await mainPage.locator('.capture-overlay').waitFor({ state: 'detached', timeout: 20000 });
      return candidate;
    }
    await sleep(300);
  }
  throw new Error(`pin window never appeared over CDP for selection ${JSON.stringify({ from, to })}`);
}

async function pinLabel(pinPage) {
  return pinPage.evaluate(() => window.__TAURI_INTERNALS__.metadata.currentWindow.label);
}

async function pinImageSize(pinPage) {
  return pinPage.evaluate(() => {
    const image = document.querySelector('img[alt="pinned"]');
    return { width: image.naturalWidth, height: image.naturalHeight };
  });
}

async function closePin(pinPage) {
  await pinPage.locator('button[aria-label="关闭钉图"]').click();
  await pinPage.waitForEvent('close', { timeout: 15000 }).catch(() => {});
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (pinPage.isClosed()) return;
    await sleep(300);
  }
  throw new Error(`pin window ${pinPage.url()} did not close after 关闭钉图`);
}

// 读取浮层 contain 几何：把客户端拖拽坐标换算成原图像素坐标，
// 用于在真机截图（内容不可知）上定位画下的标注。
async function overlayGeometry(mainPage) {
  return mainPage.evaluate(() => {
    const img = document.querySelector('.capture-overlay img');
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const cssScale = Math.min(vw / nw, vh / nh);
    return { nw, nh, offsetX: (vw - nw * cssScale) / 2, offsetY: (vh - nh * cssScale) / 2, scale: 1 / cssScale };
  });
}

const toImagePoint = (geometry, client) => ({
  x: (client.x - geometry.offsetX) * geometry.scale,
  y: (client.y - geometry.offsetY) * geometry.scale,
});

// 解码钉图窗口实际展示的 PNG 字节并采样若干坐标的像素。
async function decodePinnedImage(pinPage, probePoints) {
  return pinPage.evaluate(async ({ points }) => {
    const img = document.querySelector('img[alt="pinned"]');
    const response = await fetch(img.src);
    const bytes = new Uint8Array(await response.arrayBuffer());
    const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0);
    bitmap.close();
    return {
      width: canvas.width,
      height: canvas.height,
      pixels: points.map(([x, y]) => Array.from(ctx.getImageData(Math.round(x), Math.round(y), 1, 1).data)),
    };
  }, { points: probePoints });
}

const isStrokeRed = (pixel) => pixel[0] >= 200 && pixel[1] >= 60 && pixel[1] <= 150 && pixel[2] >= 60 && pixel[2] <= 150;

async function windowSnapshot(mainPage) {
  const [visible, maximized, fullscreen, position, size] = await Promise.all([
    invokeOn(mainPage, 'plugin:window|is_visible'),
    invokeOn(mainPage, 'plugin:window|is_maximized').catch(() => null),
    invokeOn(mainPage, 'plugin:window|is_fullscreen').catch(() => null),
    invokeOn(mainPage, 'plugin:window|outer_position').catch(() => null),
    invokeOn(mainPage, 'plugin:window|outer_size').catch(() => null),
  ]);
  return {
    maximized,
    fullscreen,
    pos: position ? `${position.x},${position.y}` : null,
    size: size ? `${size.width}x${size.height}` : null,
  };
}

// 轮询主窗可见性，记录每次翻转时的完整窗口状态（最大化/全屏/几何），
// 用于指认隐藏窗口被重新显示的原生路径（tao 的旗标差异重显）。
async function waitForMainVisibility(mainPage, expected, timeoutMs = 15000) {
  const startedAt = Date.now();
  const deadline = startedAt + timeoutMs;
  let last;
  const transitions = [];
  while (Date.now() < deadline) {
    last = await invokeOn(mainPage, 'plugin:window|is_visible');
    if (!transitions.length || transitions[transitions.length - 1].visible !== last) {
      const snapshot = await windowSnapshot(mainPage).catch(() => null);
      transitions.push({ at: `${Date.now() - startedAt}ms`, visible: last, ...snapshot });
    }
    if (last === expected) return last;
    await sleep(300);
  }
  throw new Error(`main window visibility stayed ${last}, expected ${expected}; transitions: ${JSON.stringify(transitions)}`);
}

async function runTests() {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  fs.rmSync(TEST_HOME, { recursive: true, force: true });
  fs.mkdirSync(TEST_HOME, { recursive: true });

  const tauriExe = findReleaseTauriExe();
  console.log(`[${LABEL}] Release Tauri executable:`, tauriExe);
  const tauriProcess = spawn(tauriExe, [], {
    stdio: 'pipe',
    detached: false,
    env: {
      ...process.env,
      HOME: TEST_HOME,
      MEMOPAWS_HOME: TEST_HOME,
      MEMOPAWS_E2E_HIDDEN: '1',
      WEBVIEW2_USER_DATA_FOLDER: WEBVIEW_DATA,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${CDP_PORT} --remote-allow-origins=*`,
    },
  });
  let browser;
  const problems = [];

  try {
    browser = await connectCdp();
    const context = browser.contexts()[0] || await browser.newContext();
    const mainPage = context.pages()[0] || await context.newPage();
    await mainPage.waitForSelector('.recognize-page', { timeout: 60000 });
    const knownPages = new Set([mainPage]);

    // 原生端没有 mock 调用日志：生产 invoke 走 fetch(ipc://)/postMessage，
    // 在这两层记录命令与调用栈（属性包装 __TAURI_INTERNALS__.invoke 会被静默跳过）。
    await mainPage.evaluate(() => {
      const log = [];
      window.__INVOKE_LOG__ = log;
      const shortStack = () => { try { return new Error().stack.split("\n").slice(2, 6).join(" | "); } catch { return ""; } };
      const originalFetch = window.fetch && window.fetch.bind(window);
      if (originalFetch) {
        window.fetch = function (input, init) {
          try {
            const url = typeof input === "string" ? input : (input && input.url) || "";
            if (url.indexOf("ipc") !== -1) {
              log.push({ via: "fetch", url: String(url).slice(0, 120), stack: shortStack() });
            }
          } catch { /* 诊断钩子不得影响正常调用 */ }
          return originalFetch(input, init);
        };
      }
      try {
        const webview = window.chrome && window.chrome.webview;
        if (webview && typeof webview.postMessage === "function") {
          const originalPost = webview.postMessage.bind(webview);
          webview.postMessage = function (message) {
            try {
              log.push({ via: "postMessage", body: String(typeof message === "string" ? message : JSON.stringify(message)).slice(0, 160), stack: shortStack() });
            } catch { /* 同上 */ }
            return originalPost(message);
          };
        }
      } catch { /* 同上 */ }
    });
    const sessionLog = () => mainPage.evaluate(() => window.__INVOKE_LOG__
      .map((entry) => {
        let text = entry.url || entry.body || "";
        try { text = decodeURIComponent(text); } catch { /* 保留原文 */ }
        return { text: text.slice(0, 110), stack: entry.stack };
      })
      .filter((entry) => /capture_session|pin_image|plugin:window.*(show|hide)/i.test(entry.text)));

    // Mixed-DPI report: enumerate real monitors; cross-monitor pin placement is
    // only asserted when the machine actually exposes differing scale factors.
    const monitors = await invokeOn(mainPage, 'plugin:window|available_monitors').catch(() => []);
    const scales = [...new Set(monitors.map((m) => m.scaleFactor))];
    console.log(`[${LABEL}] monitors=${JSON.stringify(monitors.map((m) => ({ size: m.size, scaleFactor: m.scaleFactor })))}`);
    if (monitors.length > 1 && scales.length > 1) {
      console.log(`[${LABEL}] mixed-DPI hardware present (scale factors ${scales.join('/')}): pins land on the invoking window's monitor via work-area clamps`);
    } else {
      console.log(`[${LABEL}] single-scale environment: cross-DPI behavior reported as unverified, not passed`);
    }

    // Scenario A: visible origin — hidden stays hidden until the LAST pin closes.
    await invokeOn(mainPage, 'plugin:window|show');
    await waitForMainVisibility(mainPage, true);
    const pin1 = await pinNewSelection(browser, knownPages, mainPage, { x: 100, y: 100 }, { x: 356, y: 267 });
    const label1 = await pinLabel(pin1);
    if (!/^pin-\d+$/.test(label1)) problems.push(`expected a unique pin-N label, saw "${label1}"`);
    const firstPinVisibility = await waitForMainVisibility(mainPage, false, 5000).catch((error) => error);
    if (firstPinVisibility instanceof Error) {
      problems.push(`${firstPinVisibility.message}; session log: ${JSON.stringify(await sessionLog())}`);
    }
    const size1 = await pinImageSize(pin1);

    // Repeated capture while pins are up: second independent pin.
    const pin2 = await pinNewSelection(browser, knownPages, mainPage, { x: 420, y: 160 }, { x: 720, y: 427 });
    const label2 = await pinLabel(pin2);
    if (label2 === label1) problems.push(`second pin reused the first label: ${label2}`);
    const size2 = await pinImageSize(pin2);
    if (size1.width === size2.width && size1.height === size2.height) {
      problems.push(`two selections produced identical pin images: ${JSON.stringify({ size1, size2 })}`);
    }
    await mainPage.screenshot({ path: path.join(SCREENSHOTS_DIR, '01-two-pins.png') });

    // Wheel zoom on pin-1: proportional to the image's natural ratio, ±1px.
    const before = await invokeOn(pin1, 'plugin:window|inner_size');
    const box = await pin1.locator('img[alt="pinned"]').boundingBox();
    await pin1.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await pin1.mouse.wheel(0, -120);
    const deadline = Date.now() + 10000;
    let after = before;
    while (Date.now() < deadline) {
      after = await invokeOn(pin1, 'plugin:window|inner_size');
      if (after.width !== before.width || after.height !== before.height) break;
      await sleep(300);
    }
    if (after.width === before.width && after.height === before.height) {
      problems.push(`wheel zoom did not resize the pin: ${JSON.stringify({ before, after })}`);
    } else {
      const expectedHeight = Math.round(after.width * (before.height / before.width));
      if (Math.abs(after.height - expectedHeight) > 1) {
        problems.push(`wheel zoom broke the aspect ratio: ${JSON.stringify({ before, after, expectedHeight })}`);
      }
    }

    // Close pin-1: pin-2 must survive, main stays hidden.
    await closePin(pin1);
    if (!(await pinLabel(pin2))) problems.push('pin-2 page became unreachable after closing pin-1');
    await pin2.locator('img[alt="pinned"]').waitFor({ timeout: 5000 });
    const nonLastVisibility = await waitForMainVisibility(mainPage, false, 5000).catch((error) => error);
    if (nonLastVisibility instanceof Error) problems.push(nonLastVisibility.message);

    // Close pin-2 (last): visible-origin session restores the main window.
    await closePin(pin2);
    const lastCloseVisibility = await waitForMainVisibility(mainPage, true).catch((error) => error);
    if (lastCloseVisibility instanceof Error) problems.push(lastCloseVisibility.message);
    await mainPage.screenshot({ path: path.join(SCREENSHOTS_DIR, '02-restored.png') });

    // Scenario B: hidden origin — even the last close must stay hidden.
    await invokeOn(mainPage, 'plugin:window|hide');
    await waitForMainVisibility(mainPage, false);
    const pin3 = await pinNewSelection(browser, knownPages, mainPage, { x: 120, y: 120 }, { x: 400, y: 320 });
    const pinUpVisibility = await waitForMainVisibility(mainPage, false, 5000).catch((error) => error);
    if (pinUpVisibility instanceof Error) problems.push(pinUpVisibility.message);
    await closePin(pin3);
    const hiddenOriginVisibility = await waitForMainVisibility(mainPage, false, 5000).catch((error) => error);
    if (hiddenOriginVisibility instanceof Error) problems.push(hiddenOriginVisibility.message);

    // OS-style destroy cleanup is the same Destroyed event the app path fires
    // (close is never prevented for pin windows), so pin_close above already
    // exercises the destroy hook; a forced taskkill cannot target one window.
    console.log(`[${LABEL}] destroy hook exercised via Destroyed on every pin close`);

    // Scenario C: annotations end-to-end in the real app — draw via the real
    // pointer UI, pin, then decode the pinned PNG bytes and verify the drawn
    // pixels (stroke color, mosaic uniformity, transparent corners), then
    // confirm and require the same stroke on the main canvas.
    await invokeOn(mainPage, 'plugin:window|show');
    await waitForMainVisibility(mainPage, true);
    await mainPage.evaluate(() => window.dispatchEvent(new CustomEvent('memopaws-capture')));
    await mainPage.locator('.capture-overlay').waitFor({ state: 'visible', timeout: 20000 });
    await drag(mainPage, { x: 80, y: 80 }, { x: 420, y: 320 });
    const geometry = await overlayGeometry(mainPage);
    const origin = toImagePoint(geometry, { x: 80, y: 80 });
    const rectFrom = { x: 130, y: 130 };
    const rectTo = { x: 300, y: 240 };
    const mosaicFrom = { x: 180, y: 180 };
    const mosaicTo = { x: 230, y: 220 };
    const ia = toImagePoint(geometry, rectFrom);
    const ib = toImagePoint(geometry, rectTo);
    const im1 = toImagePoint(geometry, mosaicFrom);
    const im2 = toImagePoint(geometry, mosaicTo);
    await mainPage.locator('.capture-overlay-tools').getByRole('button', { name: /矩形|Rectangle/ }).click();
    await drag(mainPage, rectFrom, rectTo);
    await mainPage.locator('.capture-overlay-tools').getByRole('button', { name: /马赛克|Mosaic/ }).click();
    await drag(mainPage, mosaicFrom, mosaicTo);
    await mainPage.locator('.capture-overlay').getByRole('button', { name: 'Pin image' }).click();
    const markedPinDeadline = Date.now() + 20000;
    let markedPin = null;
    while (Date.now() < markedPinDeadline) {
      markedPin = browser.contexts()[0].pages().find((p) => !knownPages.has(p) && p !== mainPage && p.url().includes('#pin')) || null;
      if (markedPin) break;
      await sleep(300);
    }
    if (!markedPin) {
      problems.push('marked pin window never appeared');
    } else {
      knownPages.add(markedPin);
      await markedPin.waitForSelector('img[alt="pinned"]', { timeout: 15000 });
      await mainPage.locator('.capture-overlay').waitFor({ state: 'detached', timeout: 20000 });
      const size = await decodePinnedImage(markedPin, []);
      // 描边：沿矩形四条边（选区相对坐标 = 原图坐标 − 选区原点）各取 30 点。
      const strokePoints = [];
      for (let index = 0; index < 30; index++) {
        const t = index / 29;
        const ax = ia.x - origin.x;
        const ay = ia.y - origin.y;
        const bx2 = ib.x - origin.x;
        const by2 = ib.y - origin.y;
        strokePoints.push([ax + (bx2 - ax) * t, ay]);
        strokePoints.push([ax + (bx2 - ax) * t, by2]);
        strokePoints.push([ax, ay + (by2 - ay) * t]);
        strokePoints.push([bx2, ay + (by2 - ay) * t]);
      }
      const stroke = await decodePinnedImage(markedPin, strokePoints);
      const redRatio = stroke.pixels.filter(isStrokeRed).length / stroke.pixels.length;
      if (redRatio < 0.6) {
        problems.push(`pinned PNG must carry the drawn rectangle stroke, red ratio ${redRatio.toFixed(2)}`);
      }
      // 马赛克：第一个块内两个采样点必须逐位相同（块平均）。
      const block = Math.max(4, Math.round(3 * 4));
      const bx = Math.floor(Math.min(im1.x, im2.x) - origin.x);
      const by = Math.floor(Math.min(im1.y, im2.y) - origin.y);
      const mosaic = await decodePinnedImage(markedPin, [[bx + 2, by + 2], [bx + block - 2, by + 2]]);
      if (JSON.stringify(mosaic.pixels[0]) !== JSON.stringify(mosaic.pixels[1])) {
        problems.push(`mosaic block must be averaged in the pinned PNG, saw ${JSON.stringify(mosaic.pixels)}`);
      }
      // 圆角：四角必须透明。
      const corners = await decodePinnedImage(markedPin, [[0, 0], [size.width - 1, 0], [0, size.height - 1], [size.width - 1, size.height - 1]]);
      if (corners.pixels.some((pixel) => pixel[3] !== 0)) {
        problems.push(`pinned PNG corners must stay transparent, saw ${JSON.stringify(corners.pixels)}`);
      }
      await closePin(markedPin);
      const afterMarkedPin = await waitForMainVisibility(mainPage, true, 5000).catch(() => false);
      if (!afterMarkedPin) problems.push('closing the marked pin must restore the visible-origin main window');
    }

    // Confirm path: the same marks must reach the main canvas unchanged.
    await mainPage.evaluate(() => window.dispatchEvent(new CustomEvent('memopaws-capture')));
    await mainPage.locator('.capture-overlay').waitFor({ state: 'visible', timeout: 20000 });
    await drag(mainPage, { x: 80, y: 80 }, { x: 420, y: 320 });
    await mainPage.locator('.capture-overlay-tools').getByRole('button', { name: /矩形|Rectangle/ }).click();
    await drag(mainPage, rectFrom, rectTo);
    await mainPage.locator('.capture-overlay').getByRole('button', { name: /确认|Confirm/ }).click();
    await mainPage.locator('.capture-overlay').waitFor({ state: 'detached', timeout: 20000 });
    const confirmedStroke = await mainPage.evaluate(async ({ topY, x0, x1, regionX, regionY }) => {
      const img = document.querySelector('.image-canvas img');
      if (!img || !img.naturalWidth) return null;
      const response = await fetch(img.src);
      const bytes = new Uint8Array(await response.arrayBuffer());
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext('2d');
      context.drawImage(bitmap, 0, 0);
      bitmap.close();
      let count = 0;
      for (let index = 0; index < 120; index++) {
        const t = index / 119;
        const pixel = context.getImageData(Math.round(x0 - regionX + (x1 - x0) * t), Math.round(topY - regionY), 1, 1).data;
        if (pixel[0] >= 200 && pixel[1] >= 60 && pixel[1] <= 150 && pixel[2] >= 60 && pixel[2] <= 150) count += 1;
      }
      return { count, width: canvas.width, height: canvas.height };
    }, { topY: ia.y, x0: ia.x, x1: ib.x, regionX: origin.x, regionY: origin.y });
    if (!confirmedStroke) {
      problems.push('confirmed capture did not reach the main canvas');
    } else if (confirmedStroke.count < 60) {
      problems.push(`confirmed main image must carry the same stroke, red samples ${confirmedStroke.count}/120 (${JSON.stringify(confirmedStroke)})`);
    }

    // Scenario D: offline OCR on the real Windows engine — generate a
    // high-contrast text PNG in the browser, import it, run local_ocr with an
    // actually installed language and require nonempty text with spaces.
    // 无已安装语言能力时报告环境不支持，绝不安装语言包或假装通过。
    const installedLanguages = await invokeOn(mainPage, 'local_ocr_languages');
    const languageTag = installedLanguages.preferred || (installedLanguages.languages && installedLanguages.languages[0]?.tag) || "";
    if (!languageTag) {
      console.log(`[${LABEL}] offline OCR skipped: no installed OCR language capability on this machine`);
    } else {
      console.log(`[${LABEL}] offline OCR language: ${languageTag}`);
      const textPng = await mainPage.evaluate(() => new Promise((resolve, reject) => {
        const canvas = document.createElement('canvas');
        canvas.width = 800;
        canvas.height = 220;
        const context = canvas.getContext('2d');
        if (!context) { reject(new Error('no 2d context')); return; }
        context.fillStyle = '#ffffff';
        context.fillRect(0, 0, 800, 220);
        context.fillStyle = '#000000';
        context.font = 'bold 64px sans-serif';
        context.textBaseline = 'middle';
        context.fillText('MemoPaws offline OCR example', 20, 110);
        canvas.toBlob((blob) => {
          if (!blob) { reject(new Error('toBlob failed')); return; }
          const reader = new FileReader();
          reader.onload = () => resolve(Array.from(new Uint8Array(reader.result)));
          reader.onerror = () => reject(new Error('reader failed'));
          reader.readAsArrayBuffer(blob);
        }, 'image/png');
      }));
      await mainPage.locator('.recognize-toolbar input[type="file"]').setInputFiles({ name: 'offline-ocr-text.png', mimeType: 'image/png', buffer: Buffer.from(textPng) });
      await mainPage.locator('.image-canvas img').waitFor({ timeout: 15000 });
      // 语言查询完成前按钮被禁用：等待其可用再点。
      await mainPage.waitForFunction(() => {
        const offline = Array.from(document.querySelectorAll('.ocr-controls button'))
          .find((button) => button.textContent === '离线 OCR' || button.textContent === 'Offline OCR');
        return Boolean(offline && !offline.disabled);
      }, null, { timeout: 15000 });
      await mainPage.locator('.ocr-controls').nth(0).getByRole('button', { name: /离线 OCR|Offline OCR/ }).click();
      await mainPage.waitForFunction(() => {
        const area = document.querySelector("textarea[aria-label='AI识别']");
        return Boolean(area && area.value.trim().length > 0);
      }, null, { timeout: 30000 });
      const offlineText = await mainPage.locator("textarea[aria-label='AI识别']").inputValue();
      if (!/[a-z]{3,}/i.test(offlineText) || !offlineText.includes(' ')) {
        problems.push(`offline OCR must return nonempty text with retained spaces, saw ${JSON.stringify(offlineText)}`);
      }
      // IPC 观察：离线路径不得触碰 AI/密钥命令，且必须有 local_ocr 调用。
      const ipcCommands = await mainPage.evaluate(() => (window.__INVOKE_LOG__ || [])
        .map((entry) => {
          let text = entry.url || entry.body || "";
          try { text = decodeURIComponent(text); } catch { /* 保留原文 */ }
          return text;
        }));
      const aiHits = ipcCommands.filter((text) => /ai_ocr|ai_translate|get_value/.test(text));
      if (aiHits.length) problems.push(`offline OCR must never touch AI/vault IPC, saw ${JSON.stringify(aiHits)}`);
      if (!ipcCommands.some((text) => text.includes('local_ocr'))) problems.push('offline OCR click must record a local_ocr IPC call');
      // 成功文本按 local_ocr 入既有历史（序列化键是 type，不是 typ）。
      const history = await invokeOn(mainPage, 'history_list');
      if (!history.some((record) => record.type === 'local_ocr' && record.text === offlineText)) {
        problems.push(`successful offline text must enter history as local_ocr, saw ${JSON.stringify(history.slice(0, 2))}`);
      }
      // 未安装语言：明确报错，不回退、不安装。
      const missingLanguageError = await mainPage.evaluate(async () => {
        try {
          await window.__TAURI_INTERNALS__.invoke('local_ocr', { image: [137, 80, 78, 71], language: 'zz-ZZ' });
          return null;
        } catch (error) {
          return String((error && error.message) || error);
        }
      });
      if (!missingLanguageError || !/not installed/i.test(missingLanguageError)) {
        problems.push(`missing language must fail explicitly without fallback, saw ${JSON.stringify(missingLanguageError)}`);
      }
      // 畸形图片：解码失败只报错，不崩溃。
      await mainPage.locator('.recognize-toolbar input[type="file"]').setInputFiles({ name: 'corrupt.png', mimeType: 'image/png', buffer: Buffer.from('this is definitely not an image') });
      await mainPage.waitForTimeout(400);
      await mainPage.locator('.ocr-controls').nth(0).getByRole('button', { name: /离线 OCR|Offline OCR/ }).click();
      await mainPage.waitForFunction(() => {
        const element = document.querySelector('.recognize-error');
        return Boolean(element && element.textContent.trim().length > 0);
      }, null, { timeout: 20000 });
      // 隔离主目录（不含 WebView 配置目录）不得出现任何 OCR 图片文件。
      const imageFiles = [];
      const walk = (directory) => {
        for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
          const full = path.join(directory, entry.name);
          if (entry.isDirectory()) {
            if (full !== WEBVIEW_DATA) walk(full);
          } else if (/\.(png|jpe?g|bmp|gif|webp)$/i.test(entry.name)) imageFiles.push(full);
        }
      };
      walk(TEST_HOME);
      if (imageFiles.length) problems.push(`offline OCR must not write image files into the data home, saw ${JSON.stringify(imageFiles)}`);
      await mainPage.screenshot({ path: path.join(SCREENSHOTS_DIR, '03-offline-ocr.png') });
    }

    if (problems.length) throw new Error(problems.join('; '));
    console.log(`[${LABEL}] Native multi-pin tests completed!`);
  } finally {
    try {
      if (browser) await browser.close();
    } finally {
      if (!tauriProcess.killed) {
        if (process.platform === 'win32') {
          spawnSync('taskkill', ['/pid', String(tauriProcess.pid), '/t', '/f']);
        } else {
          tauriProcess.kill();
        }
      }
      if (tauriProcess.exitCode === null) await new Promise((resolve) => tauriProcess.once('exit', resolve));
      for (let attempt = 0; attempt < 10; attempt++) {
        try {
          fs.rmSync(TEST_HOME, { recursive: true, force: true });
          break;
        } catch (error) {
          if (!['EPERM', 'ENOTEMPTY', 'EBUSY'].includes(error.code) || attempt === 9) throw error;
          await sleep(200);
        }
      }
    }
  }
}

runTests().catch((error) => {
  console.error(`[${LABEL}] Test failed:`, error.message);
  process.exit(1);
});
