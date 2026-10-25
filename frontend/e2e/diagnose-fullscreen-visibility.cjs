// Diagnostic: does exiting fullscreen make a window visible again, and does the
// fullscreen flag survive a hide/show cycle?
//
//   node frontend/e2e/diagnose-fullscreen-visibility.cjs --label=diag --port=9250

const { chromium } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function argValue(name, fallback) {
  const prefix = `--${name}=`;
  const hit = process.argv.slice(2).find((arg) => arg.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : fallback;
}

const LABEL = argValue('label', 'diag');
const CDP_PORT = argValue('port', '9250');
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

async function run() {
  fs.rmSync(TEST_HOME, { recursive: true, force: true });
  fs.mkdirSync(TEST_HOME, { recursive: true });
  const exe = path.join(__dirname, '..', '..', 'target', 'release', 'memopaws.exe');
  if (!fs.existsSync(exe)) throw new Error('release exe missing');
  const tauriProcess = spawn(exe, [], {
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
  try {
    browser = await connectCdp();
    const context = browser.contexts()[0] || await browser.newContext();
    const page = context.pages()[0] || await context.newPage();
    await page.waitForSelector('.recognize-page', { timeout: 60000 });
    const invoke = (command, args) => page.evaluate(({ command: c, args: a }) => window.__TAURI_INTERNALS__.invoke(c, a), { command, args });
    const probe = async (mark) => {
      const visible = await invoke('plugin:window|is_visible');
      const fullscreen = await invoke('plugin:window|is_fullscreen');
      const size = await invoke('plugin:window|outer_size');
      console.log(`[${mark}] visible=${visible} fullscreen=${fullscreen} size=${size.width}x${size.height}`);
      return { visible, fullscreen };
    };

    // 1) Visible window: does exiting fullscreen change visibility?
    await invoke('plugin:window|show');
    await probe('visible, not fullscreen');
    await invoke('plugin:window|set_fullscreen', { value: true });
    await probe('visible, fullscreen(true)');
    await invoke('plugin:window|set_fullscreen', { value: false });
    await probe('visible, fullscreen(false)  <-- does it stay visible?');

    // 2) Hidden window: exiting fullscreen (the tao re-show path).
    await invoke('plugin:window|hide');
    await probe('hidden, not fullscreen');
    await invoke('plugin:window|set_fullscreen', { value: true });
    await probe('hidden, fullscreen(true)');
    await invoke('plugin:window|set_fullscreen', { value: false });
    await probe('hidden, fullscreen(false)  <-- tao re-show path');

    // 3) Fullscreen flag across hide/show: can we re-enter fullscreen while hidden?
    await invoke('plugin:window|hide');
    await invoke('plugin:window|set_fullscreen', { value: true });
    await invoke('plugin:window|hide');
    await probe('hidden, after fullscreen+hide');
    await invoke('plugin:window|show');
    await probe('shown again (fullscreen flag?)');

    // 4) Is the main window VISIBLE while the capture overlay is on screen? The
    // overlay lives inside the main window, so its visibility decides everything.
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('memopaws-capture')));
    await page.locator('.capture-overlay').waitFor({ state: 'visible', timeout: 20000 });
    await probe('overlay on screen');
    const overlayGeometry = await page.evaluate(() => {
      const overlay = document.querySelector('.capture-overlay');
      const rect = overlay.getBoundingClientRect();
      return { width: rect.width, height: rect.height, innerWidth: window.innerWidth, innerHeight: window.innerHeight };
    });
    console.log(`[overlay geometry] ${JSON.stringify(overlayGeometry)}`);
    await probe('overlay on screen (after geometry read)');

    console.log('diagnostic finished');
  } finally {
    try {
      if (browser) await browser.close();
    } finally {
      if (!tauriProcess.killed) {
        if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(tauriProcess.pid), '/t', '/f']);
        else tauriProcess.kill();
      }
      if (tauriProcess.exitCode === null) await new Promise((resolve) => tauriProcess.once('exit', resolve));
      for (let attempt = 0; attempt < 10; attempt++) {
        try { fs.rmSync(TEST_HOME, { recursive: true, force: true }); break; }
        catch (error) {
          if (!['EPERM', 'ENOTEMPTY', 'EBUSY'].includes(error.code) || attempt === 9) throw error;
          await sleep(200);
        }
      }
    }
  }
}

run().catch((error) => { console.error('diagnostic failed:', error.message); process.exit(1); });
