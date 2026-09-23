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

  await browser.close();
  console.log('\nAll design token tests passed!');
}

runTests().catch((err) => { console.error('Test failed:', err); process.exit(1); });
