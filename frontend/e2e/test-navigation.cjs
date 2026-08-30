// Playwright E2E test: Navigation and interaction
// Usage: python scripts/with_server.py --server "npm run dev" --port 1420 -- node frontend/e2e/test-navigation.cjs

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:1420';
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');
const MOCK_SCRIPT = fs.readFileSync(path.join(__dirname, 'mock-tauri.js'), 'utf-8');

const NAV_LABELS = ['识别', '备忘录', '密钥', '剪切板', '设置'];
const NAV_SELECTORS = {
  '识别': '.recognize-page',
  '备忘录': '.memo-page',
  '密钥': '.keys-page',
  '剪切板': '.clipboard-page',
  '设置': '.settings-page',
};

async function assertCanonicalPage(page, expectedSelector) {
  const selectors = Object.values(NAV_SELECTORS);
  const counts = await Promise.all(selectors.map(selector => page.locator(selector).count()));
  const total = counts.reduce((sum, count) => sum + count, 0);
  const expectedIndex = selectors.indexOf(expectedSelector);
  if (total !== 1 || counts[expectedIndex] !== 1) {
    throw new Error(`Expected exactly one canonical page selector total for ${expectedSelector}, found total=${total}, counts=${JSON.stringify(counts)}`);
  }
}

async function runTests() {
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  }

  console.log('Launching browser...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1460, height: 960 } });
  const page = await context.newPage();

  await page.addInitScript(MOCK_SCRIPT);

  console.log(`Navigating to ${BASE_URL}...`);
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  await assertCanonicalPage(page, NAV_SELECTORS['识别']);

  // Test 1: Click through all nav items
  console.log('\n--- Test 1: Navigation clicks ---');
  for (let i = 0; i < NAV_LABELS.length; i++) {
    const label = NAV_LABELS[i];
    const num = String(i + 1).padStart(2, '0');
    console.log(`Clicking: ${label}`);

    const btn = page.locator(`.sidebar-item:has-text("${label}")`);
    if (await btn.count() !== 1) {
      throw new Error(`Expected one navigation button for ${label}, found ${await btn.count()}`);
    }
    await btn.click();
    await page.waitForTimeout(500);
    const pageSelector = NAV_SELECTORS[label];
    await assertCanonicalPage(page, pageSelector);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, `nav-${num}-${label}.png`) });
    console.log(`  ✓ Clicked and screenshot taken`);
  }

  // Test 2: Rapid navigation (stress test)
  console.log('\n--- Test 2: Rapid navigation ---');
  for (let i = 0; i < 3; i++) {
    for (const label of NAV_LABELS) {
      const btn = page.locator(`.sidebar-item:has-text("${label}")`);
      if (await btn.count() !== 1) {
        throw new Error(`Expected one navigation button for rapid navigation label ${label}, found ${await btn.count()}`);
      }
      await btn.click();
      await page.waitForTimeout(100);
      const pageSelector = NAV_SELECTORS[label];
       await assertCanonicalPage(page, pageSelector);
    }
  }
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'nav-rapid-final.png') });
  console.log('  ✓ Rapid navigation completed');

  // Test 3: Theme toggle
  console.log('\n--- Test 3: Theme toggle ---');
  const settingsBtn = page.locator('.sidebar-item:has-text("设置")');
  const settingsBtnCount = await settingsBtn.count();
  if (settingsBtnCount !== 1) {
    throw new Error(`Expected exactly one Settings navigation button, found ${settingsBtnCount}`);
  }
  await settingsBtn.click();
  await page.waitForTimeout(500);

  const sidebarThemeBtn = page.locator('.sidebar-footer .sidebar-item');
  if (await sidebarThemeBtn.count() !== 0) {
    throw new Error('Unexpected Sidebar theme button found');
  }
  console.log('  ✓ No Sidebar theme button found');

   const themeGroup = page.locator('.settings-segmented[role="group"][aria-label="主题模式"]');
  if (await themeGroup.count() !== 1) {
    throw new Error(`Expected one Settings theme control group, found ${await themeGroup.count()}`);
  }
  const lightThemeBtn = themeGroup.locator('button').filter({ hasText: '亮色' });
  const darkThemeBtn = themeGroup.locator('button').filter({ hasText: '暗色' });
  if (await lightThemeBtn.count() !== 1 || await darkThemeBtn.count() !== 1) {
    const buttonTexts = await themeGroup.locator('button').allTextContents();
    throw new Error(`Settings theme buttons 亮色 and 暗色 are required (group=${await themeGroup.count()}, light=${await lightThemeBtn.count()}, dark=${await darkThemeBtn.count()}, buttons=${JSON.stringify(buttonTexts)})`);
  }

  await lightThemeBtn.click();
  await page.waitForTimeout(300);
  const lightTheme = await page.evaluate(() => document.documentElement.dataset.theme);
  if (lightTheme !== 'light') {
    throw new Error(`Expected document theme to be light, found ${lightTheme}`);
  }
  const lightPressed = await lightThemeBtn.getAttribute('aria-pressed');
  const darkPressedAfterLight = await darkThemeBtn.getAttribute('aria-pressed');
  if (lightPressed !== 'true' || darkPressedAfterLight !== 'false') {
    throw new Error(`Expected light theme button aria-pressed=true and dark theme button aria-pressed=false, found light=${lightPressed}, dark=${darkPressedAfterLight}`);
  }
  console.log('  ✓ 亮色 sets document.documentElement.dataset.theme to light');

  await darkThemeBtn.click();
  await page.waitForTimeout(300);
  const darkTheme = await page.evaluate(() => document.documentElement.dataset.theme);
  if (darkTheme !== 'dark') {
    throw new Error(`Expected document theme to be dark, found ${darkTheme}`);
  }
  const darkPressed = await darkThemeBtn.getAttribute('aria-pressed');
  const lightPressedAfterDark = await lightThemeBtn.getAttribute('aria-pressed');
  if (darkPressed !== 'true' || lightPressedAfterDark !== 'false') {
    throw new Error(`Expected dark theme button aria-pressed=true and light theme button aria-pressed=false, found dark=${darkPressed}, light=${lightPressedAfterDark}`);
  }
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'theme-toggled.png') });
  console.log('  ✓ 暗色 sets document.documentElement.dataset.theme to dark');

  const themeCalls = await page.evaluate(() => window.__MOCK_TAURI_THEME_CALLS__);
  if (JSON.stringify(themeCalls) !== JSON.stringify(['light', 'dark'])) {
    throw new Error(`Expected set_theme calls for selected values, found ${JSON.stringify(themeCalls)}`);
  }
  console.log('  ✓ set_theme received light and dark');

  console.log('\n--- Test 4: Settings interactions ---');
  const settings = page.locator('.settings-page');
  for (const heading of ['主题', '语言', 'API 配置', '剪贴板设置', '操作历史', '存储目录', '快捷键', '关闭行为']) {
    if (await settings.getByRole('heading', { name: heading }).count() !== 1) throw new Error(`Missing settings section ${heading}`);
  }
  await settings.getByLabel('剪贴板设置最大条数').fill('80');
  await settings.getByLabel('操作历史最大条数').fill('120');
  await settings.getByRole('button', { name: '退出' }).click();
  await settings.locator('input[aria-label*="截图识别"]').press('Control+Y');
  await settings.getByRole('button', { name: '测试连接' }).click();
  await page.waitForTimeout(100);
  if ((await settings.textContent()).includes('SECRET RESPONSE') || (await settings.textContent()).includes('PRIVATE BODY')) throw new Error('API response body exposed');
  await settings.locator('.settings-footer').getByRole('button', { name: '保存设置' }).click();
  await page.waitForTimeout(100);
  const runtimeUpdates = await page.evaluate(() => window.__MOCK_TAURI_RUNTIME_UPDATES__);
  for (const command of ['set_close_behavior']) {
    if (!runtimeUpdates.some((entry) => entry.command === command)) throw new Error(`Missing runtime update ${command}`);
  }
  const commandCalls = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__);
  if (!commandCalls.some((entry) => entry.command === 'save_config')) throw new Error('Missing save_config command call');

  await lightThemeBtn.click();
  await page.waitForTimeout(300);
  await page.evaluate(() => localStorage.setItem('memopaws-theme', 'dark'));
  await page.reload();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
  const reloadedTheme = await page.evaluate(() => document.documentElement.dataset.theme);
  if (reloadedTheme !== 'light') {
    throw new Error(`Expected reload to use persisted mock backend theme light, found ${reloadedTheme}`);
  }
  console.log('  ✓ reload uses persisted mock backend theme instead of stale localStorage');

  // Test 5: Verify page elements exist
  console.log('\n--- Test 5: Page element verification ---');
  // Go to recognize page
  const recognizeBtn = page.locator('.sidebar-item:has-text("图片识别")');
  if (await recognizeBtn.count() !== 1) {
    throw new Error(`Expected one navigation button for 图片识别, found ${await recognizeBtn.count()}`);
  }
  await recognizeBtn.click();
  await page.waitForTimeout(500);
  await assertCanonicalPage(page, NAV_SELECTORS['识别']);

  // Check for key elements
  const checks = [
    { selector: '.sidebar', name: 'Sidebar' },
    { selector: '.recognize-page', name: 'Recognize Page' },
    { selector: '.recognize-toolbar', name: 'Recognize Toolbar' },
    { selector: '.sidebar-nav', name: 'Navigation' },
  ];

  for (const check of checks) {
    const el = page.locator(check.selector);
    const count = await el.count();
    if (count !== 1) {
      throw new Error(`Required page element must appear exactly once: ${check.name} (${check.selector}), found ${count}`);
    }
    console.log(`  ${check.name}: ✓`);
  }

  await browser.close();
  console.log('\nAll navigation tests completed!');
}

runTests().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
