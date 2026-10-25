// Diagnostic: capture the screen frame-by-frame right after clicking 钉图, so we
// can SEE what flashes on screen (gray mask, app UI, desktop, ...).
//
//   node frontend/e2e/diagnose-dismissal-frames.cjs --label=diag2 --port=9260

const { chromium } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function argValue(name, fallback) {
  const prefix = `--${name}=`;
  const hit = process.argv.slice(2).find((arg) => arg.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : fallback;
}

const LABEL = argValue('label', 'diag2');
const CDP_PORT = argValue('port', '9260');
const CDP_URL = `http://localhost:${CDP_PORT}`;
const TEST_HOME = path.join(__dirname, `.tauri-test-home-${LABEL}`);
const WEBVIEW_DATA = path.join(TEST_HOME, `webview-${LABEL}`);
const SHOTS = path.join(__dirname, 'screenshots', `dismissal-${LABEL}`);
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
  fs.mkdirSync(SHOTS, { recursive: true });
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
    const invoke = (command, args) => page.evaluate(({ command: c, args: a }) => window.__TAURI_INTERNALS__.invoke(c, a), { command, args });

    // Start a capture and select a region.
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('memopaws-capture')));
    await page.locator('.capture-overlay').waitFor({ state: 'visible', timeout: 20000 });
    await page.mouse.move(200, 200);
    await page.mouse.down();
    await page.mouse.move(600, 450, { steps: 6 });
    await page.mouse.up();
    await page.locator('.capture-overlay-rect').waitFor({ timeout: 10000 });

    // Grab the screen (not the webview) around the dismissal.
    const { execFileSync } = require('child_process');
    const grab = (index) => {
      const file = path.join(SHOTS, `frame-${String(index).padStart(2, '0')}.png`);
      // PowerShell screen capture: the whole virtual desktop.
      const script = `Add-Type -AssemblyName System.Windows.Forms,System.Drawing; $b=[System.Windows.Forms.SystemInformation]::VirtualScreen; $bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; $g=[System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); $bmp.Save('${file.replace(/\\/g, '\\\\')}',[System.Drawing.Imaging.ImageFormat]::Png)`;
      try { execFileSync('powershell', ['-NoProfile', '-Command', script], { stdio: 'pipe' }); } catch { /* ignore */ }
      return file;
    };

    const frames = [];
    // Pre-click frames (the overlay is up).
    frames.push(grab(0));
    await sleep(60);
    frames.push(grab(1));

    // Click 钉图 and sample the screen as fast as possible.
    await page.locator('.capture-overlay').getByRole('button', { name: 'Pin image' }).click();
    for (let index = 2; index < 22; index++) {
      frames.push(grab(index));
      await sleep(45);
    }

    // Report the window state next to the frames.
    console.log(`frames written to ${SHOTS}`);
    for (let index = 0; index < frames.length; index += 1) {
      const state = await invoke('plugin:window|is_visible').then((v) => `mainVisible=${v}`).catch(() => 'mainVisible=?');
      const position = await invoke('plugin:window|outer_position').then((p) => `pos=${p.x},${p.y}`).catch(() => 'pos=?');
      const fullscreen = await invoke('plugin:window|is_fullscreen').catch(() => '?');
      console.log(`frame ${String(index).padStart(2, '0')}: ${state} ${position} fullscreen=${fullscreen}`);
    }
    const pages = browser.contexts()[0].pages();
    console.log(`windows/pages: ${pages.length} -> ${pages.map((p) => p.url().split('#')[1] || 'main').join(', ')}`);
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
