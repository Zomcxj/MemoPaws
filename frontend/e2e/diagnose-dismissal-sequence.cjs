// Diagnostic: log every window operation with its visible/fullscreen state during
// the pin dismissal, so the exact sequence the user sees can be reconstructed.
//
//   node frontend/e2e/diagnose-dismissal-sequence.cjs --label=diag3 --port=9270

const { chromium } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function argValue(name, fallback) {
  const prefix = `--${name}=`;
  const hit = process.argv.slice(2).find((arg) => arg.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : fallback;
}

const LABEL = argValue('label', 'diag3');
const CDP_PORT = argValue('port', '9270');
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

    // Record every IPC command with a timestamp, straight from the page.
    await page.evaluate(() => {
      window.__SEQ__ = [];
      const originalFetch = window.fetch.bind(window);
      window.fetch = function (input, init) {
        try {
          const url = typeof input === 'string' ? input : (input && input.url) || '';
          if (url.indexOf('ipc') !== -1) window.__SEQ__.push({ at: Math.round(performance.now()), url: decodeURIComponent(url) });
        } catch { /* ignore */ }
        return originalFetch(input, init);
      };
    });

    const state = async () => {
      const visible = await page.evaluate(() => window.__TAURI_INTERNALS__.invoke('plugin:window|is_visible')).catch(() => null);
      const fullscreen = await page.evaluate(() => window.__TAURI_INTERNALS__.invoke('plugin:window|is_fullscreen')).catch(() => null);
      const position = await page.evaluate(() => window.__TAURI_INTERNALS__.invoke('plugin:window|outer_position')).catch(() => null);
      const size = await page.evaluate(() => window.__TAURI_INTERNALS__.invoke('plugin:window|outer_size')).catch(() => null);
      return { visible, fullscreen, pos: position ? `${position.x},${position.y}` : null, size: size ? `${size.width}x${size.height}` : null };
    };

    // Start a capture and select a region.
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('memopaws-capture')));
    await page.locator('.capture-overlay').waitFor({ state: 'visible', timeout: 20000 });
    await page.mouse.move(200, 200);
    await page.mouse.down();
    await page.mouse.move(600, 450, { steps: 6 });
    await page.mouse.up();
    await page.locator('.capture-overlay-rect').waitFor({ timeout: 10000 });

    console.log(`[before pin] ${JSON.stringify(await state())}`);
    await page.evaluate(() => { window.__SEQ__.length = 0; });

    // Click 钉图 and sample the window state as fast as possible.
    await page.locator('.capture-overlay').getByRole('button', { name: 'Pin image' }).click();
    const samples = [];
    for (let index = 0; index < 20; index++) {
      samples.push({ at: index, ...(await state()) });
      await sleep(25);
    }
    for (const sample of samples) {
      console.log(`[sample ${String(sample.at).padStart(2, '0')}] visible=${sample.visible} fullscreen=${sample.fullscreen} pos=${sample.pos} size=${sample.size}`);
    }
    const sequence = await page.evaluate(() => window.__SEQ__);
    console.log('--- IPC sequence after the pin click ---');
    for (const entry of sequence) console.log(`  ${entry.at}ms ${entry.url}`);
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
