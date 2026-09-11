// Standalone Playwright smoke test for the built Tauri app over native CDP.

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots', 'tauri');
const CDP_URL = process.env.TAURI_CDP_URL || 'http://localhost:9222';

// Find the Tauri executable
function findTauriExe() {
  const possiblePaths = [
    path.join(__dirname, '..', '..', 'target', 'release', 'memopaws.exe'),
    path.join(__dirname, '..', '..', 'target', 'debug', 'memopaws.exe'),
    path.join(__dirname, '..', '..', 'crates', 'tauri', 'target', 'release', 'memopaws.exe'),
    path.join(__dirname, '..', '..', 'crates', 'tauri', 'target', 'debug', 'memopaws.exe'),
  ];
  for (const p of possiblePaths) {
    if (fs.existsSync(p)) return p;
  }
  throw new Error('Tauri executable not found. Run: cargo build -p memopaws-tauri --release');
}

async function runTests() {
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  }

  const tauriExe = findTauriExe();
  console.log('Tauri executable:', tauriExe);

  // An external launcher must expose the configured native CDP endpoint.
  const tauriProcess = require('child_process').spawn(tauriExe, [], {
    stdio: 'pipe',
  });

  let browser;
  try {
    console.log(`Launching Tauri app; waiting for external CDP at ${CDP_URL}...`);
    await new Promise(resolve => setTimeout(resolve, 3000)); // Wait for app to start

    // A blank Chromium page is not a native-app test, so CDP is mandatory.
    try {
      browser = await chromium.connectOverCDP(CDP_URL);
    } catch (err) {
      throw new Error(`Native Tauri/CDP runtime unavailable on ${CDP_URL}; ensure an external launcher exposes CDP there. Native execution was not run: ${err.message}`);
    }
    console.log('Connected to native Tauri app via CDP');

    const context = browser.contexts()[0] || await browser.newContext({ viewport: { width: 1460, height: 960 } });
    const page = context.pages()[0] || await context.newPage();

  await page.waitForTimeout(2000);

  const destinations = {
    '识别': '.recognize-page',
    '备忘录': '.memo-page',
    '密钥': '.keys-page',
    '剪切板': '.clipboard-page',
    '设置': '.settings-page',
  };
  async function assertCanonicalPage(expectedNav) {
    const selectors = Object.values(destinations);
    const counts = await Promise.all(selectors.map(selector => page.locator(selector).count()));
    const total = counts.reduce((sum, count) => sum + count, 0);
    const expectedIndex = selectors.indexOf(destinations[expectedNav]);
    if (total !== 1 || counts[expectedIndex] !== 1) {
      throw new Error(`Expected exactly one canonical page selector total for ${expectedNav}, found total=${total}, counts=${JSON.stringify(counts)}`);
    }
  }

  await assertCanonicalPage('识别');

  // Take screenshots of each page
  const pages = [
    { name: 'recognize', nav: '识别' },
    { name: 'memo', nav: '备忘录' },
    { name: 'keys', nav: '密钥' },
    { name: 'clipboard', nav: '剪切板' },
    { name: 'settings', nav: '设置' },
  ];

  // Screenshot default page
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01-default.png'), fullPage: false });
  console.log('Screenshot: 01-default.png');

  for (let i = 0; i < pages.length; i++) {
    const { name, nav } = pages[i];
    const num = String(i + 1).padStart(2, '0');

    const btn = page.locator('.sidebar-item').filter({ hasText: nav });
    const buttonCount = await btn.count();
    if (buttonCount !== 1) {
      throw new Error(`Expected exactly one navigation button for ${nav}, found ${buttonCount}`);
    }
    await btn.click();
    await page.waitForTimeout(500);
    await assertCanonicalPage(nav);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, `${num}-${name}.png`), fullPage: false });
    console.log(`Screenshot: ${num}-${name}.png`);
  }

  // Settings owns the only theme control: exactly two mutually exclusive buttons.
  const settingsBtn = page.locator('.sidebar-item:has-text("设置")');
  if (await settingsBtn.count() !== 1) {
    throw new Error(`Expected exactly one Settings navigation button, found ${await settingsBtn.count()}`);
  }
  await settingsBtn.click();
  await page.waitForTimeout(500);
  const themeGroup = page.locator('.settings-segmented[role="group"]');
  if (await themeGroup.count() !== 1) {
    throw new Error(`Expected exactly one Settings theme control, found ${await themeGroup.count()}`);
  }
  const themeButtons = themeGroup.locator('button');
  if (await themeButtons.count() !== 2) {
    throw new Error(`Expected exactly two Settings theme buttons, found ${await themeButtons.count()}`);
  }
  const lightThemeBtn = themeButtons.filter({ hasText: '亮色' });
  const darkThemeBtn = themeButtons.filter({ hasText: '暗色' });
  if (await lightThemeBtn.count() !== 1 || await darkThemeBtn.count() !== 1) {
    throw new Error('Settings theme buttons 亮色 and 暗色 are required');
  }
  const sidebarThemeButton = page.locator('.sidebar-footer .sidebar-item');
  if (await sidebarThemeButton.count() !== 0) {
    throw new Error(`Expected no Sidebar theme button, found ${await sidebarThemeButton.count()}`);
  }
  await lightThemeBtn.click();
  await page.waitForTimeout(500);
  if (await page.evaluate(() => document.documentElement.dataset.theme) !== 'light') {
    throw new Error('Selecting 亮色 must set document.documentElement.dataset.theme to light');
  }
  if (await lightThemeBtn.getAttribute('aria-pressed') !== 'true' || await darkThemeBtn.getAttribute('aria-pressed') !== 'false') {
    throw new Error('亮色 must be pressed and 暗色 must not be pressed after selecting light theme');
  }
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '06-theme-light.png'), fullPage: false });
  console.log('Screenshot: 06-theme-light.png');

  await darkThemeBtn.click();
  await page.waitForTimeout(500);
  if (await page.evaluate(() => document.documentElement.dataset.theme) !== 'dark' ||
      await darkThemeBtn.getAttribute('aria-pressed') !== 'true' || await lightThemeBtn.getAttribute('aria-pressed') !== 'false') {
    throw new Error('Settings dark theme dataset/aria assertions failed');
  }

    console.log('\nTauri Driver tests completed!');
  } finally {
    try {
      if (browser) await browser.close();
    } finally {
      if (!tauriProcess.killed) tauriProcess.kill();
    }
  }
}

runTests().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
