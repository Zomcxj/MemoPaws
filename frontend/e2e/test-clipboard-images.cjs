// Playwright E2E: clipboard image resource lifecycle (near-viewport thumbnails).
//
// Usage: keep `npm --prefix frontend run dev` running, then
//   node frontend/e2e/test-clipboard-images.cjs
//
// Covers: grid loads only near-viewport thumbnails (never the original bytes),
// offscreen thumbnails release, preview/copy always use the original image, and
// a failed thumbnail shows a retry button that recovers.

const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

// MEMOPAWS_E2E_BASE_URL overrides the dev server (e.g. when 1420 is taken by another project).
const BASE_URL = process.env.MEMOPAWS_E2E_BASE_URL || 'http://localhost:1420';
const MOCK_SCRIPT = fs.readFileSync(path.join(__dirname, 'mock-tauri.js'), 'utf-8');
const IMAGE_COUNT = 30;
const ORIGINAL_WIDTH = 128; // mock clipboard_get_image serves a 128x96 PNG
const THUMB_WIDTH = 8;      // mock clipboard_get_thumbnail serves an 8x8 PNG

async function thumbCalls(page) {
  return page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__
    .filter((call) => call.command === 'clipboard_get_thumbnail')
    .map((call) => call.args.id));
}

async function fullCalls(page) {
  return page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__
    .filter((call) => call.command === 'clipboard_get_image')
    .map((call) => call.args.id));
}

async function blobImageCount(page) {
  return page.locator('.clipboard-image-wrap img[src^="blob:"]').count();
}

async function openWithSeeds(browser, extraInit) {
  const context = await browser.newContext({ viewport: { width: 1460, height: 960 } });
  const page = await context.newPage();
  await page.addInitScript(MOCK_SCRIPT);
  await page.addInitScript((count) => {
    window.__MOCK_TAURI_SET_CLIPBOARD_ITEMS__(Array.from({ length: count }, (_, index) => ({
      id: index + 1,
      time: String(1700000000 + index),
      content_type: 'image',
      text: null,
      image_path: 'C:\seed\grid-image-' + (index + 1) + '.png',
    })));
  }, IMAGE_COUNT);
  if (extraInit) await page.addInitScript(extraInit);
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForLoadState('networkidle');
  await page.locator('.sidebar-item:has-text("剪切板")').click();
  await page.waitForTimeout(400);
  return { context, page };
}

async function nearViewportLoading(browser) {
  const { context, page } = await openWithSeeds(browser);
  try {
    await page.locator('.clipboard-view-toggle button[data-value="grid"]').click();
    await page.locator('.clipboard-image-wrap img[src^="blob:"]').first().waitFor({ timeout: 5000 });

    const seen = new Set(await thumbCalls(page));
    assert.ok(seen.size > 0, 'visible thumbnails must be requested');
    assert.ok(seen.size < IMAGE_COUNT, `first screen must not fetch every thumbnail (${seen.size}/${IMAGE_COUNT})`);
    assert.deepEqual(await fullCalls(page), [], 'grid must not fetch original images');

    const first = await blobImageCount(page);
    assert.ok(first < IMAGE_COUNT, 'blob images must stay bounded on first screen');

    // Scroll to the bottom: late items load through the same bounded queue.
    await page.locator('.clipboard-body').evaluate((el) => { el.scrollTop = el.scrollHeight; });
    await page.locator(`.clipboard-image-wrap[data-clipboard-id="${IMAGE_COUNT}"] img[src^="blob:"]`).waitFor({ timeout: 5000 });
    const bottomSeen = new Set(await thumbCalls(page));
    assert.ok(bottomSeen.has(IMAGE_COUNT), 'bottom item thumbnail must load after scrolling');
    const atBottom = await blobImageCount(page);

    // Scroll back to top: offscreen thumbnails release, placeholders return.
    await page.locator('.clipboard-body').evaluate((el) => { el.scrollTop = 0; });
    await page.waitForTimeout(800);
    const backTop = await blobImageCount(page);
    assert.ok(backTop < atBottom, `offscreen thumbnails must release (top ${backTop} < bottom ${atBottom})`);
    console.log('  near-viewport loading and offscreen release: ok');
  } finally {
    await context.close();
  }
}

async function previewAndCopyUseOriginal(browser) {
  const { context, page } = await openWithSeeds(browser);
  try {
    await page.locator('.clipboard-view-toggle button[data-value="grid"]').click();
    await page.locator('.clipboard-image-wrap img[src^="blob:"]').first().waitFor({ timeout: 5000 });

    await page.locator('.clipboard-image-open').first().click();
    await page.locator('.clipboard-preview').waitFor({ timeout: 5000 });
    const previewWidth = await page.locator('.clipboard-preview-stage img').evaluate((el) => el.naturalWidth);
    assert.equal(previewWidth, ORIGINAL_WIDTH, `preview must show the original (${ORIGINAL_WIDTH}px), not the ${THUMB_WIDTH}px thumbnail`);
    const previewId = await page.evaluate(() => {
      const calls = window.__MOCK_TAURI_COMMAND_CALLS__.filter((call) => call.command === 'clipboard_get_image');
      return calls.length && calls[calls.length - 1].args.id;
    });
    assert.equal(previewId, 1, 'preview must fetch the original for the previewed record');

    await page.keyboard.press('Escape');
    await page.locator('.clipboard-preview').waitFor({ state: 'detached', timeout: 5000 });

    await page.evaluate(() => {
      window.__COPIED_IMAGE__ = null;
      navigator.clipboard.write = async (items) => {
        for (const item of items) window.__COPIED_IMAGE__ = await item.getType('image/png');
      };
    });
    await page.locator('.clipboard-item').first().locator('.clipboard-copy').click();
    await page.waitForFunction(() => window.__COPIED_IMAGE__ !== null, null, { timeout: 5000 });
    const copied = await page.evaluate(async () => {
      const bitmap = await createImageBitmap(window.__COPIED_IMAGE__);
      const dims = { width: bitmap.width, height: bitmap.height };
      bitmap.close();
      return dims;
    });
    assert.deepEqual(copied, { width: ORIGINAL_WIDTH, height: 96 }, 'copied blob must decode to the original size');
    console.log('  preview and copy use the original image: ok');
  } finally {
    await context.close();
  }
}

async function thumbnailFailureRetries(browser) {
  const { context, page } = await openWithSeeds(browser, () => {
    window.__MOCK_TAURI_FAIL_THUMB_ONCE__(1);
  });
  try {
    await page.locator('.clipboard-view-toggle button[data-value="grid"]').click();
    const retry = page.locator('.clipboard-image-wrap').first().locator('.clipboard-image-load');
    await retry.waitFor({ timeout: 5000 });
    // The other visible thumbnails keep loading despite the single failure.
    await page.locator('.clipboard-image-wrap img[src^="blob:"]').first().waitFor({ timeout: 5000 });

    await retry.click();
    await page.locator('.clipboard-image-wrap').first().locator('img[src^="blob:"]').waitFor({ timeout: 5000 });
    console.log('  thumbnail failure shows retry and recovers: ok');
  } finally {
    await context.close();
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    await nearViewportLoading(browser);
    await previewAndCopyUseOriginal(browser);
    await thumbnailFailureRetries(browser);
    console.log('Clipboard image resource tests passed.');
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
