// Playwright E2E test: Page screenshots
// Usage: python scripts/with_server.py --server "npm run dev" --port 1420 -- node frontend/e2e/test-pages.cjs

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:1420';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');
const MOCK_SCRIPT = fs.readFileSync(path.join(__dirname, 'mock-tauri.js'), 'utf-8');

const PAGES = [
  { name: 'recognize', label: '识别页', selector: '.recognize-page' },
  { name: 'memo', label: '备忘录页', selector: '.memo-page' },
  { name: 'keys', label: '密钥页', selector: '.keys-page' },
  { name: 'clipboard', label: '剪切板页', selector: '.clipboard-page' },
  { name: 'settings', label: '设置页', selector: '.settings-page' },
];

const NAV_LABELS = {
  recognize: '识别',
  memo: '备忘录',
  keys: '密钥',
  clipboard: '剪切板',
  settings: '设置',
};

async function assertCanonicalPage(page, expectedName) {
  const counts = await Promise.all(PAGES.map(({ selector }) => page.locator(selector).count()));
  const total = counts.reduce((sum, count) => sum + count, 0);
  const expectedIndex = PAGES.findIndex(({ name }) => name === expectedName);
  if (total !== 1 || counts[expectedIndex] !== 1) {
    throw new Error(`Expected exactly one canonical page selector total for "${expectedName}", found total=${total}, counts=${JSON.stringify(counts)}`);
  }
}

async function runTests() {
  // Ensure screenshots directory exists
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  }

  console.log('Launching browser...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1460, height: 960 } });
  const page = await context.newPage();

  // Inject mock Tauri API before navigation
  await page.addInitScript(MOCK_SCRIPT);

  console.log(`Navigating to ${BASE_URL}...`);
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000); // Wait for React to render

  await assertCanonicalPage(page, 'recognize');

  // Take initial screenshot (recognize page is default)
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01-recognize-default.png'), fullPage: false });
  console.log('Screenshot: 01-recognize-default.png');

  // Click through each page and take screenshots
  for (let i = 0; i < PAGES.length; i++) {
    const { name, label, selector } = PAGES[i];
    const navLabel = NAV_LABELS[name];
    const num = String(i + 1).padStart(2, '0');

    console.log(`Navigating to ${label} (${navLabel})...`);

    // Click the sidebar button
    const navButton = page.locator('.sidebar-item').filter({ hasText: navLabel });
    const navButtonCount = await navButton.count();
    if (navButtonCount !== 1) {
      throw new Error(`Expected exactly one navigation button for "${navLabel}", found ${navButtonCount}`);
    }
    await navButton.click();
    await page.waitForTimeout(500); // Wait for page transition

    await assertCanonicalPage(page, name);

    // Take screenshot
    const screenshotPath = path.join(SCREENSHOTS_DIR, `${num}-${name}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: false });
    console.log(`  Screenshot: ${num}-${name}.png`);

    console.log(`  ✓ Page loaded correctly (${selector})`);
  }

  // Take sidebar screenshot
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '06-sidebar.png'), fullPage: false });
  console.log('Screenshot: 06-sidebar.png');

  // Verify the Settings theme control is the only theme control.
  const sidebarThemeButton = page.locator('.sidebar-footer .sidebar-item');
  if (await sidebarThemeButton.count() !== 0) {
    throw new Error('Unexpected Sidebar theme button found');
  }
  const themeGroup = page.locator('.settings-segmented[role="group"][aria-label="主题模式"]');
  if (await themeGroup.count() !== 1 || await themeGroup.locator('button').count() !== 3) {
    throw new Error('Expected exactly one Settings theme control with three buttons');
  }
  const lightThemeButton = themeGroup.locator('button').filter({ hasText: '亮色' });
  const darkThemeButton = themeGroup.locator('button').filter({ hasText: '暗色' });
  const autoThemeButton = themeGroup.locator('button').filter({ hasText: '跟随系统' });
  if (await lightThemeButton.count() !== 1 || await darkThemeButton.count() !== 1 || await autoThemeButton.count() !== 1) {
    throw new Error('Expected 亮色/暗色/跟随系统 buttons in Settings');
  }
  const clippedThemeButtons = await themeGroup.locator('button').evaluateAll((els) =>
    els.filter((el) => el.scrollWidth > el.clientWidth).map((el) => `${el.textContent}(${el.scrollWidth}>${el.clientWidth})`)
  );
  if (clippedThemeButtons.length) {
    throw new Error(`Settings theme buttons clipped: ${clippedThemeButtons.join(', ')}`);
  }
  await lightThemeButton.click();
  await page.waitForTimeout(500);
  if (await page.evaluate(() => document.documentElement.dataset.theme) !== 'light' ||
      await lightThemeButton.getAttribute('aria-pressed') !== 'true' ||
      await darkThemeButton.getAttribute('aria-pressed') !== 'false') {
    throw new Error('Settings light theme assertions failed');
  }
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '07-theme-light.png'), fullPage: false });
  console.log('Screenshot: 07-theme-light.png');
  await darkThemeButton.click();
  await page.waitForTimeout(500);
  if (await page.evaluate(() => document.documentElement.dataset.theme) !== 'dark' ||
      await darkThemeButton.getAttribute('aria-pressed') !== 'true' ||
      await lightThemeButton.getAttribute('aria-pressed') !== 'false') {
    throw new Error('Settings dark theme assertions failed');
  }
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '08-theme-dark.png'), fullPage: false });
  console.log('Screenshot: 08-theme-dark.png');

  const settings = page.locator('.settings-page');
  for (const heading of ['主题', '语言', 'API 配置', '剪贴板设置', '操作历史', '存储目录', '快捷键', '关闭行为']) {
    if (await settings.getByRole('heading', { name: heading }).count() !== 1) throw new Error(`Missing settings section: ${heading}`);
  }
  await settings.getByRole('button', { name: 'English' }).click();
  await page.waitForTimeout(100);
  for (const text of ['Theme', 'Language', 'API Configuration', 'Clipboard Settings', 'History', 'Storage Directory', 'Keyboard Shortcuts', 'Close Behavior']) {
    if (await settings.getByText(text, { exact: true }).count() < 1) throw new Error(`Missing translated settings text: ${text}`);
  }
  if (await settings.getByRole('button', { name: 'System' }).count() !== 1) throw new Error('Missing translated auto theme option');
  if (await settings.getByText('test-api-key-12345', { exact: false }).count() !== 0) throw new Error('API key rendered in settings');
  await settings.getByRole('button', { name: '中文' }).click();

  await browser.close();
  console.log('\nAll tests completed! Screenshots saved to:', SCREENSHOTS_DIR);
}

runTests().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
