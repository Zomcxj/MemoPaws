// Playwright E2E: 更新通知全链路——角标 → 卡片（事件/挂载两条路径）→ 下载（离线/安装/失败）→ 重启。
// Usage: 保持 `npm --prefix frontend run dev` 运行，然后
//   node frontend/e2e/test-update-check.cjs

const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE_URL = 'http://localhost:1420';
const MOCK_SCRIPT = fs.readFileSync(path.join(__dirname, 'mock-tauri.js'), 'utf-8');

// initScript 在 mock 加载后、页面脚本前执行，用于预置 latest_release_version / 下载模式
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

// 卡片路径说明：SettingsPage 刻意不监听 update-available（版本只存本页 state），
// 卡片由挂载时的 latest_release_version 查询驱动——所以下面的卡片用例都通过
// __MOCK_TAURI_SET_LATEST_VERSION__ 预置版本，而不是 emit 事件。角标同样由
// App 挂载时的 latest_release_version 查询点亮（update-available 事件可能在
// 监听器注册前被后端丢弃），所以预置非 null 返回值时卡片与角标应同时出现。

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

// 安装包路径：后端下载完交给 NSIS 安装器并 exit(0)，没有终态事件——
// 即使等过离线包 ready 本会到达的时刻，UI 也必须停留在下载态而不是就绪态
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

// 挂载查询路径：update-available 事件可能在监听器注册前被后端丢弃（冷启动 15 秒轮询），
// 设置页与 App 挂载时都主动调 latest_release_version 兜底（后者驱动角标），
// mock 里通过 initScript 预置返回值
async function checkCardFromMountQuery(browser) {
  const { context, page } = await newPage(browser, () => {
    window.__MOCK_TAURI_SET_LATEST_VERSION__("0.0.4");
  });
  try {
    await openSettings(page);
    const card = page.locator('.settings-update-card');
    assert.equal(await card.count(), 1, 'latest_release_version 返回新版本时挂载即应出现卡片');
    const text = await card.textContent();
    assert.ok(text.includes('0.0.4'), '卡片应显示挂载查询到的新版本号, got ' + text);
    assert.ok(text.includes('0.0.4'), '卡片应显示当前版本号, got ' + text);
    // I1 回归：App 挂载查询必须点亮角标——否则事件丢失时角标整场缺失
    assert.equal(await page.locator('.sidebar-update-dot').count(), 1, '挂载查询应点亮角标');
    console.log('  mount query flow: ok');
  } finally {
    await context.close();
  }
}

// 失败路径：mock 切到 error 模式后 download_update 派发 update-download-error，
// UI 应显示错误并恢复两个下载按钮（downloadKind 只清掉失败的那个）
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

// I1 回归：unlisten 必须把 handler 从 mock 注册表移除——否则页面导航往返后
// 一次 emit 会触发所有历史 handler（真实 Tauri 在 unlisten 后不再投递）。
// 直接复刻 @tauri-apps/api listen/unlisten 的底层 IPC 形状：
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

// I3 回归：reject 模式下 download_update 的 invoke 立即失败且不发任何事件，
// UI 必须靠 SettingsPage.startDownload 的 catch 分支恢复：错误文案 + 两个按钮可再点。
// （3d58123 的 setDownloadKind 守卫在浏览器层测不了并发场景：downloadKind 非 null 时
// 两个下载按钮已卸载，无法在第一个下载进行中触发第二次 startDownload；mock 的
// downloadMode 又是全局的，无法只对第二次 invoke 设为 reject。守卫逻辑留给 Rust 层。）
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

// 手动"检查更新"按钮：覆盖三种结局——检查失败（Err → "检查失败"）、确认无更新
//（Ok(null) → "未发现新版本"）、发现新版本（卡片 + 角标点亮）。mock 值可在页面
// 加载后动态改，四段点击覆盖全部状态迁移。
async function checkManualCheck(browser) {
  const { context, page } = await newPage(browser);
  try {
    await openSettings(page);
    assert.equal(await page.locator('.settings-update-card').count(), 0, '初始无更新时不应有卡片');

    const checkButton = page.getByRole('button', { name: '检查更新' });
    const versionHint = page.locator('.settings-actions .settings-hint').filter({ hasText: '当前版本' });
    assert.equal(await versionHint.count(), 1, '软件更新组应显示当前版本号');
    assert.ok((await versionHint.textContent()).includes('0.0.4'), '当前版本应为 0.0.4, got ' + await versionHint.textContent());

    // 1) 检查失败（后端 Err）：必须说"检查失败"，不能谎报"未发现新版本"
    await page.evaluate(() => window.__MOCK_TAURI_SET_LATEST_VERSION__("__error__"));
    await checkButton.click();
    await page.waitForTimeout(200);
    const failedHint = page.locator('.settings-update-error').filter({ hasText: '检查失败' });
    assert.equal(await failedHint.count(), 1, '检查失败应显示"检查失败"提示');
    assert.equal(await page.locator('.settings-update-card').count(), 0, '检查失败不应出卡片');

    // 2) 确认无更新：显示"未发现新版本"
    await page.evaluate(() => window.__MOCK_TAURI_SET_LATEST_VERSION__(null));
    await checkButton.click();
    await page.waitForTimeout(200);
    const hint = page.locator('.settings-actions .settings-hint').filter({ hasText: '未发现新版本' });
    assert.equal(await hint.count(), 1, '无更新时应显示"未发现新版本"提示');
    assert.equal(await failedHint.count(), 0, '失败提示应被新结果替换');

    // 3) 发现新版本：卡片出现 + 角标点亮（手动链路与自动链路可见性一致），提示消失
    await page.evaluate(() => window.__MOCK_TAURI_SET_LATEST_VERSION__("9.9.9"));
    await checkButton.click();
    await page.waitForTimeout(200);
    const card = page.locator('.settings-update-card');
    assert.equal(await card.count(), 1, '手动检查发现新版本后应出现卡片');
    assert.ok((await card.textContent()).includes('9.9.9'), '卡片应显示新版本号');
    assert.equal(await page.locator('.sidebar-update-dot').count(), 1, '手动检查发现新版本应点亮角标');
    assert.equal(await hint.count(), 0, '发现新版本后"未发现新版本"提示应消失');

    // 4) 卡片已显示时检查失败：保持安静（不再与卡片矛盾，真机实测踩过）
    await page.evaluate(() => window.__MOCK_TAURI_SET_LATEST_VERSION__("__error__"));
    await checkButton.click();
    await page.waitForTimeout(200);
    assert.equal(await page.locator('.settings-update-card').count(), 1, '检查失败不得清掉已有卡片');
    assert.equal(await failedHint.count(), 0, '卡片已显示时检查失败应保持安静');
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
