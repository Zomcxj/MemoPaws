// Playwright E2E test: the built Tauri app driven over its native WebView2 CDP.
//
// Parameterised so several instances can run without colliding. Each run needs
// its own CDP port, MEMOPAWS_HOME and WebView2 user-data folder, otherwise the
// second app attaches to the first one's debugger and profile:
//
//   node e2e/test-tauri-native.cjs                      # defaults (label "app", port 9222)
//   node e2e/test-tauri-native.cjs --label=driver --port=9223
//
// `MEMOPAWS_HOME` is what keeps the real `%USERPROFILE%\.memopaws` untouched;
// `dirs::home_dir()` reads the Win32 known-folder API, so overriding
// HOME/USERPROFILE alone is not enough.

const { chromium } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function argValue(name, fallback) {
  const prefix = `--${name}=`;
  const hit = process.argv.slice(2).find(arg => arg.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : fallback;
}

const LABEL = argValue('label', process.env.TAURI_TEST_LABEL || 'app');
const CDP_PORT = argValue('port', process.env.TAURI_CDP_PORT || '9222');
const CDP_URL = process.env.TAURI_CDP_URL || `http://localhost:${CDP_PORT}`;
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots', `tauri-${LABEL}`);
const TEST_HOME = path.join(__dirname, `.tauri-test-home-${LABEL}`);
const WEBVIEW_DATA = path.join(TEST_HOME, `webview-${LABEL}`);

const DESTINATIONS = {
  '识别': '.recognize-page',
  '备忘录': '.memo-page',
  '密钥': '.keys-page',
  '剪切板': '.clipboard-page',
  '设置': '.settings-page',
};
const PAGES = [
  { name: 'recognize', nav: '识别' },
  { name: 'memo', nav: '备忘录' },
  { name: 'keys', nav: '密钥' },
  { name: 'clipboard', nav: '剪切板' },
  { name: 'settings', nav: '设置' },
];

function findTauriExe() {
  const candidates = [
    path.join(__dirname, '..', '..', 'target', 'release', 'memopaws.exe'),
    path.join(__dirname, '..', '..', 'target', 'debug', 'memopaws.exe'),
    path.join(__dirname, '..', '..', 'crates', 'tauri', 'target', 'release', 'memopaws.exe'),
    path.join(__dirname, '..', '..', 'crates', 'tauri', 'target', 'debug', 'memopaws.exe'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error('Native Tauri runtime unavailable: executable not found. Run cargo build -p memopaws-tauri --release');
}

async function runTests() {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  fs.rmSync(TEST_HOME, { recursive: true, force: true });
  fs.mkdirSync(TEST_HOME, { recursive: true });

  const tauriExe = findTauriExe();
  console.log(`[${LABEL}] Tauri executable:`, tauriExe);
  const tauriProcess = spawn(tauriExe, [], {
    stdio: 'pipe',
    detached: false,
    env: {
      ...process.env,
      HOME: TEST_HOME,
      USERPROFILE: TEST_HOME,
      MEMOPAWS_HOME: TEST_HOME,
      WEBVIEW2_USER_DATA_FOLDER: WEBVIEW_DATA,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${CDP_PORT} --remote-allow-origins=*`,
    },
  });
  let browser;

  try {
    console.log(`[${LABEL}] Launching Tauri app; waiting for native CDP at ${CDP_URL}...`);
    await new Promise(resolve => setTimeout(resolve, 3000));
    // A blank Chromium page is not a native-app test, so CDP is mandatory.
    try {
      browser = await chromium.connectOverCDP(CDP_URL);
    } catch (err) {
      throw new Error(`Native Tauri/CDP runtime unavailable on ${CDP_URL}; no UI actions were run: ${err.message}`);
    }

    const context = browser.contexts()[0] || await browser.newContext({ viewport: { width: 1460, height: 960 } });
    const page = context.pages()[0] || await context.newPage();
    await page.waitForTimeout(2000);

    async function assertCanonicalPage(expectedNav) {
      const selectors = Object.values(DESTINATIONS);
      const counts = await Promise.all(selectors.map(selector => page.locator(selector).count()));
      const total = counts.reduce((sum, count) => sum + count, 0);
      const expectedIndex = selectors.indexOf(DESTINATIONS[expectedNav]);
      if (total !== 1 || counts[expectedIndex] !== 1) {
        throw new Error(`Expected exactly one canonical page selector total for ${expectedNav}, found total=${total}, counts=${JSON.stringify(counts)}`);
      }
    }

    await assertCanonicalPage('识别');
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01-default.png'), fullPage: false });

    for (let i = 0; i < PAGES.length; i++) {
      const { name, nav } = PAGES[i];
      const button = page.locator('.sidebar-item').filter({ hasText: nav });
      if (await button.count() !== 1) throw new Error(`Expected exactly one navigation button for ${nav}`);
      await button.click();
      await page.waitForTimeout(500);
      await assertCanonicalPage(nav);
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, `${String(i + 2).padStart(2, '0')}-${name}.png`), fullPage: false });
    }

    // Settings owns the only theme control: exactly two mutually exclusive buttons.
    const settingsButton = page.locator('.sidebar-item').filter({ hasText: '设置' });
    if (await settingsButton.count() !== 1) throw new Error('Expected exactly one Settings navigation button');
    await settingsButton.click();
    await page.waitForTimeout(500);
    await assertCanonicalPage('设置');

    const themeGroup = page.locator('.settings-segmented[role="group"]');
    if (await themeGroup.count() !== 1 || await themeGroup.locator('button').count() !== 2) {
      throw new Error('Expected exactly one Settings theme control with two buttons');
    }
    const light = themeGroup.locator('button').filter({ hasText: '亮色' });
    const dark = themeGroup.locator('button').filter({ hasText: '暗色' });
    if (await light.count() !== 1 || await dark.count() !== 1) throw new Error('Settings theme buttons 亮色 and 暗色 are required');
    if (await page.locator('.sidebar-footer .sidebar-item').count() !== 0) throw new Error('Expected no Sidebar theme button');

    await light.click();
    await page.waitForTimeout(500);
    if (await page.evaluate(() => document.documentElement.dataset.theme) !== 'light' || await light.getAttribute('aria-pressed') !== 'true' || await dark.getAttribute('aria-pressed') !== 'false') {
      throw new Error('Light theme dataset/aria assertions failed');
    }
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '07-theme-light.png'), fullPage: false });

    await dark.click();
    await page.waitForTimeout(500);
    if (await page.evaluate(() => document.documentElement.dataset.theme) !== 'dark' || await dark.getAttribute('aria-pressed') !== 'true' || await light.getAttribute('aria-pressed') !== 'false') {
      throw new Error('Dark theme dataset/aria assertions failed');
    }
    console.log(`[${LABEL}] Native Tauri tests completed!`);
  } finally {
    try {
      if (browser) await browser.close();
    } finally {
      if (!tauriProcess.killed) {
        if (process.platform === 'win32') {
          // /t /f kills the WebView2 child processes too, which otherwise keep
          // the user-data folder locked and make the rmSync below fail.
          spawnSync('taskkill', ['/pid', String(tauriProcess.pid), '/t', '/f']);
        } else {
          tauriProcess.kill();
        }
      }
      if (tauriProcess.exitCode === null) await new Promise(resolve => tauriProcess.once('exit', resolve));
      for (let attempt = 0; attempt < 10; attempt++) {
        try {
          fs.rmSync(TEST_HOME, { recursive: true, force: true });
          break;
        } catch (error) {
          if (!['EPERM', 'ENOTEMPTY', 'EBUSY'].includes(error.code) || attempt === 9) throw error;
          await new Promise(resolve => setTimeout(resolve, 200));
        }
      }
    }
  }
}

runTests().catch(err => {
  console.error(`[${LABEL}] Test failed:`, err);
  process.exit(1);
});
