// Mock Tauri API for Playwright E2E testing
// This script is injected via addInitScript before any page scripts run

(function() {
  const MOCK_THEME_KEY = "memopaws-mock-backend-theme";
  const storedTheme = sessionStorage.getItem(MOCK_THEME_KEY);
  let backendTheme = storedTheme === "light" || storedTheme === "dark" || storedTheme === "auto" ? storedTheme : "dark";
  const themeCalls = [];
  const commandCalls = [];
  const windowCalls = [];
  const runtimeUpdates = [];
  let apiTestMode = "success-vision";
  let fullscreen = false;
  let visible = true;
  // Controlled failure modes: pin rejection (retention assertions) / delayed AI OCR results (token invalidation)
  let pinRejectMode = false;
  let aiOcrDelay = 0;
  // Offline OCR controlled modes: success (default) / error (recognition failed) / empty (empty text)
  // / nolangs (no installed language capability) / langerror (language query failed).
  // Persisted via sessionStorage so modes survive a reload (the no-languages scenario reloads the page).
  const LOCAL_OCR_MODE_KEY = "memopaws-mock-local-ocr";
  const clampLocalOcrMode = (mode) => (["error", "empty"].includes(mode) ? mode : "success");
  const clampLanguagesMode = (mode) => (["error", "nolangs"].includes(mode) ? mode : "success");
  let localOcrMode = clampLocalOcrMode(sessionStorage.getItem(LOCAL_OCR_MODE_KEY + ":ocr") || "success");
  let localOcrLanguagesMode = clampLanguagesMode(sessionStorage.getItem(LOCAL_OCR_MODE_KEY + ":langs") || "success");
  // Event stubs: eventHandlers records the handler id registered per event name (the return value of
  // plugin:event|listen), eventCallbacks maps transformCallback-assigned ids to callbacks; emit looks
  // callbacks up by id.
  const eventHandlers = {};
  const eventCallbacks = {};
  // Injectable return value for latest_release_version: null means no update (silent on the mount-query path)
  let latestReleaseVersion = null;
  // Outcome mode for download_update: success (offline package → ready) / error (→ update-download-error)
  // / reject (invoke rejects immediately and emits nothing, mirroring the backend's instant failure when the download mutex is taken)
  let downloadMode = "success";

  // Pin-session state machine: the same rules as Rust `pinned_images::Pins` (visibility before the
  // first pin, session mutex, the three finish outcomes cancel/confirm/pin, restore only when the last pin dies).
  const pinSession = { next: 0, images: new Map(), captureVisible: null, restoreVisible: null };
  function sessionBegin(visible) {
    if (pinSession.captureVisible !== null) throw new Error("capture is already active");
    pinSession.captureVisible = Boolean(visible);
  }
  function sessionInsert() {
    pinSession.next += 1;
    const label = "pin-" + pinSession.next;
    if (pinSession.restoreVisible === null) {
      pinSession.restoreVisible = pinSession.captureVisible === null ? false : pinSession.captureVisible;
    }
    pinSession.images.set(label, {});
    return label;
  }
  function sessionRemove(label) {
    if (!pinSession.images.delete(label)) return null;
    if (pinSession.images.size === 0 && pinSession.captureVisible === null) {
      const restore = pinSession.restoreVisible;
      pinSession.restoreVisible = null;
      return restore;
    }
    return null;
  }
  function sessionFinish(outcome) {
    if (!["pin", "confirm", "cancel"].includes(outcome)) throw new Error("invalid capture outcome");
    if (pinSession.captureVisible === null) throw new Error("capture is not active");
    const before = pinSession.captureVisible;
    pinSession.captureVisible = null;
    const pending = pinSession.images.size === 0 ? pinSession.restoreVisible : null;
    if (pinSession.images.size === 0) pinSession.restoreVisible = null;
    if (outcome === "confirm") return true;
    if (outcome === "pin" && pinSession.images.size > 0) return false;
    if (outcome === "cancel" && pinSession.images.size > 0) return before;
    return pending !== null ? pending : true;
  }
  const MOCK_DATA = {
    key_list: [
      { id: 1, name: "Test LLM Key", type: "llm", url: "https://api.openai.com/v1", url_anthropic: "", note: "Test key", order: 0, created: "1700000000" },
      { id: 2, name: "Another Key", type: "llm", url: "https://api.anthropic.com", url_anthropic: "", note: "", order: 1, created: "1700000001" }
    ],
    // Two LLM keys so reordering has somewhere to move, plus the internal
    // settings key, which KeysPage must hide from the list.
    list: [
      { id: 1, name: "Test LLM Key", type: "llm", url: "https://api.openai.com/v1", url_anthropic: "", note: "Test key", order: 0, created: "1700000000" },
      { id: 2, name: "Second LLM Key", type: "llm", url: "https://api.anthropic.com", url_anthropic: "", note: "", order: 1, created: "1700000001" },
      { id: 3, name: "settings_api_key", type: "llm", url: "https://api.openai.com/v1", url_anthropic: "", note: "", order: 2, created: "1700000002" }
    ],
    memo_list: [
      { id: 1, title: "Test Memo", content: "# Hello World\n\nThis is a test memo.", tags: ["test"], created: "2024-01-01T00:00:00Z", updated: "2024-01-01T00:00:00Z" },
      { id: 2, title: "Second Memo", content: "Another memo.", tags: [], created: "2024-01-02T00:00:00Z", updated: "2024-01-02T00:00:00Z" }
    ],
    history_list: [
      { time: "1700000000", type: "ocr", text: "Recognized text", ocr_text: "Recognized text", translate_text: null },
      { time: "1700000001", type: "translate", text: "Translated", ocr_text: "Original", translate_text: "Translated" }
    ],
    list_displays: [
      { index: 0, name: "Primary", x: 0, y: 0, width: 1280, height: 720, is_primary: true },
      { index: 1, name: "Secondary", x: 1280, y: 0, width: 1600, height: 900, is_primary: false }
    ],
    clipboard_list: [
      // Multi-line on purpose: the list summary must show only the first line.
      { id: 1, time: "1700000000", content_type: "text", text: "Clipboard text\nSECOND LINE MUST NOT SHOW", image_path: null },
      // Long name on purpose: the list summary must show only the ellipsized filename.
      { id: 2, time: "1700000001", content_type: "image", text: null, image_path: "C:\\some\\deep\\folder\\a-very-long-clipboard-image-filename-that-must-be-ellipsized.png" }
    ],
       get_config: {
        language: "zh", close_behavior: "tray",
       has_api_key: true,
       clipboard_max_items: 50, history_max_items: 100,
       shortcuts: { capture: "Alt+X", canvas_fit: "Ctrl+F", new_memo: "Ctrl+N", global_search: "Ctrl+Shift+F" }
    },
    status: { has_master: true, unlocked: true, load_failed: false, version: 3 },
    // Mirrors the real renderer's fenced-code markup (crates/memo/src/renderer.rs):
    // a copy button carrying only a data marker, never an inline onclick.
    memo_render: "<h1>Hello World</h1><p>This is a test memo.</p>"
      + "<div class=\"memo-code-block\"><div class=\"memo-code-toolbar\">"
      + "<span class=\"memo-code-language\">rust</span>"
      + "<button type=\"button\" class=\"memo-code-copy\" data-memo-code-copy aria-label=\"Copy code\">Copy</button>"
      + "</div><pre class=\"memo-code\"><code>fn main() {}</code></pre></div>",
    memo_search: [],
    memo_get: { id: 1, title: "Test Memo", content: "# Hello World\n\nThis is a test memo.", tags: ["test"], created: "2024-01-01T00:00:00Z", updated: "2024-01-01T00:00:00Z" },
    capture_list: [],
    get_value: "test-api-key-12345"
  };

   // One-shot opaque PNG (128×96) so image_crop and friends can return real decodable bytes.
   let opaquePngCache = null;
   function opaquePngBytes() {
     if (!opaquePngCache) {
       const canvas = document.createElement("canvas");
       canvas.width = 128;
       canvas.height = 96;
       const ctx = canvas.getContext("2d");
       ctx.fillStyle = "rgb(18,52,86)";
       ctx.fillRect(0, 0, canvas.width, canvas.height);
       const binary = atob(canvas.toDataURL("image/png").split(",")[1]);
       const bytes = new Uint8Array(binary.length);
       for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
       opaquePngCache = Array.from(bytes);
     }
     return opaquePngCache;
   }

   // capture_screen's target contract is tauri::ipc::Response: invoke directly receives the full-screen
   // PNG as an ArrayBuffer and the frontend creates its own objectURL and decodes once. 1280×720 fully
   // opaque, pixels encode coordinates as rgb(x%256, y%256, 64) so tests verify the crop is the
   // selection, not the whole screen.
   let capturePngCache = null;
   function capturePngBuffer() {
     if (!capturePngCache) {
       const canvas = document.createElement("canvas");
       canvas.width = 1280;
       canvas.height = 720;
       const ctx = canvas.getContext("2d");
       const frame = ctx.createImageData(1280, 720);
       const data = frame.data;
       for (let y = 0; y < 720; y++) {
         for (let x = 0; x < 1280; x++) {
           const i = (y * 1280 + x) * 4;
           data[i] = x % 256;
           data[i + 1] = y % 256;
           data[i + 2] = 64;
           data[i + 3] = 255;
         }
       }
       ctx.putImageData(frame, 0, 0);
       const binary = atob(canvas.toDataURL("image/png").split(",")[1]);
       const bytes = new Uint8Array(binary.length);
       for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
       capturePngCache = bytes.buffer;
     }
     return capturePngCache;
   }

   function mockInvoke(command, args) {
     commandCalls.push({ command: command, args: args || null, visible: visible });
     return new Promise(function(resolve, reject) {
      setTimeout(function() {
        if (command === "get_theme") {
          resolve(backendTheme);
        } else if (command === "set_theme") {
          const nextTheme = args && args.theme;
          themeCalls.push(nextTheme);
          if (nextTheme === "light" || nextTheme === "dark" || nextTheme === "auto") {
            backendTheme = nextTheme;
            sessionStorage.setItem(MOCK_THEME_KEY, backendTheme);
          }
           resolve();
        } else if (command === "set_language") {
          const nextLanguage = args && args.language === "en" ? "en" : "zh";
          MOCK_DATA.get_config.language = nextLanguage;
          // The real backend persists the language into config: the mock mirrors it via sessionStorage across reloads.
          sessionStorage.setItem("memopaws-mock-language", nextLanguage);
          resolve();
        } else if (command === "get_config") {
          const persistedLanguage = sessionStorage.getItem("memopaws-mock-language");
          resolve(Object.assign({}, MOCK_DATA.get_config, { theme: backendTheme }, persistedLanguage ? { language: persistedLanguage } : {}));
        } else if (command === "test_api_connection") {
          if (apiTestMode === "timeout") return setTimeout(function() { resolve({ error: "timeout", elapsed_ms: 10000 }); }, 120);
          if (apiTestMode === "connect") return resolve({ error: "connect", elapsed_ms: 32 });
          if (apiTestMode === "401") return resolve({ status_code: 401, elapsed_ms: 41, text: "SECRET RESPONSE MUST NOT SHOW" });
          if (apiTestMode === "404") return resolve({ status_code: 404, elapsed_ms: 42, text: "PRIVATE BODY MUST NOT SHOW" });
          if (apiTestMode === "generic") return resolve({ status_code: 500, elapsed_ms: 43, text: "PRIVATE BODY MUST NOT SHOW" });
          return resolve({ status_code: 200, elapsed_ms: 44, vision_result: { success: true, text: "OCR test" } });
        } else if (command === "set_clipboard_max_items" || command === "set_history_max_items") {
          runtimeUpdates.push({ command: command, value: args && (args.value ?? args.max_items) }); resolve();
        } else if (command === "set_close_behavior") {
          runtimeUpdates.push({ command: command, value: args && (args.value ?? args.visible) }); resolve();
        } else if (command === "get_storage_dir_conflict") {
          resolve(Boolean(args && args.path && String(args.path).includes("conflict")));
        } else if (command === "migrate_data_dir") {
          runtimeUpdates.push({ command: command, mode: args && args.mode }); resolve({ migrated: true, restart_required: true });
        } else if (command === "memo_render") {
          // Echo the requested theme so tests can observe which theme rendered.
          resolve("<p class=\"memo-render-theme\">" + String(args && args.theme) + "</p>" + MOCK_DATA.memo_render);
        } else if (command in MOCK_DATA) {
          resolve(MOCK_DATA[command]);
        } else if (command === "memo_create") {
          resolve({ id: 99, title: (args && args.memo && args.memo.title) || "New", content: (args && args.memo && args.memo.content) || "", tags: [], created: new Date().toISOString(), updated: new Date().toISOString() });
        } else if (command === "memo_update") {
          resolve((args && args.memo) || { id: 1, title: "Updated", content: "", tags: [], created: "", updated: "" });
        } else if (command === "memo_delete" || command === "delete" || command === "lock" || command === "set_master" || command === "remove_master" || command === "save_config" || command === "history_delete" || command === "history_clear" || command === "clipboard_delete" || command === "clipboard_clear" || command === "capture_delete") {
          resolve();
        } else if (command === "add" || command === "update") {
          resolve({ id: 99, name: (args && args.entry && args.entry.name) || "New Key", type: (args && args.entry && args.entry.type) || "llm", url: (args && args.entry && args.entry.url) || "", url_anthropic: "", note: "", order: 0, created: String(Date.now()) });
        } else if (command === "unlock") {
          resolve(true);
        } else if (command === "capture_screen") {
          // Raw binary: invoke's return value IS the ArrayBuffer, no { image, preview } wrapper.
          resolve(capturePngBuffer());
        } else if (command === "pin_image") {
          // Mirrors the new backend: returns a unique pin-N label and registers it in the session state.
          // pinRejectMode: invoke fails immediately, for overlay-error and mark-retention assertions.
          if (pinRejectMode) { reject(new Error("Mock pin rejected")); return; }
          try { resolve(sessionInsert()); } catch (error) { reject(error); }
        } else if (command === "pin_close") {
          // The real backend restores the main window via the destroy hook; in the browser, closing goes through __MOCK_TAURI_CLOSE_PIN__.
          resolve(null);
        } else if (command === "capture_session_begin") {
          try { sessionBegin(args && args.visible); resolve(null); } catch (error) { reject(error); }
        } else if (command === "capture_session_finish") {
          try { resolve(sessionFinish((args && args.outcome) || "cancel")); } catch (error) { reject(error); }
        } else if (command === "capture_settle_fullscreen_exit") {
          // Mocks the native offscreen settle; in the browser there is no window geometry to move.
          resolve(true);
        } else if (command === "pin_show") {
          resolve(null);
        } else if (command === "image_crop") {
          // The frontend must crop on a local canvas; this branch only exists so implementations that
          // wrongly call IPC get caught by the image_crop count assertion instead of failing at decode.
          resolve({ image: opaquePngBytes() });
        } else if (command === "ai_ocr") {
          // aiOcrDelay > 0: delayed fill, verifies the operation token invalidates stale results after marks/selection change.
          if (aiOcrDelay > 0) { setTimeout(function() { resolve({ text: "Mock OCR text" }); }, aiOcrDelay); return; }
          resolve({ text: "Mock OCR text" });
        } else if (command === "local_ocr_languages") {
          if (localOcrLanguagesMode === "error") { reject(new Error("Mock language query failed")); return; }
          if (localOcrLanguagesMode === "nolangs") { resolve({ languages: [], preferred: "" }); return; }
          resolve({ languages: [{ tag: "en-US", name: "English" }, { tag: "zh-Hans-CN", name: "中文" }], preferred: "zh-Hans-CN" });
        } else if (command === "local_ocr") {
          if (localOcrMode === "error") { reject(new Error("Mock offline OCR failed")); return; }
          if (localOcrMode === "empty") { resolve({ text: "" }); return; }
          resolve({ text: "Local OCR example text" });
        } else if (command === "ai_translate") {
          resolve({ text: "Mock translation" });
        } else if (command === "latest_release_version") {
          // The "__error__" sentinel mirrors the real backend's Err: the check itself failed (network/rate limit), invoke rejects.
          // The return shape matches the backend's UpdateCheck: null = repo has no release; "0.0.4" equal to the
          // current version → hasUpdate false; a higher version → hasUpdate true.
          if (latestReleaseVersion === "__error__") {
            reject(new Error("Mock release check failed"));
            return;
          }
          if (latestReleaseVersion === null) {
            resolve({ latestVersion: null, currentVersion: "0.0.4", hasUpdate: false });
          } else {
            resolve({ latestVersion: latestReleaseVersion, currentVersion: "0.0.4", hasUpdate: latestReleaseVersion !== "0.0.4" });
          }
        } else if (command === "download_update") {
          // reject mode: invoke fails immediately and emits nothing — the UI must recover via invoke's
          // catch branch (SettingsPage startDownload), covering the guard path from 3d58123.
          if (downloadMode === "reject") {
            reject(new Error("Mock download rejected"));
            return;
          }
          // Mirrors the real backend: the command resolves immediately, progress and terminal states are
          // dispatched asynchronously via events. The installer path hands off to the NSIS installer and
          // exits(0) with no terminal event; error mode skips ready so tests can drive the failure path.
          const kind = args && args.kind;
          const total = 2097152;
          setTimeout(function () { window.__MOCK_TAURI_EMIT__("update-download-progress", { received: Math.floor(total / 2), total: total }); }, 30);
          setTimeout(function () { window.__MOCK_TAURI_EMIT__("update-download-progress", { received: total, total: total }); }, 80);
          if (downloadMode === "error") {
            setTimeout(function () { window.__MOCK_TAURI_EMIT__("update-download-error", { message: "Mock download failed" }); }, 150);
          } else if (kind === "offline") {
            setTimeout(function () { window.__MOCK_TAURI_EMIT__("update-ready", {}); }, 200);
          }
          resolve();
        } else if (command === "clipboard_get_image" || command === "capture_get_image") {
          resolve([137, 80, 78, 71]);
        } else {
          console.warn("[Mock] Unknown command: " + command);
          resolve(null);
        }
      }, 10);
    });
  }

  // Tauri 2 uses __TAURI_INTERNALS__ not __TAURI__
  // invoke goes through the wrapper below (plugin:* routing + fallback to mockInvoke)
  window.__TAURI_INTERNALS__ = {
    metadata: { currentWindow: { label: "main" }, currentWebview: { label: "main" } },
    callbacks: {},
     invoke: function(command, payload) {
       if (command === "plugin:window|outer_position") return Promise.resolve({ x: 0, y: 0 });
       if (command === "plugin:window|outer_size") return Promise.resolve({ width: 1280, height: 720 });
       if (command === "plugin:window|inner_size") { windowCalls.push({ command: command }); return Promise.resolve({ width: 800, height: 600 }); }
       if (command === "plugin:window|scale_factor") return Promise.resolve(1);
       if (command === "plugin:window|current_monitor") {
         return Promise.resolve({ name: "Primary", position: { x: 0, y: 0 }, size: { width: 1280, height: 720 }, scaleFactor: 1, workArea: { position: { x: 0, y: 0 }, size: { width: 1280, height: 720 } } });
       }
       if (command === "plugin:window|start_dragging") { windowCalls.push({ command: command }); return Promise.resolve(); }
        if (command === "plugin:window|is_fullscreen") { windowCalls.push({ command: command }); return Promise.resolve(fullscreen); }
        if (command === "plugin:window|is_visible") { windowCalls.push({ command: command }); return Promise.resolve(visible); }
        if (command === "plugin:window|set_fullscreen") { windowCalls.push({ command: command, value: payload && payload.value }); fullscreen = Boolean(payload && payload.value); return Promise.resolve(); }
        if (command === "plugin:window|hide") { windowCalls.push({ command: command }); visible = false; return Promise.resolve(); }
        // @tauri-apps/api/event's listen/unlisten come through here; handler is the transformCallback-returned id
        if (command === "plugin:event|listen") {
          const name = payload && payload.event;
          const handler = payload && payload.handler;
          (eventHandlers[name] = eventHandlers[name] || []).push(handler);
          return Promise.resolve(handler || 0);
        }
        if (command === "plugin:event|unlisten") {
          // @tauri-apps/api/event._unlisten passes { event, eventId } where eventId is the handler id
          // registered into eventHandlers by listen. It must be removed, otherwise after page
          // navigation a single emit would fire all historical handlers — real Tauri stops delivering
          // after unlisten.
          const name = payload && payload.event;
          const eventId = payload && payload.eventId;
          const handlers = eventHandlers[name];
          if (Array.isArray(handlers)) {
            const index = handlers.indexOf(eventId);
            if (index !== -1) handlers.splice(index, 1);
          }
          return Promise.resolve();
        }
        // getVersion() (@tauri-apps/api/app) answers with the real app version so the update card shows "current 0.0.4"
        if (command === "plugin:app|version") return Promise.resolve("0.0.4");
        if (command === "plugin:window|show") { windowCalls.push({ command: command }); visible = true; return Promise.resolve(); }
        if (command === "plugin:window|set_position" || command === "plugin:window|set_size") { windowCalls.push({ command: command, value: payload && payload.value }); return Promise.resolve(); }
       return mockInvoke(command, payload);
     }
  };
  window.__MOCK_TAURI_THEME_CALLS__ = themeCalls;
  window.__MOCK_TAURI_COMMAND_CALLS__ = commandCalls;
  window.__MOCK_TAURI_WINDOW_CALLS__ = windowCalls;
  window.__MOCK_TAURI_RUNTIME_UPDATES__ = runtimeUpdates;
  window.__MOCK_TAURI_SET_API_MODE__ = function(mode) { apiTestMode = mode; };
  window.__MOCK_TAURI_SET_FULLSCREEN__ = function(value) { fullscreen = Boolean(value); };
  // Simulates the native destroyed hook: removes the pin; restores visibility only when it returns
  // true (last pin closed and the window was visible before the first pin).
  window.__MOCK_TAURI_CLOSE_PIN__ = function(label) {
    const restore = sessionRemove(label);
    if (restore === true) visible = true;
    return restore;
  };
  window.__MOCK_TAURI_PIN_LABELS__ = function() { return Array.from(pinSession.images.keys()); };
  // Visibility maintained by plugin:window|hide/show, reported truthfully by scripts recording commands.
  window.__MOCK_TAURI_IS_VISIBLE__ = function() { return visible; };

  // Before listen() registers a callback, @tauri-apps/api first calls transformCallback for a handler
  // id; in the real environment Tauri's IPC injects it, so the browser mock must provide it.
  window.__TAURI_INTERNALS__.transformCallback = window.__TAURI_INTERNALS__.transformCallback || function (callback) {
    // The once parameter is ignored: @tauri-apps/api's once() is implemented at the JS level with
    // listen + manual unlisten; the listen path never passes once, so the mock need not simulate
    // "auto-unregister after the first call".
    const id = Math.floor(Math.random() * 1e9);
    eventCallbacks[id] = callback;
    return id;
  };
  // Programmable emit hook for tests: any event + any payload, fully controlled by the test. Real
  // Tauri events arrive asynchronously over IPC, so each callback is deferred one macro task via
  // setTimeout(0), keeping timing semantics consistent with the real environment (synchronous
  // assertions right after emit must not hold).
  window.__MOCK_TAURI_EMIT__ = function (event, payload) {
    for (const id of eventHandlers[event] || []) {
      const callback = eventCallbacks[id];
      if (typeof callback === "function") {
        setTimeout(function () {
          try { callback({ event: event, id: id, payload: payload }); } catch (error) { console.warn("[Mock] event handler error for " + event + ":", error); }
        }, 0);
      }
    }
  };
  // Shortcut: simulate the backend's cold-start poll finding a new version (payload fixed at 9.9.9 to avoid repeating it in every test)
  window.__MOCK_EMIT_UPDATE__ = function () {
    window.__MOCK_TAURI_EMIT__("update-available", { version: "9.9.9", currentVersion: "0.0.4" });
  };
  // Injects the version detected by latest_release_version (mount-query path; null restores
  // "repo has no release", "__error__" makes invoke reject — mirroring the backend's Err "check failed" path).
  window.__MOCK_TAURI_SET_LATEST_VERSION__ = function (value) { latestReleaseVersion = value; };
  // Switches download_update's outcome: success (default) / error (error event) / reject (invoke fails immediately)
  window.__MOCK_TAURI_SET_DOWNLOAD_MODE__ = function (mode) { downloadMode = mode === "error" || mode === "reject" ? mode : "success"; };
  window.__MOCK_TAURI_SET_PIN_REJECT__ = function (value) { pinRejectMode = Boolean(value); };
  window.__MOCK_TAURI_SET_OCR_DELAY__ = function (ms) { aiOcrDelay = Number(ms) || 0; };
  window.__MOCK_TAURI_SET_LOCAL_OCR_MODE__ = function (mode) { localOcrMode = clampLocalOcrMode(mode); sessionStorage.setItem(LOCAL_OCR_MODE_KEY + ":ocr", localOcrMode); };
  window.__MOCK_TAURI_SET_LOCAL_OCR_LANGUAGES_MODE__ = function (mode) { localOcrLanguagesMode = clampLanguagesMode(mode); sessionStorage.setItem(LOCAL_OCR_MODE_KEY + ":langs", localOcrLanguagesMode); };

  // Also set __TAURI__ for older compatibility
  window.__TAURI__ = {
    invoke: mockInvoke,
    event: {
      listen: function(event, callback) { return Promise.resolve(function() {}); },
      emit: function(event, payload) { return Promise.resolve(); }
    },
    window: {
      getCurrent: function() {
        return {
          listen: function(event, callback) { return Promise.resolve(function() {}); },
          emit: function(event, payload) { return Promise.resolve(); },
          hide: function() { return Promise.resolve(); },
          show: function() { return Promise.resolve(); }
        };
      },
      getAll: function() { return []; }
    },
    path: {
      appConfigDir: function() { return Promise.resolve("/mock/config"); },
      appDataDir: function() { return Promise.resolve("/mock/data"); }
    }
  };

  console.log("[Mock] Tauri API injected successfully");
})();
