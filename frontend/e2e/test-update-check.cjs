// Playwright E2E: the update-notification full chain — badge → card (event/mount paths) → download
// (offline/install/failure) → restart.
// Usage: keep `npm --prefix frontend run dev` running, then
//   node frontend/e2e/test-update-check.cjs

const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE_URL = 'http://localhost:1420';
const MOCK_SCRIPT = fs.readFileSync(path.join(__dirname, 'mock-tauri.js'), 'utf-8');

// initScript runs after the mock loads and before page scripts, used to preset latest_release_version / download modes
async function newPage(browser, initScript) {
  const context = await browser.newContext({ viewport: { width: 1460, height: 960 } });
  const page = await context.newPage();
  await page.addInitScript(MOCK_SCRIPT);
  if (initScript) await page.addInitScript(initScript);
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForLoadState('networkidle');
  return { context, page };
}

async function openSettings(page) {
  await page.locator('.sidebar-item').filter({ hasText: '设置' }).click();
  await page.waitForTimeout(400);
}

async function checkBadge(browser) {
  const { context, page } = await newPage(browser);
  try {
    assert.equal(await page.locator('.sidebar-update-dot').count(), 0, '初始状态不应有角标');

    await page.evaluate(() => window.__MOCK_EMIT_UPDATE__());
    await page.waitForTimeout(200);
    assert.equal(await page.locator('.sidebar-update-dot').count(), 1, '收到 update-available 后设置入口应有角标');
    console.log('  badge flow: ok');
  } finally {
    await context.close();
  }
}

// Card path note: SettingsPage deliberately does not listen to update-available (the version only
// lives in this page's state); the card is driven by the mount-time latest_release_version query —
// so the card cases below preset the version via __MOCK_TAURI_SET_LATEST_VERSION__ instead of
// emitting events. The badge is lit by the same mount-time query in App (the update-available event
// can be dropped before a listener registers), so presetting a non-null return value should make
// card and badge appear together.

async function checkOfflineFlow(browser) {
  const { context, page } = await newPage(browser, () => {
    window.__MOCK_TAURI_SET_LATEST_VERSION__("9.9.9");
  });
  try {
    await openSettings(page);
    const card = page.locator('.settings-update-card');
    assert.equal(await card.count(), 1, '设置页应出现更新卡片');
    const text = await card.textContent();
    assert.ok(text.includes('9.9.9'), '卡片应显示新版本号, got ' + text);
    assert.ok(text.includes('0.0.4'), '卡片应显示当前版本号, got ' + text);

    await card.getByRole('button', { name: '下载离线包' }).click();
    await page.waitForTimeout(600);

    const calls = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__);
    const download = calls.find((entry) => entry.command === 'download_update');
    assert.ok(download, '应调用 download_update');
    assert.equal(download.args.kind, 'offline', '离线包按钮应传 kind=offline');

    const restart = card.getByRole('button', { name: '重启以完成更新' });
    assert.equal(await restart.count(), 1, '收到 update-ready 后应显示重启按钮');
    await restart.click();
    await page.waitForTimeout(200);
    const restartCalls = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__);
    assert.ok(restartCalls.some((entry) => entry.command === 'restart_app'), '重启按钮应调用 restart_app');
    console.log('  offline flow: ok');
  } finally {
    await context.close();
  }
}

// Installer path: after downloading, the backend hands off to the NSIS installer and exits(0) — there
// is no terminal event, so even past the moment when the offline package would have reached ready,
// the UI must stay in the downloading state rather than the ready state.
async function checkInstallerFlow(browser) {
  const { context, page } = await newPage(browser, () => {
    window.__MOCK_TAURI_SET_LATEST_VERSION__("9.9.9");
  });
  try {
    await openSettings(page);
    await page.locator('.settings-update-card').getByRole('button', { name: '下载安装包' }).click();
    await page.waitForTimeout(600);
    const calls = await page.evaluate(() => window.__MOCK_TAURI_COMMAND_CALLS__);
    const download = calls.find((entry) => entry.command === 'download_update');
    assert.ok(download, '应调用 download_update');
    assert.equal(download.args.kind, 'installer', '安装包按钮应传 kind=installer');
    const card = page.locator('.settings-update-card');
    assert.equal(await card.getByRole('button', { name: '重启以完成更新' }).count(), 0, '安装包路径不应出现就绪态');
    assert.ok((await card.textContent()).includes('下载中'), '安装包下载中应停留在进度态');
    console.log('  installer flow: ok');
  } finally {
    await context.close();
  }
}

// Mount-query path: the update-available event can be dropped before a listener registers (the
// cold-start poll runs after 15 seconds), so both SettingsPage and App query latest_release_version
// on mount as a fallback (the latter drives the badge); the mock presets the return value via initScript.
async function checkCardFromMountQuery(browser) {
  const { context, page } = await newPage(browser, () => {
    // Preset the detected latest version 9.9.9 (> current 0.0.4 → hasUpdate true)
    window.__MOCK_TAURI_SET_LATEST_VERSION__("9.9.9");
  });
  try {
    await openSettings(page);
    const card = page.locator('.settings-update-card');
    assert.equal(await card.count(), 1, 'latest_release_version 返回新版本时挂载即应出现卡片');
    const text = await card.textContent();
    assert.ok(text.includes('9.9.9'), '卡片应显示挂载查询到的新版本号, got ' + text);
    assert.ok(text.includes('0.0.4'), '卡片应显示当前版本号, got ' + text);
    // I1 regression: App's mount query must light the badge — otherwise the badge is missing entirely whenever the event is lost.
    assert.equal(await page.locator('.sidebar-update-dot').count(), 1, '挂载查询应点亮角标');
    console.log('  mount query flow: ok');
  } finally {
    await context.close();
  }
}

// Failure path: after the mock switches to error mode, download_update dispatches update-download-error;
// the UI should show the error and restore both download buttons (downloadKind only clears the failed one).
async function checkDownloadError(browser) {
  const { context, page } = await newPage(browser, () => {
    window.__MOCK_TAURI_SET_LATEST_VERSION__("9.9.9");
    window.__MOCK_TAURI_SET_DOWNLOAD_MODE__("error");
  });
  try {
    await openSettings(page);
    const card = page.locator('.settings-update-card');
    await card.getByRole('button', { name: '下载离线包' }).click();
    await page.waitForTimeout(600);

    const text = await card.textContent();
    assert.ok(text.includes('更新失败：Mock download failed'), '应显示错误信息, got ' + text);
    assert.equal(await card.getByRole('button', { name: '下载安装包' }).count(), 1, '出错后下载安装包按钮应恢复');
    assert.equal(await card.getByRole('button', { name: '下载离线包' }).count(), 1, '出错后下载离线包按钮应恢复');
    assert.equal(await card.getByRole('button', { name: '重启以完成更新' }).count(), 0, '失败后不应进入就绪态');
    console.log('  download error flow: ok');
  } finally {
    await context.close();
  }
}

// I1 regression: unlisten must remove the handler from the mock registry — otherwise after page
// navigation a single emit would fire all historical handlers (real Tauri stops delivering after
// unlisten). Directly replicates the low-level IPC shape of @tauri-apps/api listen/unlisten:
//   listen   → invoke("plugin:event|listen", { event, target, handler })
//   unlisten → invoke("plugin:event|unlisten", { event, eventId })
async function checkUnlistenRemovesHandler(browser) {
  const { context, page } = await newPage(browser);
  try {
    await page.evaluate(() => {
      window.__UNLISTEN_CHECK__ = { count: 0, handler: 0 };
      window.__UNLISTEN_CHECK__.handler = window.__TAURI_INTERNALS__.transformCallback(function () {
        window.__UNLISTEN_CHECK__.count += 1;
      });
      void window.__TAURI_INTERNALS__.invoke("plugin:event|listen", {
        event: "mock-unlisten-probe",
        target: { kind: "Any" },
        handler: window.__UNLISTEN_CHECK__.handler,
      });
    });
    await page.evaluate(() => window.__MOCK_TAURI_EMIT__("mock-unlisten-probe", {}));
    await page.waitForTimeout(100);
    assert.equal(await page.evaluate(() => window.__UNLISTEN_CHECK__.count), 1, 'unlisten 前应恰好收到一次');

    await page.evaluate(() => {
      void window.__TAURI_INTERNALS__.invoke("plugin:event|unlisten", {
        event: "mock-unlisten-probe",
        eventId: window.__UNLISTEN_CHECK__.handler,
      });
    });
    await page.evaluate(() => window.__MOCK_TAURI_EMIT__("mock-unlisten-probe", {}));
    await page.waitForTimeout(100);
    assert.equal(await page.evaluate(() => window.__UNLISTEN_CHECK__.count), 1, 'unlisten 后不得再收到事件');
    console.log('  unlisten removes handler: ok');
  } finally {
    await context.close();
  }
}

// I3 regression: in reject mode download_update's invoke fails immediately and emits nothing; the UI
// must recover through SettingsPage.startDownload's catch branch: error text + both buttons clickable
// again. (3d58123's setDownloadKind guard cannot be tested at the browser layer for concurrency: when
// downloadKind is non-null both download buttons are unmounted, so a second startDownload cannot be
// triggered while the first download is in flight; the mock's downloadMode is also global and cannot
// be set to reject for only the second invoke. The guard logic is left to the Rust layer.)
async function checkDownloadInvokeReject(browser) {
  const { context, page } = await newPage(browser, () => {
    window.__MOCK_TAURI_SET_LATEST_VERSION__("9.9.9");
    window.__MOCK_TAURI_SET_DOWNLOAD_MODE__("reject");
  });
  try {
    await openSettings(page);
    const card = page.locator('.settings-update-card');
    await card.getByRole('button', { name: '下载离线包' }).click();
    await page.waitForTimeout(400);

    const text = await card.textContent();
    assert.ok(text.includes('更新失败：Mock download rejected'), 'invoke 立即失败后应显示错误文案, got ' + text);
    assert.equal(await card.getByRole('button', { name: '下载安装包' }).count(), 1, 'invoke 失败后下载安装包按钮应恢复');
    assert.equal(await card.getByRole('button', { name: '下载离线包' }).count(), 1, 'invoke 失败后下载离线包按钮应恢复');
    assert.equal(await card.getByRole('button', { name: '重启以完成更新' }).count(), 0, 'invoke 失败后不应进入就绪态');
    console.log('  download invoke reject flow: ok');
  } finally {
    await context.close();
  }
}

// The manual "check for updates" button: covers three outcomes — check failed (Err → "检查失败"),
// confirmed no update (Ok(null) → "未发现新版本"), new version found (card + badge lit). The mock
// value can be changed dynamically after page load; the four clicks cover every state transition.
async function checkManualCheck(browser) {
  const { context, page } = await newPage(browser);
  try {
    await openSettings(page);
    assert.equal(await page.locator('.settings-update-card').count(), 0, '初始无更新时不应有卡片');

    const checkButton = page.getByRole('button', { name: '检查更新' });
    const versionHint = page.locator('.settings-actions .settings-hint').filter({ hasText: '当前版本' });
    assert.equal(await versionHint.count(), 1, '软件更新组应显示当前版本号');
    assert.ok((await versionHint.textContent()).includes('0.0.4'), '当前版本应为 0.0.4, got ' + await versionHint.textContent());

    // 1) Check failed (backend Err): must say "检查失败", never lie with "未发现新版本"
    await page.evaluate(() => window.__MOCK_TAURI_SET_LATEST_VERSION__("__error__"));
    await checkButton.click();
    await page.waitForTimeout(200);
    const failedHint = page.locator('.settings-update-error').filter({ hasText: '检查失败' });
    assert.equal(await failedHint.count(), 1, '检查失败应显示"检查失败"提示');
    assert.equal(await page.locator('.settings-update-card').count(), 0, '检查失败不应出卡片');

    // 2) Detected version equal to current: show the detected version directly (matches the agent2api wording)
    await page.evaluate(() => window.__MOCK_TAURI_SET_LATEST_VERSION__("0.0.4"));
    await checkButton.click();
    await page.waitForTimeout(200);
    const hint = page.locator('.settings-actions .settings-hint').filter({ hasText: '已是最新版本' });
    assert.equal(await hint.count(), 1, '无更新时应显示"已是最新版本（x.y.z）"提示');
    assert.ok((await hint.textContent()).includes('0.0.4'), '提示应包含检测到的版本号');
    assert.equal(await failedHint.count(), 0, '失败提示应被新结果替换');

    // 3) Repo has no release: fall back to "未发现新版本"
    await page.evaluate(() => window.__MOCK_TAURI_SET_LATEST_VERSION__(null));
    await checkButton.click();
    await page.waitForTimeout(200);
    assert.equal(await hint.count(), 0, '无 release 时不应显示版本号提示');
    const noReleaseHint = page.locator('.settings-actions .settings-hint').filter({ hasText: '未发现新版本' });
    assert.equal(await noReleaseHint.count(), 1, '仓库无 release 时应显示"未发现新版本"');

    // 4) New version found: card appears + badge lit (manual and automatic chains share the same visibility), hint gone
    await page.evaluate(() => window.__MOCK_TAURI_SET_LATEST_VERSION__("9.9.9"));
    await checkButton.click();
    await page.waitForTimeout(200);
    const card = page.locator('.settings-update-card');
    assert.equal(await card.count(), 1, '手动检查发现新版本后应出现卡片');
    assert.ok((await card.textContent()).includes('9.9.9'), '卡片应显示新版本号');
    assert.equal(await page.locator('.sidebar-update-dot').count(), 1, '手动检查发现新版本应点亮角标');
    assert.equal(await hint.count(), 0, '发现新版本后"已是最新版本"提示应消失');
    assert.equal(await noReleaseHint.count(), 0, '发现新版本后"未发现新版本"提示应消失');

    // 5) Check failed while the card is showing: show "检查失败" without clearing the card — silence was once read as "nothing happened" on a real machine
    await page.evaluate(() => window.__MOCK_TAURI_SET_LATEST_VERSION__("__error__"));
    await checkButton.click();
    await page.waitForTimeout(200);
    assert.equal(await page.locator('.settings-update-card').count(), 1, '检查失败不得清掉已有卡片');
    assert.equal(await failedHint.count(), 1, '卡片已显示时检查失败也要明说');
    console.log('  manual check flow: ok');
  } finally {
    await context.close();
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    await checkBadge(browser);
    await checkOfflineFlow(browser);
    await checkInstallerFlow(browser);
    await checkCardFromMountQuery(browser);
    await checkDownloadError(browser);
    await checkUnlistenRemovesHandler(browser);
    await checkDownloadInvokeReject(browser);
    await checkManualCheck(browser);
    console.log('Update check tests passed.');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error('Test failed:', error);
  process.exit(1);
});
