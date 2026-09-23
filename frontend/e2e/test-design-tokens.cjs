// Playwright E2E: design token + theme contract
// Usage: node frontend/e2e/test-design-tokens.cjs (requires `npm --prefix frontend run dev` on :1420)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const BASE_URL = 'http://localhost:1420';
const MOCK_SCRIPT = fs.readFileSync(path.join(__dirname, 'mock-tauri.js'), 'utf-8');

const SCALE_TOKENS = [
  '--space-8', '--space-12', '--space-24',
  '--radius-8', '--radius-full',
  '--font-size-12', '--font-size-13', '--font-weight-600',
];
const SEMANTIC_TOKENS = ['--accent-contrast', '--success', '--warning', '--scrim'];

const EXPECTED = {
  light: { '--text-muted': '#75706A', '--accent-contrast': '#1C1B1A' },
  dark: { '--error': '#F87171', '--accent-contrast': '#262624' },
};

function assertEqual(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label}: expected "${expected}", got "${actual}"`);
}

async function readTokens(page, names) {
  return page.evaluate((list) => {
    const cs = getComputedStyle(document.documentElement);
    return Object.fromEntries(list.map((n) => [n, cs.getPropertyValue(n).trim()]));
  }, names);
}

async function runTests() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1460, height: 960 }, colorScheme: 'dark' });
  const page = await context.newPage();
  await page.addInitScript(MOCK_SCRIPT);
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);

  for (const theme of ['light', 'dark']) {
    await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);
    const tokens = await readTokens(page, [...SCALE_TOKENS, ...SEMANTIC_TOKENS, '--text-muted', '--error']);
    for (const name of [...SCALE_TOKENS, ...SEMANTIC_TOKENS]) {
      if (!tokens[name]) throw new Error(`Missing token ${name} in ${theme} theme`);
    }
    for (const [name, expected] of Object.entries(EXPECTED[theme])) {
      assertEqual(tokens[name].toUpperCase(), expected.toUpperCase(), `${theme} ${name}`);
    }
    console.log(`  ✓ ${theme} tokens present and calibrated`);
  }

  // Transition contract: the class applies a transition to descendants.
  const transition = await page.evaluate(() => {
    const root = document.documentElement;
    root.classList.add('theme-transitioning');
    const value = getComputedStyle(document.body).transitionProperty;
    root.classList.remove('theme-transitioning');
    return value;
  });
  if (!/background-color/.test(transition)) {
    throw new Error(`Expected .theme-transitioning to transition background-color, got "${transition}"`);
  }
  console.log('  ✓ theme transition rule present');

  // Shared component token contract (computed values must be unchanged by tokenization).
  // .seg-control only exists on pages with a SegmentedControl, so navigate to Settings first.
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.locator('.sidebar-item').filter({ hasText: '设置' }).click();
  await page.waitForTimeout(300);
  const seg = await page.locator('.seg-control').first().evaluate((el) => getComputedStyle(el).borderRadius);
  if (seg !== '8px') throw new Error(`Expected .seg-control border-radius 8px, got ${seg}`);
  const sidebarItem = await page.locator('.sidebar-item').first().evaluate((el) => getComputedStyle(el).fontSize);
  if (sidebarItem !== '13px') throw new Error(`Expected .sidebar-item font-size 13px, got ${sidebarItem}`);
  const activeSeg = await page.locator('.seg-control button.active').first().evaluate((el) => getComputedStyle(el).color);
  if (activeSeg !== 'rgb(38, 38, 36)') throw new Error(`Expected active segment color rgb(38, 38, 36) (--accent-contrast dark), got ${activeSeg}`);
  console.log('  ✓ shared component tokens applied');

  // Page accent-button text must use --accent-contrast in both themes (.settings-save is on Settings).
  for (const [theme, expected] of [['light', 'rgb(28, 27, 26)'], ['dark', 'rgb(38, 38, 36)']]) {
    await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);
    const btn = await page.locator('.settings-save').first().evaluate((el) => getComputedStyle(el).color);
    if (btn !== expected) throw new Error(`Expected .settings-save color ${expected} in ${theme}, got ${btn}`);
  }
  // No non-exempt hardcoded colors remain (shadows and over-media surfaces are exempt).
  const nonExempt = execSync(
    `grep -nE '#fff\\b|#3d9a5f|#c9a227|#2ecc71|rgb\\(0 0 0 / 45%\\)|rgba\\(5, 10, 25, 0\\.5\\)|rgba\\(20, 19, 17, 0\\.42\\)' ` +
    `frontend/src/pages/*.css frontend/src/components/GlobalSearch.css frontend/src/components/SegmentedControl.css || true`,
    { cwd: path.join(__dirname, '..', '..'), encoding: 'utf-8', shell: 'bash' }
  ).trim();
  if (nonExempt) throw new Error(`Unexpected hardcoded colors remain:\n${nonExempt}`);
  console.log('  ✓ page colors migrated');

  await browser.close();
  console.log('\nAll design token tests passed!');
}

runTests().catch((err) => { console.error('Test failed:', err); process.exit(1); });
