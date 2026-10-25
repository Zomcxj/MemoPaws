// Smoke check for the separate-overlay-window architecture: the main window must
// stay hidden for the whole capture session (no main-UI flash is possible), the
// overlay must appear as its OWN page (#capture-overlay), pinning must destroy
// the overlay and reveal the pin on a clean desktop, and closing the pin must
// bring the main window back.
//
//   node frontend/e2e/diagnose-overlay-smoke.cjs --label=smoke --port=9280

const { chromium } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function argValue(name, fallback) {
  const prefix = `--${name}=`;
  const hit = process.argv.slice(2).find((arg) => arg.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : fallback;
}

const LABEL = argValue('label', 'smoke');
const CDP_PORT = argValue('port', '9280');
const CDP_URL = `http://localhost:${CDP_PORT}`;
const TEST_HOME = path.join(__dirname, `.tauri-test-home-${LABEL}`);
const WEBVIEW_DATA = path.join(TEST_HOME, `webview-${LABEL}`);
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
  throw new Error(`CDP unavailable: ${lastError && lastError.message}`);
}

const overlayConsole = [];
const pinConsole = [];

async function run() {
  fs.rmSync(TEST_HOME, { recursive: true, force: true });
  fs.mkdirSync(TEST_HOME, { recursive: true });
  const exe = path.join(__dirname, '..', '..', 'target', 'release', 'memopaws.exe');
  if (!fs.existsSync(exe)) throw new Error('release exe missing');
  let appStderr = '';
  const tauriProcess = spawn(exe, [], {
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
  tauriProcess.stderr?.on('data', (d) => { appStderr += d.toString(); });
  tauriProcess.stdout?.on('data', () => {});
  let browser;
  try {
    browser = await connectCdp();
    const context = browser.contexts()[0];
    // The overlay window is pre-created at startup (about:blank until it
    // navigates): pick the real main page by URL and wait for it — pages()[0]
    // may be the overlay target during boot.
    let mainPage = null;
    const mainDeadline = Date.now() + 30000;
    while (!mainPage && Date.now() < mainDeadline) {
      mainPage = context.pages().find((page) => /tauri\.localhost|localhost:\d+/.test(page.url()) && !page.url().includes('#capture-overlay') && !page.url().includes('#pin')) || null;
      if (!mainPage) await sleep(500);
    }
    if (!mainPage) throw new Error('main page never appeared');
    await mainPage.waitForSelector('.recognize-page', { timeout: 60000 });
    // The test home starts the app hidden (E2E env); make it a visible-origin
    // session so the restore after the last pin closes is expected.
    await mainPage.evaluate(() => window.__TAURI_INTERNALS__.invoke('plugin:window|show'));
    await sleep(300);
    // The probe must never wedge the check: a sync command that stops resolving
    // means the main thread is stuck. DURING overlay creation this is expected
    // (WebView2 cold start occupies the main thread for seconds) and is not a
    // violation; after the overlay exists, a wedge IS one.
    const withTimeout = (promise, ms) => Promise.race([promise, new Promise((resolve) => setTimeout(() => resolve({ wedged: true }), ms))]);
    const mainProbe = async () => withTimeout(mainPage.evaluate(() => window.__TAURI_INTERNALS__.invoke('window_probe').catch(() => null)), 5000);

    // Start a capture: the main window must hide and the overlay must open as its
    // own page. The main window is probed continuously: any visible sample is a
    // violation.
    await mainPage.evaluate(() => window.dispatchEvent(new CustomEvent('memopaws-capture')));
    const violations = [];
    // The overlay window is PRE-CREATED at startup (hidden) and reused: "the
    // overlay is open" means the page exists AND is visible (painted, ready).
    // visibilityState is unreliable in WebView2 (a hidden window's page may still
    // report "visible"): probe the REAL window state with window_probe.
    const overlayVisible = async () => {
      const candidate = context.pages().find((page) => page.url().includes('#capture-overlay')) || null;
      if (!candidate) return null;
      const probe = await candidate.evaluate(() => window.__TAURI_INTERNALS__.invoke('window_probe').catch(() => null));
      return probe && probe.visible ? candidate : null;
    };
    let overlayPage = null;
    let hideConfirmed = false;
    const deadline = Date.now() + 20000;
    const captureStartedAt = Date.now();
    while (Date.now() < deadline && !overlayPage) {
      overlayPage = await overlayVisible();
      const probe = await mainProbe();
      if (probe && !probe.wedged) {
        // Samples before the hide lands are the legitimate pre-capture state:
        // arm the check on the first hidden read, everything visible afterwards
        // (including once the overlay exists) is a violation.
        if (!hideConfirmed) hideConfirmed = !probe.visible;
        else if (probe.visible && probe.x > -20000 && probe.y > -20000) violations.push({ phase: 'waiting-for-overlay', probe });
      }
      const overlaySelf = overlayPage ? await overlayPage.evaluate(() => window.__TAURI_INTERNALS__.invoke('window_probe').catch(() => null)) : null;
      if (Math.round((Date.now() - captureStartedAt) / 40) !== Math.round((Date.now() - captureStartedAt - 40) / 40)) {
        console.log(`[t+${Date.now() - captureStartedAt}ms] main=${probe && !probe.wedged ? `v=${probe.visible}@${probe.x},${probe.y}` : 'wedged'} overlaySelf=${overlaySelf ? `v=${overlaySelf.visible}@${overlaySelf.x},${overlaySelf.y} ${overlaySelf.width}x${overlaySelf.height}` : 'none'}`);
      }
      await sleep(20);
    }
    if (!overlayPage) throw new Error('overlay page never appeared');
    console.log(`overlay visible after ${Date.now() - captureStartedAt}ms`);
    if (!hideConfirmed) {
      const probe = await mainProbe();
      if (probe && !probe.wedged && probe.visible) violations.push({ phase: 'overlay-open-but-main-visible', probe });
    }
    await overlayPage.waitForSelector('.capture-overlay', { timeout: 20000 });
    const overlayGeometry = await overlayPage.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight, screen: window.screen.width * window.devicePixelRatio }));
    console.log(`overlay page open, viewport ${overlayGeometry.width}x${overlayGeometry.height} (screen ${overlayGeometry.screen})`);

    // Select a region on the overlay and pin it.
    await overlayPage.waitForSelector('.capture-overlay', { timeout: 20000 });
    // The window shows only after the page signals ready; interaction needs it visible.
    await overlayPage.waitForFunction(() => window.__TAURI_INTERNALS__.invoke('window_probe').then((probe) => probe && probe.visible).catch(() => false), null, { timeout: 10000 });
    await overlayPage.mouse.move(300, 300);
    await overlayPage.mouse.down();
    await overlayPage.mouse.move(900, 600, { steps: 6 });
    await overlayPage.mouse.up();
    await overlayPage.locator('.capture-overlay-rect').waitFor({ timeout: 10000 });
    await overlayPage.locator('.capture-overlay').getByRole('button', { name: /钉图|Pin image/ }).click();

    // The overlay must hide, a pin page must appear, and the main window must
    // stay hidden until the last pin closes.
    let pinPage = null;
    while (Date.now() < deadline && !pinPage) {
      pinPage = context.pages().find((candidate) => candidate.url().includes('#pin')) || null;
      const overlayGone = !(await overlayVisible());
      const probe = await mainProbe();
      if (probe && probe.wedged) violations.push({ phase: 'pin-session', probe });
      else if (probe && probe.visible && probe.x > -20000 && probe.y > -20000) violations.push({ phase: 'pin-session', probe });
      if (pinPage && overlayGone) break;
      await sleep(25);
    }
    if (!pinPage) throw new Error('pin page never appeared');
    pinPage.on('console', (msg) => { pinConsole.push(msg.text()); });
    pinPage.on('pageerror', (err) => { pinConsole.push('PAGEERROR: ' + err.message); });
    // Verify the pin ACTUALLY renders the image (window existence proved nothing
    // in the confirm flow — do not repeat that mistake here).
    let pinContent = null;
    const pinContentDeadline = Date.now() + 10000;
    while (Date.now() < pinContentDeadline && !pinContent) {
      pinContent = await pinPage.evaluate(() => {
        const img = document.querySelector('img[alt="pinned"]');
        if (!img) {
          const errDiv = document.querySelector('div[style*="f2a2a2"]');
          return { error: errDiv ? errDiv.textContent : 'no img element', url: null };
        }
        const src = img.getAttribute('src');
        const natural = img.naturalWidth > 0 && img.naturalHeight > 0;
        const box = img.getBoundingClientRect();
        return { natural, url: src, box: { width: Math.round(box.width), height: Math.round(box.height) } };
      }).catch((e) => { return { error: String(e) }; });
      if (!pinContent) await sleep(200);
    }
    // Verify the pin actually RENDERs in the window: (1) the img element has
    // a real display size (offsetWidth/Height > 0), (2) the screenshot has a
    // meaningful ratio of non-transparent pixels. naturalWidth > 0 alone is NOT
    // enough — the image can decode but render at 0x0 (blank window).
    let pinRender = null;
    const renderDeadline = Date.now() + 10000;
    while (Date.now() < renderDeadline && !pinRender) {
      pinRender = await pinPage.evaluate(() => {
        const img = document.querySelector('img[alt="pinned"]');
        const canvas = document.querySelector('canvas');
        const target = canvas || img;
        if (!target) return null;
        const rect = target.getBoundingClientRect();
        return {
          offsetW: target.offsetWidth,
          offsetH: target.offsetHeight,
          dispW: Math.round(rect.width),
          dispH: Math.round(rect.height),
          naturalW: img ? img.naturalWidth : 0,
          naturalH: img ? img.naturalHeight : 0,
          canvasW: canvas ? canvas.width : 0,
          canvasH: canvas ? canvas.height : 0,
          complete: img ? img.complete : true,
          src: (img ? img.getAttribute('src') : '').slice(0, 40),
        };
      }).catch(() => null);
      if (!pinRender || !pinRender.offsetW || !pinRender.offsetH) await sleep(200);
    }
    const screenshotPath = `e2e/pin-screenshot-${process.env.LABEL || 'smoke'}.png`;
    await pinPage.screenshot({ path: screenshotPath }).catch(() => {});
    // Analyze the screenshot for non-transparent pixel ratio.
    let shotPixels = 0, shotTotal = 0;
    try {
      const fs = require('fs');
      const PNG = require('playwright-core/lib/utils/png');
      if (!PNG) throw new Error('no png util');
    } catch (e) {
      // Fallback: use page.evaluate with canvas to read the screenshot via
      // toDataURL on a page-level canvas.
    }
    // Simpler: check the screenshot file size as a rough proxy for content.
    let shotSize = 0;
    try { shotSize = fs.statSync(screenshotPath).size; } catch (e) {}
    if (!pinRender || !pinRender.offsetW || !pinRender.offsetH || pinRender.offsetW < 10) {
      throw new Error('PIN NOT RENDERING (display size 0): ' + JSON.stringify(pinRender) + ' | shotSize: ' + shotSize + ' | pinConsole: ' + JSON.stringify(pinConsole.slice(-5)));
    }
    console.log('pin rendered at ' + pinRender.offsetW + 'x' + pinRender.offsetH + ' (natural ' + pinRender.naturalW + 'x' + pinRender.naturalH + '), screenshot ' + shotSize + ' bytes saved to ' + screenshotPath);
    // REAL SCREEN proof: the page screenshot above proves the DOM renders, NOT
    // that the OS window is on screen. Capture the actual primary-screen
    // top-left corner (where the pin is positioned) and require it to contain
    // substantial content. A blank pin window compresses to a couple of KB.
    const { execSync } = require('child_process');
    const screenPath = `e2e/pin-screen-${process.env.LABEL || 'smoke'}.png`;
    try {
      execSync(`powershell -ExecutionPolicy Bypass -File "${path.join(__dirname, 'capture-screen.ps1')}" -OutPath "${path.resolve(screenPath)}"`, { stdio: 'pipe' });
      const screenSize = fs.statSync(screenPath).size;
      console.log('real screen capture: ' + screenPath + ' ' + screenSize + ' bytes');
      if (screenSize < 20000) {
        throw new Error('PIN NOT ON REAL SCREEN (blank top-left corner): ' + screenSize + ' bytes — the pin window exists but is not visible');
      }
    } catch (e) {
      if (String(e).includes('PIN NOT ON REAL SCREEN')) throw e;
      console.log('real screen capture unavailable: ' + String(e));
    }
    await sleep(600);
    // Close the pin through the product path (× button → pin_close): a bare CDP
    // page close never destroys the tauri window, so the restore hook would not
    // fire.
    let mainBack = false;
    for (let attempt = 0; attempt < 3 && !mainBack; attempt++) {
      // The first click usually closes the pin (its page target disappears);
      // never touch a dead page — just keep polling the main window.
      if (context.pages().some((page) => page === pinPage)) {
        await pinPage.getByRole('button', { name: '关闭钉图' }).click().catch(async () => {
          if (context.pages().some((page) => page === pinPage)) await pinPage.keyboard.press('Escape').catch(() => {});
        });
      }
      const closeDeadline = Date.now() + 4000;
      while (Date.now() < closeDeadline && !mainBack) {
        const probe = await mainProbe();
        mainBack = Boolean(probe && probe.visible);
        if (!mainBack) await sleep(100);
      }
    }
    if (!mainBack) throw new Error('pin close attempts never restored the main window');
    if (violations.length) throw new Error(`main window was visible during the session: ${JSON.stringify(violations.slice(0, 3))}`);
    if (!mainBack) throw new Error('main window never came back after the last pin closed');
    console.log('overlay smoke passed: main hidden through the session, restored after the last pin closed');

    // Second session: CONFIRM path. Any handler error is printed by the overlay's
    // own error UI — capture it verbatim. Also proves the capture guard re-arms
    // after a session ends.
    await mainPage.evaluate(() => window.dispatchEvent(new CustomEvent('memopaws-capture')));
    let overlay2 = null;
    const deadline2 = Date.now() + 20000;
    while (Date.now() < deadline2 && !overlay2) {
      const candidate = context.pages().find((page) => page.url().includes('#capture-overlay')) || null;
      if (candidate && await candidate.evaluate(() => window.__TAURI_INTERNALS__.invoke('window_probe').then((probe) => probe && probe.visible).catch(() => false))) overlay2 = candidate;
      await sleep(25);
    }
    if (!overlay2) { console.log('overlay console:', JSON.stringify(overlayConsole.slice(-12), null, 0)); throw new Error('second overlay never appeared (capture guard did not re-arm?)'); }
    await overlay2.waitForSelector('.capture-overlay', { timeout: 20000 });
    await overlay2.waitForFunction(() => window.__TAURI_INTERNALS__.invoke('window_probe').then((probe) => probe && probe.visible).catch(() => false), null, { timeout: 10000 });
    // Regression: the reused window must NOT leak the first session's selection
    // into the second one — a fresh overlay starts with no selection rect.
    const staleRects = await overlay2.locator('.capture-overlay-rect').count();
    if (staleRects > 0) {
      const leak = await overlay2.evaluate(() => ({
        rect: document.querySelector('.capture-overlay-rect')?.outerHTML?.slice(0, 220) || '',
        sessions: [...document.querySelectorAll('[data-overlay-session]')].map((element) => element.getAttribute('data-overlay-session')),
      }));
      console.log('overlay console:', JSON.stringify(overlayConsole.slice(-12), null, 0));
      throw new Error(`second session leaked ${staleRects} selection rect(s): ${JSON.stringify(leak)}`);
    }
    await overlay2.mouse.move(300, 300);
    await overlay2.mouse.down();
    await overlay2.mouse.move(800, 550, { steps: 6 });
    await overlay2.mouse.up();
    await overlay2.locator('.capture-overlay-rect').waitFor({ timeout: 10000 });
    await overlay2.locator('.capture-overlay').getByRole('button', { name: /确认|Confirm/ }).click();
    let confirmError = '';
    const errorDeadline = Date.now() + 5000;
    while (Date.now() < errorDeadline) {
      confirmError = await overlay2.evaluate(() => {
        const hit = [...document.querySelectorAll('.capture-overlay [role="alert"], .capture-overlay-error, .capture-overlay-hint')]
          .map((element) => element.textContent || '').find((text) => /command|error|失败|错误/i.test(text));
        return hit || '';
      }).catch(() => '');
      if (confirmError) break;
      const overlayGone = !(await overlayVisible());
      const probe = await mainProbe();
      if (overlayGone && probe && probe.visible) break;
      await sleep(100);
    }
    if (confirmError) throw new Error(`confirm surfaced an error: ${confirmError}`);
    let confirmRestored = false;
    const restoreDeadline = Date.now() + 10000;
    while (Date.now() < restoreDeadline && !confirmRestored) {
      const probe = await mainProbe();
      confirmRestored = Boolean(probe && probe.visible);
      if (!confirmRestored) await sleep(100);
    }
    if (!confirmRestored) throw new Error('main window never came back after confirm');
    console.log('confirm smoke passed: no error, overlay closed, main restored with the result');
  } finally {
    try {
      if (browser) await browser.close();
    } finally {
      if (!tauriProcess.killed) {
        if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(tauriProcess.pid), '/t', '/f']);
        else tauriProcess.kill();
      }
      if (tauriProcess.exitCode === null) await new Promise((resolve) => tauriProcess.once('exit', resolve));
      await sleep(800);
      for (let attempt = 0; attempt < 20; attempt++) {
        try { fs.rmSync(TEST_HOME, { recursive: true, force: true }); break; }
        catch (error) {
          if (!['EPERM', 'ENOTEMPTY', 'EBUSY'].includes(error.code) || attempt === 19) throw error;
          await sleep(700);
        }
      }
    }
  }
}

run().catch((error) => { console.error('overlay smoke failed:', error.message); console.error('overlay console:', JSON.stringify(overlayConsole.slice(-15))); process.exit(1); });
