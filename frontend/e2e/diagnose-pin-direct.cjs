// Direct pin diagnostic: does the pin window actually appear ON SCREEN?
// Captures: window visibility/position from Rust side + a full-desktop screenshot.
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { chromium } = require('playwright-core');

const ROOT = path.resolve(__dirname, '..', '..');
const EXE = path.join(ROOT, 'target', 'release', 'memopaws.exe');
const TEST_HOME = path.join(os.tmpdir(), 'memopaws-pindiag-' + Date.now());
const WEBVIEW_DATA = path.join(TEST_HOME, 'webview');
const CDP_PORT = Number(process.env.PORT || 9471);
const LABEL = process.env.LABEL || 'pindiag';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function connectCdp() {
  for (let i = 0; i < 40; i++) {
    try {
      const browser = await chromium.connectOverCDP(`http://127.0.0.1:${CDP_PORT}`);
      return browser;
    } catch (e) {
      await sleep(250);
    }
  }
  throw new Error('CDP unavailable');
}

async function main() {
  const tauriProcess = spawn(EXE, [], {
    stdio: 'pipe',
    env: {
      ...process.env,
      HOME: TEST_HOME,
      MEMOPAWS_HOME: TEST_HOME,
      MEMOPAWS_E2E_HIDDEN: '1',
      WEBVIEW2_USER_DATA_FOLDER: WEBVIEW_DATA,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${CDP_PORT} --remote-allow-origins=*`,
    },
  });
  let appStderr = '';
  tauriProcess.stderr.on('data', (d) => { appStderr += d.toString(); });

  let browser;
  try {
    browser = await connectCdp();
    const context = browser.contexts()[0];

    // Wait for the main page
    let mainPage = null;
    const deadline = Date.now() + 30000;
    while (!mainPage && Date.now() < deadline) {
      mainPage = context.pages().find((p) => /tauri\.localhost|localhost:\d+/.test(p.url()) && !p.url().includes('#capture-overlay') && !p.url().includes('#pin')) || null;
      await sleep(200);
    }
    if (!mainPage) throw new Error('main page never appeared');
    console.log('[t] main page ready');

    // Start capture
    await mainPage.evaluate(() => window.dispatchEvent(new CustomEvent('memopaws-capture')));
    let overlayPage = null;
    const oDeadline = Date.now() + 15000;
    while (!overlayPage && Date.now() < oDeadline) {
      overlayPage = context.pages().find((p) => p.url().includes('#capture-overlay')) || null;
      await sleep(200);
    }
    if (!overlayPage) throw new Error('overlay page never appeared');
    await overlayPage.waitForSelector('.capture-overlay', { timeout: 10000 });
    console.log('[t] overlay open');

    overlayPage.on('console', (m) => console.log('[overlay-console]', m.text()));
    overlayPage.on('pageerror', (e) => console.log('[overlay-console] PAGEERROR', e.message));

    // Draw a selection
    const vp = await overlayPage.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));
    await overlayPage.mouse.move(vp.width * 0.25, vp.height * 0.25, { steps: 6 });
    await overlayPage.mouse.down();
    await overlayPage.mouse.move(vp.width * 0.75, vp.height * 0.75, { steps: 8 });
    await overlayPage.mouse.up();
    await overlayPage.locator('.capture-overlay-rect').waitFor({ timeout: 10000 });
    console.log('[t] selection drawn');

    // Click pin
    await overlayPage.locator('.capture-overlay').getByRole('button', { name: /钉图|Pin image/ }).click();
    console.log('[t] pin button clicked');

    // Wait for the pin page
    let pinPage = null;
    const pDeadline = Date.now() + 15000;
    while (!pinPage && Date.now() < pDeadline) {
      pinPage = context.pages().find((p) => p.url().includes('#pin')) || null;
      await sleep(200);
    }
    if (!pinPage) throw new Error('pin page never appeared');
    console.log('[t] pin page found, url:', pinPage.url());

    // Give it time to load + render
    await sleep(3000);

    // 1) Query the pin page's own window geometry through Tauri
    const geo = await pinPage.evaluate(async () => {
      try {
        const { getCurrentWindow } = await import('/node_modules/@tauri-apps/api/window.js');
        const w = getCurrentWindow();
        const [visible, pos, size, factor] = await Promise.all([
          w.isVisible(), w.outerPosition(), w.outerSize(), w.scaleFactor(),
        ]);
        return { visible, pos: { x: pos.x, y: pos.y }, size: { width: size.width, height: size.height }, factor };
      } catch (e) {
        return { error: String(e) };
      }
    });
    console.log('[window] pin geometry from Tauri:', JSON.stringify(geo));

    // 2) Dump the pin page DOM
    const dom = await pinPage.evaluate(() => {
      const img = document.querySelector('img[alt="pinned"]');
      const canvas = document.querySelector('canvas');
      const root = document.querySelector('[data-pin-root]');
      return {
        url: location.href,
        hasImg: !!img,
        imgSrcLen: img ? (img.getAttribute('src') || '').length : 0,
        imgNatural: img ? [img.naturalWidth, img.naturalHeight] : null,
        imgOffset: img ? [img.offsetWidth, img.offsetHeight] : null,
        imgDisplay: img ? getComputedStyle(img).display : null,
        hasCanvas: !!canvas,
        canvasSize: canvas ? [canvas.width, canvas.height, canvas.offsetWidth, canvas.offsetHeight] : null,
        hasRoot: !!root,
        bodyHTML: document.body.innerHTML.slice(0, 400),
      };
    });
    console.log('[dom]', JSON.stringify(dom, null, 1));

    // 2b) OS-level window enumeration for THIS process: does the pin window
    // exist as a real, visible, on-screen HWND?
    const { execSync: exec2 } = require('child_process');
    try {
      const out = exec2(`powershell -ExecutionPolicy Bypass -File "${path.join(__dirname, 'list-app-windows.ps1')}" -PID ${tauriProcess.pid}`, { encoding: 'utf8' });
      console.log('[os-windows]' + String.fromCharCode(10) + out.trim());
    } catch (e) {
      console.log('[os-windows] failed:', String(e));
    }

    // 3) Screenshot the pin page itself (DOM render only - NOT proof of an
    // on-screen window)
    const shot = `e2e/pindiag-${LABEL}.png`;
    await pinPage.screenshot({ path: shot }).catch((e) => console.log('[shot] page screenshot failed:', String(e)));
    console.log('[shot] pin page screenshot:', shot, fs.statSync(shot).size, 'bytes');

    // 3b) REAL SCREEN capture. The pin is positioned at the monitor work-area
    // origin (top-left), so capture the top-left corner of the PRIMARY screen.
    // The script sleeps to let you compare before/after.
    const { execSync } = require('child_process');
    const capScript = path.join(__dirname, 'capture-screen.ps1');
    try {
      execSync(`powershell -ExecutionPolicy Bypass -File "${capScript}" -OutPath "${path.resolve(__dirname, 'pindiag-screen-' + LABEL + '.png')}"`, { stdio: 'inherit' });
    } catch (e) {
      console.log('[shot] real screen capture failed:', String(e));
    }

    if (appStderr.trim()) {
      const lines = appStderr.split('\n').filter((l) => l.trim()).slice(-15);
      console.log('[stderr]', lines.join('\n'));
    }
  } finally {
    tauriProcess.kill();
  }
}

main().catch((e) => { console.error('DIAG FAILED:', e.message); process.exit(1); });
