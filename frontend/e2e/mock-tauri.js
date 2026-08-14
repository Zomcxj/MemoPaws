// Mock Tauri API for Playwright E2E testing
// This script is injected via addInitScript before any page scripts run

(function() {
  const MOCK_THEME_KEY = "memopaws-mock-backend-theme";
  const storedTheme = sessionStorage.getItem(MOCK_THEME_KEY);
  let backendTheme = storedTheme === "light" || storedTheme === "dark" ? storedTheme : "dark";
  const themeCalls = [];
  const commandCalls = [];
  const windowCalls = [];
  const runtimeUpdates = [];
  let apiTestMode = "success-vision";
  let fullscreen = false;
  let visible = true;
  const MOCK_DATA = {
    key_list: [
      { id: 1, name: "Test LLM Key", type: "llm", url: "https://api.openai.com/v1", url_anthropic: "", note: "Test key", order: 0, created: "1700000000" },
      { id: 2, name: "Another Key", type: "llm", url: "https://api.anthropic.com", url_anthropic: "", note: "", order: 1, created: "1700000001" }
    ],
    list: [
      { id: 1, name: "Test LLM Key", type: "llm", url: "https://api.openai.com/v1", url_anthropic: "", note: "Test key", order: 0, created: "1700000000" }
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
      { id: 1, time: "1700000000", content_type: "text", text: "Clipboard text", image_path: null },
      { id: 2, time: "1700000001", content_type: "image", text: null, image_path: "1.png" }
    ],
       get_config: {
        language: "zh", close_behavior: "tray",
       has_api_key: true,
      clipboard_max_items: 50, history_max_items: 100, show_floating_widget: true,
       shortcuts: { capture: "Alt+X", canvas_fit: "Ctrl+F", new_memo: "Ctrl+N", global_search: "Ctrl+Shift+F" }
    },
    status: { has_master: true, unlocked: true, load_failed: false, version: 3 },
    memo_render: "<h1>Hello World</h1><p>This is a test memo.</p>",
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
          if (nextTheme === "light" || nextTheme === "dark") {
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
        } else if (command === "set_close_behavior" || command === "set_floating_widget_visible") {
          runtimeUpdates.push({ command: command, value: args && (args.value ?? args.visible) }); resolve();
        } else if (command === "get_storage_dir_conflict") {
          resolve(Boolean(args && args.path && String(args.path).includes("conflict")));
        } else if (command === "migrate_data_dir") {
          runtimeUpdates.push({ command: command, mode: args && args.mode }); resolve({ migrated: true, restart_required: true });
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
