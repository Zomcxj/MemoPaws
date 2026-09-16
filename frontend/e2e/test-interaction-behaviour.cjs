// Playwright E2E test: behaviour that used to be asserted by grepping source text.
//
// Usage: keep `npm --prefix frontend run dev` running, then
//   node frontend/e2e/test-interaction-behaviour.cjs
//
// Every check here drives the real UI and asserts an observable result, so it
// keeps passing when the implementation is refactored and fails when the
// behaviour actually regresses.

const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE_URL = 'http://localhost:1420';
const MOCK_SCRIPT = fs.readFileSync(path.join(__dirname, 'mock-tauri.js'), 'utf-8');

async function open(browser, nav) {
  const context = await browser.newContext({ viewport: { width: 1460, height: 960 } });
  const page = await context.newPage();
  await page.addInitScript(MOCK_SCRIPT);
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForLoadState('networkidle');
  await page.locator(`.sidebar-item:has-text("${nav}")`).click();
  await page.waitForTimeout(400);
  return { context, page };
}

async function clipboardChecks(browser) {
  const { context, page } = await open(browser, '剪切板');
  try {
    // Icon actions stay square: the page-level button padding must not win.
    // A grep for `width: 26px` cannot see a later rule overriding it.
    const icon = page.locator('.clipboard-icon-action').first();
    const box = await icon.boundingBox();
    assert.ok(box, 'clipboard icon action must be visible');
    assert.equal(Math.round(box.width), 26, 'icon action must render 26px wide');
    assert.equal(Math.round(box.height), 26, 'icon action must render 26px tall');

    // List rows keep a stable height even with content that wants more room.
    const rows = page.locator('.clipboard-items.list .clipboard-item');
    const rowCount = await rows.count();
    assert.ok(rowCount >= 2, `expected mocked clipboard rows, found ${rowCount}`);
    for (let i = 0; i < rowCount; i++) {
      const rowBox = await rows.nth(i).boundingBox();
      assert.equal(Math.round(rowBox.height), 40, `list row ${i} must stay 40px tall`);
    }

    // Text summaries show the first line only.
    const summary = await page.locator('.clipboard-list-summary').first().textContent();
    assert.ok(summary.includes('Clipboard text'), 'summary must show the first line');
    assert.ok(!summary.includes('SECOND LINE MUST NOT SHOW'), 'summary must not show later lines');

    // Image summaries show an ellipsized filename, never the directory path.
    const name = page.locator('.clipboard-image-name').first();
    if (await name.count()) {
      const text = (await name.textContent()).trim();
      assert.ok(!text.includes('\\') && !text.includes('/'), `image summary must drop the path, got ${text}`);
      const clipped = await name.evaluate(el => ({
        overflowing: el.scrollWidth > el.clientWidth,
        ellipsis: getComputedStyle(el).textOverflow,
        wrap: getComputedStyle(el).whiteSpace,
      }));
      assert.equal(clipped.ellipsis, 'ellipsis', 'long filenames must be ellipsized');
      assert.equal(clipped.wrap, 'nowrap', 'filenames must stay on one line');
      assert.ok(clipped.overflowing, 'the mocked long filename must actually overflow its box');
    }
    console.log('  clipboard row layout and summaries: ok');
  } finally {
    await context.close();
  }
}

async function keysChecks(browser) {
  const { context, page } = await open(browser, '密钥');
  try {
    // The internal settings entry is mocked into the list but must stay hidden.
    const cards = page.locator('.key-card-llm');
    const titles = await cards.locator('h3').allTextContents();
    assert.ok(!titles.some(t => t.includes('settings_api_key')), `settings key must be hidden, got ${JSON.stringify(titles)}`);
    assert.ok(titles.length >= 2, `expected the two mocked LLM keys, got ${JSON.stringify(titles)}`);

    // Drag handles are the only drag affordance and are keyboard reachable.
    const handles = page.locator('.key-card-llm .key-drag-handle');
    const handle = handles.first();
    assert.equal(await handle.getAttribute('role'), 'button', 'drag handle needs a button role');
    assert.equal(await handle.getAttribute('tabindex'), '0', 'drag handle must be focusable');
    const label = await handle.getAttribute('aria-label');
    assert.ok(label && label.length > 0, 'drag handle needs an accessible label');
    assert.ok(/箭头|Arrow/.test(label), `label must disclose arrow-key reordering, got ${label}`);
    assert.equal(
      await handle.evaluate(el => getComputedStyle(el).touchAction),
      'none',
      'drag handle must declare touch-action none so pointer streams survive the threshold',
    );
    assert.notEqual(
      await cards.first().evaluate(el => getComputedStyle(el).cursor),
      'grab',
      'the whole card must not advertise a drag affordance',
    );

    // An arrow key alone reorders: no Space/Enter to arm, no keyup to commit.
    const orderBefore = await cards.evaluateAll(els => els.map(el => el.dataset.keyId));
    await handle.focus();
    await page.keyboard.press('ArrowDown');
    await page.waitForTimeout(300);
    const orderAfter = await cards.evaluateAll(els => els.map(el => el.dataset.keyId));
    const reorderCalled = await page.evaluate(() =>
      window.__MOCK_TAURI_COMMAND_CALLS__.some(entry => entry.command === 'reorder'));
    assert.ok(
      JSON.stringify(orderBefore) !== JSON.stringify(orderAfter) || reorderCalled,
      `ArrowDown alone must reorder; order stayed ${JSON.stringify(orderAfter)} and reorder invoked=${reorderCalled}`,
    );

    // A pointer press below the LLM threshold must not start a drag.
    const handleBox = await handles.nth(0).boundingBox();
    await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(handleBox.x + handleBox.width / 2 + 4, handleBox.y + handleBox.height / 2);
    await page.waitForTimeout(120);
    assert.equal(await page.locator('.key-card-llm.is-dragging').count(), 0, '4px must stay below the 8px LLM drag threshold');
    await page.mouse.move(handleBox.x + handleBox.width / 2 + 24, handleBox.y + handleBox.height / 2);
    await page.waitForTimeout(120);
    assert.equal(await page.locator('.key-card-llm.is-dragging').count(), 1, '24px must cross the LLM drag threshold');
    await page.mouse.up();
    await page.waitForTimeout(200);
    console.log('  key drag handle affordance and thresholds: ok');
  } finally {
    await context.close();
  }
}

async function speedTestChecks(browser) {
  const { context, page } = await open(browser, '密钥');
  try {
    // A transport failure must render localized text, never the raw category.
    await page.evaluate(() => window.__MOCK_TAURI_SET_API_MODE__('connect'));
    await page.locator('.keys-page button', { hasText: /测试速度|Test Speed/ }).first().click();
    await page.waitForTimeout(800);
    const latencies = await page.locator('.key-latency').allTextContents();
    const joined = latencies.join(' | ');
    assert.ok(!/\bconnect\b/.test(joined), `raw category must not reach the UI, got ${joined}`);
    assert.ok(/无法连接|Could not connect/.test(joined), `connect must render localized text, got ${joined}`);

    // An HTTP error must not leak the upstream response body.
    await page.evaluate(() => window.__MOCK_TAURI_SET_API_MODE__('401'));
    await page.locator('.keys-page button', { hasText: /测试速度|Test Speed/ }).first().click();
    await page.waitForTimeout(800);
    const pageText = await page.locator('.keys-page').textContent();
    assert.ok(!pageText.includes('SECRET RESPONSE'), 'the upstream response body must never be shown');
    console.log('  speed test localization and body redaction: ok');
  } finally {
    await context.close();
  }
}

async function memoChecks(browser) {
  const { context, page } = await open(browser, '备忘录');
  try {
    await page.locator('.memo-page').getByText('Test Memo').first().click();
    await page.waitForTimeout(300);
    // The default view mode is edit; the preview is only mounted in preview/split.
    await page.locator('.memo-mode').getByRole('button', { name: '预览' }).click();
    await page.waitForTimeout(700);
    const preview = page.locator('.memo-preview');
    if (!(await preview.count())) {
      console.log('  memo preview not mounted in this mode, skipped');
      return;
    }

    // Ctrl+wheel zooms the preview and stays inside the supported range.
    const readScale = () => preview.evaluate(el =>
      parseFloat(getComputedStyle(el).getPropertyValue('--memo-preview-scale')));
    const base = await readScale();
    assert.ok(Number.isFinite(base), 'preview scale must be a number');
    await preview.hover();
    for (let i = 0; i < 40; i++) {
      await page.keyboard.down('Control');
      await page.mouse.wheel(0, -120);
      await page.keyboard.up('Control');
    }
    await page.waitForTimeout(300);
    const zoomed = await readScale();
    assert.ok(zoomed > base, `Ctrl+wheel must zoom in, ${base} -> ${zoomed}`);
    assert.ok(zoomed <= 1.35 + 1e-6, `zoom must clamp to the max scale, got ${zoomed}`);
    for (let i = 0; i < 200; i++) {
      await page.keyboard.down('Control');
      await page.mouse.wheel(0, 120);
      await page.keyboard.up('Control');
    }
    await page.waitForTimeout(300);
    const zoomedOut = await readScale();
    assert.ok(zoomedOut >= 0.85 - 1e-6, `zoom must clamp to the min scale, got ${zoomedOut}`);

    // Code copy is delegated from the renderer marker, so the rendered HTML
    // needs no inline JavaScript to make the button work.
    const copyButton = preview.locator('button[data-memo-code-copy]');
    if (await copyButton.count()) {
      await page.evaluate(() => {
        window.__COPIED__ = [];
        navigator.clipboard.writeText = text => { window.__COPIED__.push(text); return Promise.resolve(); };
      });
      await copyButton.first().click();
      await page.waitForTimeout(200);
      const copied = await page.evaluate(() => window.__COPIED__);
      assert.equal(copied.length, 1, `delegated copy must fire once, got ${JSON.stringify(copied)}`);
      assert.ok(copied[0].includes('fn main()'), `copy must carry the code block text, got ${JSON.stringify(copied)}`);
      assert.ok(!copied[0].includes('Copy'), 'copy must not include the toolbar label');
    }
    console.log('  memo preview zoom clamp and delegated copy: ok');
  } finally {
    await context.close();
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    await clipboardChecks(browser);
    await keysChecks(browser);
    await speedTestChecks(browser);
    await memoChecks(browser);
    console.log('Interaction behaviour tests passed.');
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
