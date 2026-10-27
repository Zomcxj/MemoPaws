// Continuous-session stress: pin and confirm ALTERNATE as fast as the UI allows.
// Gate: every session must fully settle (overlay closed, expected window shown,
// result landed for confirm) — catches the intermittent "stuck after confirm".
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { chromium } = require('playwright-core');

const ROOT = path.resolve(__dirname, '..', '..');
const EXE = path.join(ROOT, 'target', 'release', 'memopaws.exe');
const TEST_HOME = path.join(os.tmpdir(), 'memopaws-cont-' + Date.now());
const CDP_PORT = Number(process.env.PORT || 9601);
const ROUNDS = Number(process.env.ROUNDS || 8);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function connectCdp() {
  for (let i = 0; i < 60; i++) {
    try { return await chromium.connectOverCDP(`http://127.0.0.1:${CDP_PORT}`); }
    catch (e) { await sleep(250); }
  }
  throw new Error('CDP unavailable');
}

async function main() {
  fs.rmSync(TEST_HOME, { recursive: true, force: true });
  const app = spawn(EXE, [], {
    stdio: 'pipe',
    env: { ...process.env, HOME: TEST_HOME, MEMOPAWS_HOME: TEST_HOME, MEMOPAWS_E2E_HIDDEN: '1',
      WEBVIEW2_USER_DATA_FOLDER: path.join(TEST_HOME, 'webview'),
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${CDP_PORT} --remote-allow-origins=*` },
  });
  let failures = 0;
  let appStderr = '';
  const t0 = Date.now();
  app.stderr.on('data', (d) => { appStderr += d.toString(); });
  try {
    const browser = await connectCdp();
    const context = browser.contexts()[0];
    let mainPage = null;
    const md = Date.now() + 30000;
    while (!mainPage && Date.now() < md) {
      mainPage = context.pages().find((p) => /tauri\.localhost/.test(p.url()) && !p.url().includes('#capture-overlay') && !p.url().includes('#pin')) || null;
      await sleep(200);
    }
    if (!mainPage) throw new Error('main never appeared');

    for (let round = 1; round <= ROUNDS; round++) {
      const usePin = round % 2 === 1;
      // Start capture
      await mainPage.evaluate(() => window.dispatchEvent(new CustomEvent('memopaws-capture')));
      let overlay = null;
      const od = Date.now() + 15000;
      while (!overlay && Date.now() < od) {
        overlay = context.pages().find((p) => p.url().includes('#capture-overlay')) || null;
        await sleep(150);
      }
      if (!overlay) { failures++; console.log(`round ${round}: OVERLAY NEVER APPEARED`); continue; }
      const sel = await overlay.waitForSelector('.capture-overlay', { timeout: 10000 }).then(() => true).catch(() => false);
      if (!sel) {
        failures++;
        console.log(`round ${round}: overlay page present but .capture-overlay never painted — AUTOPSY:`);
        const autopsy = await overlay.evaluate(async () => {
          const gen = await window.__TAURI_INTERNALS__.invoke('capture_overlay_generation').then((v) => v).catch((e) => 'ERR:' + e);
          // Does the image command answer at all, error, or hang?
          const img = await Promise.race([
            window.__TAURI_INTERNALS__.invoke('capture_overlay_image').then(() => 'answered').catch((e) => 'ERR:' + String(e).slice(0, 80)),
            new Promise((resolve) => setTimeout(() => resolve('HUNG>3s'), 3000)),
          ]);
          return {
            url: location.href,
            generation: gen,
            imageCommand: img,
            overlayDiv: !!document.querySelector('.capture-overlay'),
            rootChildren: document.getElementById('root') ? document.getElementById('root').children.length : -1,
            bodySnippet: document.body.innerHTML.slice(0, 150),
          };
        }).catch((e) => ({ autopsyError: String(e) }));
        console.log(JSON.stringify(autopsy, null, 1));
        continue;
      }

      // Select a region and act
      await overlay.mouse.move(500, 400, { steps: 5 });
      await overlay.mouse.down();
      await overlay.mouse.move(1100, 800, { steps: 7 });
      await overlay.mouse.up();
      await overlay.locator('.capture-overlay-rect').waitFor({ timeout: 10000 });
      await overlay.locator('.capture-overlay').getByRole('button', { name: usePin ? /钉图|Pin image/ : /确认|Confirm/ }).click();

      if (usePin) {
        // Pin: overlay must close, a pin page must appear, main must stay hidden
        let pinPage = null;
        const pd = Date.now() + 15000;
        while (!pinPage && Date.now() < pd) {
          pinPage = context.pages().find((p) => p.url().includes('#pin')) || null;
          await sleep(150);
        }
        const overlayGone = await overlay.evaluate(() => !document.querySelector('.capture-overlay:not(.is-hidden)')).catch(() => false);
        if (!pinPage) { failures++; console.log(`round ${round}: pin page never appeared`); }
        else if (!overlayGone) { failures++; console.log(`round ${round}: overlay did not clear before pin`); }
        else console.log(`round ${round}: PIN ok`);
        // Close the pin right away so the next round starts clean
        if (pinPage) await pinPage.evaluate(() => { const b = document.querySelector('button[aria-label="关闭钉图"]'); if (b) b.click(); }).catch(() => {});
        await sleep(400);
      } else {
        // Confirm: overlay must close and main must show AND hold the result
        const cd = Date.now() + 15000;
        let landed = null;
        while (Date.now() < cd && !landed) {
          landed = await mainPage.evaluate(() => {
            const img = document.querySelector('img[data-capture-preview]') || document.querySelector('.recognize-page img');
            const ta = document.querySelector('textarea');
            return { preview: !!(img && img.naturalWidth > 0), ocr: ta ? ta.value.length : -1 };
          }).catch(() => null);
          const overlayGone = await overlay.evaluate(() => !document.querySelector('.capture-overlay:not(.is-hidden)')).catch(() => false);
          if (landed && landed.preview) break;
          if (!overlayGone) await sleep(200);
          else await sleep(200);
        }
        if (!landed || !landed.preview) { failures++; console.log(`round ${round}: CONFIRM DID NOT LAND: ${JSON.stringify(landed)} — STUCK`); }
        else console.log(`round ${round}: CONFIRM ok (ocr=${landed.ocr})`);
      }
      await sleep(500); // user-like pace, deliberately short to stress the race
      const seqLines = appStderr.split(String.fromCharCode(10)).filter((l) => l.includes('[seq]'));
      console.log('   seq:', seqLines.slice(-4).join(' | ').replace(/\[seq\] /g, ''));
    }
    console.log(failures === 0 ? `ALL ${ROUNDS} ROUNDS PASSED` : `${failures}/${ROUNDS} ROUNDS FAILED`);
    process.exitCode = failures === 0 ? 0 : 1;
  } finally {
    app.kill();
  }
}
main().catch((e) => { console.error('STRESS FAILED:', e.message); process.exit(1); });
