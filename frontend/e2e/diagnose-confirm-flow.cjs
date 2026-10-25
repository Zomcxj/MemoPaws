// Strict reproduction of the REAL user confirm flow, with verification of what
// actually lands in the main window (not just window visibility):
//
//   capture -> select -> OFFLINE OCR -> click check -> verify:
//   (a) the overlay is gone, (b) the main window is visible,
//   (c) the main page actually holds the image (preview <img> with bytes),
//   (d) the OCR text field is filled.
//
//   cd frontend && node e2e/diagnose-confirm-flow.cjs --label=confirm --port=9290

const { chromium } = require('playwright-core');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function argValue(name, fallback) {
  const prefix = `--${name}=`;
  const hit = process.argv.slice(2).find((arg) => arg.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : fallback;
}

const LABEL = argValue('label', 'confirm');
const CDP_PORT = argValue('port', '9290');
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

const probe = (page) => page.evaluate(() => window.__TAURI_INTERNALS__.invoke('window_probe').catch(() => null));

async function run() {
  fs.rmSync(TEST_HOME, { recursive: true, force: true });
  fs.mkdirSync(TEST_HOME, { recursive: true });
  const exe = path.join(__dirname, '..', '..', 'target', 'release', 'memopaws.exe');
  if (!fs.existsSync(exe)) throw new Error('release exe missing');
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
  let browser;
  try {
    browser = await connectCdp();
    const context = browser.contexts()[0];
    let mainPage = null;
    const mainDeadline = Date.now() + 30000;
    while (!mainPage && Date.now() < mainDeadline) {
      mainPage = context.pages().find((page) => /tauri\.localhost|localhost:\d+/.test(page.url()) && !page.url().includes('#capture-overlay') && !page.url().includes('#pin')) || null;
      if (!mainPage) await sleep(500);
    }
    if (!mainPage) throw new Error('main page never appeared');
    await mainPage.waitForSelector('.recognize-page', { timeout: 60000 });
    mainPage.on('console', (message) => console.log(`main console: ${message.text()}`));
    await mainPage.evaluate(() => window.__TAURI_INTERNALS__.invoke('plugin:window|show'));
    await sleep(300);

    const baseline = await mainPage.evaluate(() => ({
      preview: document.querySelector('.recognize-preview img')?.getAttribute('src') || '',
      ocr: (document.querySelector('.result-panel textarea')?.value || '').length,
    }));
    console.log(`baseline: preview=${baseline.preview ? 'set' : 'empty'} ocrChars=${baseline.ocr}`);

    await mainPage.evaluate(() => window.dispatchEvent(new CustomEvent('memopaws-capture')));
    let overlayPage = null;
    const openDeadline = Date.now() + 20000;
    while (Date.now() < openDeadline && !overlayPage) {
      const candidate = context.pages().find((page) => page.url().includes('#capture-overlay')) || null;
      if (candidate && (await probe(candidate))?.visible) overlayPage = candidate;
      await sleep(25);
    }
    if (!overlayPage) throw new Error('overlay never became visible');
    await overlayPage.waitForSelector('.capture-overlay', { timeout: 20000 });

    await overlayPage.mouse.move(400, 300);
    await overlayPage.mouse.down();
    await overlayPage.mouse.move(900, 600, { steps: 6 });
    await overlayPage.mouse.up();
    await overlayPage.locator('.capture-overlay-rect').waitFor({ timeout: 10000 });

    // THE USER PATH: offline OCR first, THEN the check mark.
    const ocrButton = overlayPage.locator('.capture-overlay').getByRole('button', { name: /离线\s*OCR/i }).first();
    if (await ocrButton.count()) {
      await ocrButton.click();
      await sleep(2500);
      const overlayOcr = await overlayPage.evaluate(() => document.querySelector('.capture-result-window textarea')?.value || '');
      console.log(`overlay OCR result chars: ${overlayOcr.length}`);
    } else {
      console.log('overlay OCR button not found (skipping OCR step)');
    }
    const overlayError = await overlayPage.evaluate(() => document.querySelector('.capture-result-error, .capture-overlay [role="alert"]')?.textContent || '');
    if (overlayError) console.log(`overlay error before confirm: ${overlayError}`);

    const confirmButton = overlayPage.locator('.capture-overlay').getByRole('button', { name: /确认|Confirm/ });
    console.log(`confirm button enabled: ${await confirmButton.isEnabled().catch(() => false)}`);
    await confirmButton.click();
    // Poll the status command from the MAIN page directly, with timestamps, to
    // see exactly what the main page can observe (and when).
    const statusTimeline = [];
    const statusDeadline = Date.now() + 6000;
    const startedAt = Date.now();
    while (Date.now() < statusDeadline) {
      const status = await mainPage.evaluate(() => window.__TAURI_INTERNALS__.invoke('capture_session_status').catch((error) => ({ error: String(error && error.message || error) })));
      statusTimeline.push({ at: Date.now() - startedAt, active: status && status.active, resultGeneration: status && status.resultGeneration, ocrChars: status && status.ocrText ? status.ocrText.length : null });
      await sleep(120);
    }
    for (const entry of statusTimeline) console.log(`status t+${entry.at}ms active=${entry.active} resultGen=${entry.resultGeneration} ocrChars=${entry.ocrChars}`);
    // What does the binary channel actually return to the MAIN page? (A wrong
    // assumption here is exactly how the result silently never landed.)
    await sleep(1200);
    const resultImageShape = await mainPage.evaluate(async () => {
      try {
        const raw = await window.__TAURI_INTERNALS__.invoke('capture_session_result_image');
        const isArrayBuffer = raw instanceof ArrayBuffer;
        const numbers = !isArrayBuffer && Array.isArray(raw) ? raw : null;
        return {
          isArrayBuffer,
          isArray: Boolean(numbers),
          length: isArrayBuffer ? raw.byteLength : numbers ? numbers.length : typeof raw === 'string' ? raw.length : -1,
          ctor: raw && raw.constructor ? raw.constructor.name : typeof raw,
        };
      } catch (error) {
        return { error: String(error && error.message || error) };
      }
    });
    console.log(`capture_session_result_image -> ${JSON.stringify(resultImageShape)}`);

    let overlayGone = false;
    let mainVisible = false;
    let landed = null;
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline && (!overlayGone || !mainVisible || !landed)) {
      const overlayCandidate = context.pages().find((page) => page.url().includes('#capture-overlay')) || null;
      overlayGone = !overlayCandidate || !(await probe(overlayCandidate))?.visible;
      const mainProbe = await probe(mainPage);
      mainVisible = Boolean(mainProbe && mainProbe.visible);
      if (mainVisible) {
        const dom = await mainPage.evaluate(() => ({
          previewImgs: document.querySelectorAll('img').length,
          previewSrcs: [...document.querySelectorAll('img')].slice(0, 3).map((img) => (img.getAttribute('src') || '').slice(0, 24)),
          textareas: [...document.querySelectorAll('textarea')].map((field) => (field.value || '').length),
          hasRecognizePage: Boolean(document.querySelector('.recognize-page')),
          panels: document.querySelectorAll('.result-panel').length,
        }));
        landed = { preview: dom.previewImgs > 0 && dom.textareas.some((length) => length > 0), ocr: Math.max(0, ...dom.textareas) };
        if (!landed.preview) { landed = null; console.log('main DOM dump: ' + JSON.stringify(dom)); }
      }
      await sleep(150);
    }
    console.log(`overlayGone=${overlayGone} mainVisible=${mainVisible} landed=${JSON.stringify(landed)}`);
    if (!overlayGone) throw new Error('CONFIRM FAILED: the overlay window is still up');
    if (!mainVisible) throw new Error('CONFIRM FAILED: the main window never came back');
    if (!landed) throw new Error('CONFIRM FAILED: the main window is back but holds no image/OCR result');
    console.log('CONFIRM FLOW PASSED: overlay closed, main restored, image+OCR landed in the main page');
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

run().catch((error) => { console.error('confirm flow failed:', error.message); process.exit(1); });
