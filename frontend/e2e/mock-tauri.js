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
  // 事件桩：eventHandlers 记录每个事件名注册的 handler id（plugin:event|listen 的返回值），
  // eventCallbacks 记录 transformCallback 分配的 id → 回调，emit 时按 id 取回调用
  const eventHandlers = {};
  const eventCallbacks = {};
  // latest_release_version 的可注入返回值：null 表示无更新（挂载查询路径静默）
  let latestReleaseVersion = null;
  // download_update 的结局模式：success（离线包→ready）/ error（→update-download-error）
  let downloadMode = "success";
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

   function mockInvoke(command, args) {
     commandCalls.push({ command: command, args: args || null, visible: visible });
     return new Promise(function(resolve) {
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
          MOCK_DATA.get_config.language = args && args.language === "en" ? "en" : "zh"; resolve();
        } else if (command === "get_config") {
          resolve(Object.assign({}, MOCK_DATA.get_config, { theme: backendTheme }));
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
          resolve({ image: [137, 80, 78, 71], preview: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1280' height='720'%3E%3Crect width='1280' height='720' fill='%23456789'/%3E%3C/svg%3E" });
        } else if (command === "image_crop") {
          resolve({ image: [137, 80, 78, 71] });
        } else if (command === "ai_ocr") {
          resolve({ text: "Mock OCR text" });
        } else if (command === "ai_translate") {
          resolve({ text: "Mock translation" });
        } else if (command === "latest_release_version") {
          resolve(latestReleaseVersion);
        } else if (command === "download_update") {
          // 镜像真实后端：command 立即 resolve，进度与终态通过事件异步派发。
          // 安装包路径后端直接交给 NSIS 安装器并 exit(0)，没有终态事件；
          // error 模式不发 ready，供测试驱动失败路径
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
  window.__TAURI_INTERNALS__ = {
    invoke: mockInvoke,
    metadata: { currentWindow: { label: "main" }, currentWebview: { label: "main" } },
    callbacks: {},
     invoke: function(command, payload) {
       if (command === "plugin:window|outer_position") return Promise.resolve({ x: 0, y: 0 });
       if (command === "plugin:window|outer_size") return Promise.resolve({ width: 1280, height: 720 });
       if (command === "plugin:window|is_fullscreen") { windowCalls.push({ command: command }); return Promise.resolve(fullscreen); }
        if (command === "plugin:window|set_fullscreen") { windowCalls.push({ command: command, value: payload && payload.value }); fullscreen = Boolean(payload && payload.value); return Promise.resolve(); }
        if (command === "plugin:window|hide") { windowCalls.push({ command: command }); visible = false; return Promise.resolve(); }
        // @tauri-apps/api/event 的 listen/unlisten 走这里；handler 是 transformCallback 返回的 id
        if (command === "plugin:event|listen") {
          const name = payload && payload.event;
          const handler = payload && payload.handler;
          (eventHandlers[name] = eventHandlers[name] || []).push(handler);
          return Promise.resolve(handler || 0);
        }
        if (command === "plugin:event|unlisten") return Promise.resolve();
        // getVersion()（@tauri-apps/api/app）用真实应用版本回答，更新卡片显示"当前 0.0.3"
        if (command === "plugin:app|version") return Promise.resolve("0.0.3");
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

  // listen() 注册回调前 @tauri-apps/api 会先调 transformCallback 拿 handler id，
  // 真实环境由 Tauri IPC 注入，浏览器 mock 环境必须自己补
  window.__TAURI_INTERNALS__.transformCallback = window.__TAURI_INTERNALS__.transformCallback || function (callback) {
    const id = Math.floor(Math.random() * 1e9);
    eventCallbacks[id] = callback;
    return id;
  };
  // 测试可编程 emit 钩子：任意事件 + 任意 payload，payload 完全由测试控制
  window.__MOCK_TAURI_EMIT__ = function (event, payload) {
    for (const id of eventHandlers[event] || []) {
      const callback = eventCallbacks[id];
      if (typeof callback === "function") {
        try { callback({ event: event, id: id, payload: payload }); } catch (error) { /* 测试桩忽略回调异常 */ }
      }
    }
  };
  // 快捷方式：模拟后端冷启动轮询发现新版本（payload 固定 9.9.9，避免每个测试重复写）
  window.__MOCK_EMIT_UPDATE__ = function () {
    window.__MOCK_TAURI_EMIT__("update-available", { version: "9.9.9", currentVersion: "0.0.3" });
  };
  // 注入 latest_release_version 的返回值（挂载查询路径；传 null 恢复"无更新"）
  window.__MOCK_TAURI_SET_LATEST_VERSION__ = function (value) { latestReleaseVersion = value; };
  // 切换 download_update 的结局：success（默认）/ error
  window.__MOCK_TAURI_SET_DOWNLOAD_MODE__ = function (mode) { downloadMode = mode === "error" ? "error" : "success"; };

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
