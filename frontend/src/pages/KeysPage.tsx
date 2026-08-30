import { FormEvent, KeyboardEvent, PointerEvent, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { Lang } from "../i18n/lang";
import "./KeysPage.css";

type KeyType = "llm" | "secret";
interface VaultStatus { has_master: boolean; unlocked: boolean; load_failed: boolean; version: number }
interface KeyEntry {
  id: number; name: string; type: KeyType; url: string; url_anthropic: string;
  note: string; order: number; created: string;
}
interface Draft {
  name: string; type: KeyType; value: string; url: string; url_anthropic: string; note: string;
}
type Latency = { ms?: number; error?: string };
const MATRIX_CHARS = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789";
const matrixFrame = () => Array.from({ length: 8 }, () => MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)]).join("");
const waitForRender = () => new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));

const blankDraft = (type: KeyType = "llm"): Draft => ({
  name: "", type, value: "", url: "", url_anthropic: "", note: "",
});
const errorText = (error: unknown) => (error instanceof Error ? error.message : String(error));

const isVisionModel = (note: string) =>
  /vision|vl|gpt-4o|claude-3|glm-4v|gemini|multimodal/i.test(note);

const shortUrl = (url: string) => {
  const cleaned = url.replace(/^https?:\/\//i, "");
  return cleaned.length > 30 ? `${cleaned.slice(0, 30)}…` : cleaned;
};

const copy = {
  zh: {
    opening: "正在打开密钥库…",
    loadFailTitle: "密钥库无法读取",
    loadFailBody: "为防止覆盖原文件，当前保持锁定且禁止写入。",
    lockedTitle: "密钥库已锁定",
    lockedBody: "输入主密码后才能查看条目元数据。",
    masterPh: "主密码",
    confirmMasterPh: "确认主密码",
    unlocking: "解锁中…",
    unlock: "解锁",
    badPassword: "主密码错误",
    passwordMismatch: "两次密码不一致",
    removeMasterConfirm: "确定要移除主密码吗？密钥将以明文保存。",
    removeMaster: "移除主密码",
    lock: "锁定",
    setMaster: "设置主密码",
    add: "添加密钥",
    testSpeed: "测试速度",
    importOc: "读取 opencode",
    ocConfirm: "从 opencode 读取到 {p} 个提供商 / {m} 个模型，全部导入为密钥？",
    ocDone: "已导入 {a} 个密钥，跳过已存在 {s} 个",
    ocNone: "opencode 配置中没有含 API Key 的提供商",
    testing: "测试中…",
    unauthorized: "API Key 无效 (401)",
    not_found: "地址不存在 (404)",
    timeout: "网络超时",
    connect: "无法连接服务器",
    forbidden: "无权限 (403)",
    rate_limit: "请求过多 (429)",
    service_unavailable: "服务暂不可用 (503)",
    request_timeout: "请求超时 (408)",
    bad_request: "请求无效 (400)",
    server_error: "服务器错误 (500)",
    bad_gateway: "网关错误 (502)",
    http_error: "请求失败",
    generic: "请求失败",
    cancel: "取消",
    close: "关闭",
    newKey: "添加密钥",
    editKey: "编辑密钥",
    name: "名称",
    llmType: "大模型密钥",
    secretType: "普通密钥",
    value: "API 密钥",
    openaiUrl: "OpenAI 地址",
    anthropicUrl: "Anthropic 地址",
    modelId: "模型ID",
    note: "备注",
    noteOptional: "备注（可选）",
    save: "保存",
    saving: "保存中…",
    llmTitle: "🤖 大模型密钥",
    secretTitle: "🔑 普通密钥",
    empty: "暂无密钥",
    model: "模型",
    source: "来源",
    latency: "延迟",
    multimodal: "多模态",
    textOnly: "文本",
    delete: "删除",
    edit: "编辑",
    setAsSettings: "设为密钥",
    setAsSettingsDone: "已设为设置密钥",
    copyBtn: "复制",
    showValue: "显示",
    hideValue: "隐藏",
    moveUp: "上移",
    moveDown: "下移",
    dragHandle: "拖动以重新排序；按上箭头或下箭头可立即调整顺序",
    masterTitle: "设置主密码",
    masterHint: "使用 scrypt 与 AES-256-GCM 加密。",
    enable: "启用加密",
    encrypting: "加密中…",
    nameRequired: "名称和密钥不能为空",
    typeLabel: "密钥类型",
  },
  en: {
    opening: "Opening vault…",
    loadFailTitle: "Vault unreadable",
    loadFailBody: "Staying locked to avoid overwriting the file.",
    lockedTitle: "Vault locked",
    lockedBody: "Enter the master password to view entries.",
    masterPh: "Master password",
    confirmMasterPh: "Confirm master password",
    unlocking: "Unlocking…",
    unlock: "Unlock",
    badPassword: "Wrong password",
    passwordMismatch: "Passwords do not match",
    removeMasterConfirm: "Remove master password? Keys will be stored in plain text.",
    removeMaster: "Remove master",
    lock: "Lock",
    setMaster: "Set master password",
    add: "Add Key",
    testSpeed: "Test Speed",
    importOc: "Import opencode",
    ocConfirm: "Found {p} providers / {m} models in opencode. Import all as keys?",
    ocDone: "Imported {a} keys, skipped {s} existing",
    ocNone: "No providers with API keys found in opencode config",
    testing: "Testing…",
    unauthorized: "Invalid API Key (401)",
    not_found: "Endpoint not found (404)",
    timeout: "Network timeout",
    connect: "Could not connect to server",
    forbidden: "Forbidden (403)",
    rate_limit: "Rate limited (429)",
    service_unavailable: "Service unavailable (503)",
    request_timeout: "Request timeout (408)",
    bad_request: "Bad request (400)",
    server_error: "Server error (500)",
    bad_gateway: "Bad gateway (502)",
    http_error: "Request failed",
    generic: "Request failed",
    cancel: "Cancel",
    close: "Close",
    newKey: "Add Key",
    editKey: "Edit Key",
    name: "Name",
    llmType: "LLM Key",
    secretType: "Secret Key",
    value: "API Key",
    openaiUrl: "OpenAI URL",
    anthropicUrl: "Anthropic URL",
    modelId: "Model ID",
    note: "Note",
    noteOptional: "Note (optional)",
    save: "Save",
    saving: "Saving…",
    llmTitle: "🤖 Model keys",
    secretTitle: "🔑 Secrets",
    empty: "No keys",
    model: "Model",
    source: "Source",
    latency: "Latency",
    multimodal: "Multimodal",
    textOnly: "Text",
    delete: "Delete",
    edit: "Edit",
    setAsSettings: "Set as key",
    setAsSettingsDone: "Set as settings key",
    copyBtn: "Copy",
    showValue: "Show",
    hideValue: "Hide",
    moveUp: "Move up",
    moveDown: "Move down",
    dragHandle: "Drag to reorder; press ArrowUp or ArrowDown to move immediately",
    masterTitle: "Set master password",
    masterHint: "Uses scrypt and AES-256-GCM.",
    enable: "Enable",
    encrypting: "Encrypting…",
    nameRequired: "Name and key cannot be empty",
    typeLabel: "Key type",
  },
} as const;

type Texts = (typeof copy)[Lang];

export function KeysPage({ language = "zh" }: { language?: Lang }) {
  const t = copy[language];
  const [vault, setVault] = useState<VaultStatus | null>(null);
  const [entries, setEntries] = useState<KeyEntry[]>([]);
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [draft, setDraft] = useState<Draft>(blankDraft());
  const [editing, setEditing] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [showMaster, setShowMaster] = useState(false);
  const [showValue, setShowValue] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [latency, setLatency] = useState<Record<number, Latency>>({});
  const [testingGlyphs, setTestingGlyphs] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reordering, setReordering] = useState(false);
  const [dragging, setDragging] = useState<{ id: number; type: KeyType } | null>(null);
  const [overId, setOverId] = useState<number | null>(null);
  const [dragOffset, setDragOffset] = useState<{ x: number; y: number } | null>(null);
  const entriesRef = useRef(entries);
  useEffect(() => {
    entriesRef.current = entries;
  }, [entries]);
  const pointerDrag = useRef<{ id: number; type: KeyType; x: number; y: number; started: boolean; targetId: number | null; insertAfter: boolean } | null>(null);

  const wipeSensitiveState = () => {
    setDraft(blankDraft());
    setPassword("");
    setPassword2("");
    setEditing(null);
    setShowForm(false);
    setShowMaster(false);
    setShowValue(false);
  };

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const status = await invoke<VaultStatus>("status");
      setVault(status);
      setEntries(status.unlocked ? await invoke<KeyEntry[]>("list") : []);
      if (!status.unlocked) wipeSensitiveState();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    void refresh();
    const unlisten = listen("vault-locked", () => {
      if (!active) return;
      wipeSensitiveState();
      setEntries([]);
      setVault((current) => (current ? { ...current, unlocked: false } : current));
    });
    return () => {
      active = false;
      void unlisten.then((stop) => stop());
      wipeSensitiveState();
    };
  }, []);

  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await operation();
      await refresh();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };

  const authenticate = () =>
    run(async () => {
      if (vault?.has_master) {
        if (!(await invoke<boolean>("unlock", { password }))) throw new Error(t.badPassword);
      } else {
        if (password !== password2) throw new Error(t.passwordMismatch);
        await invoke("set_master", { password });
      }
      wipeSensitiveState();
    });

  const lockVault = () =>
    run(async () => {
      await invoke("lock");
      wipeSensitiveState();
      setLatency({});
    });

  const removeMaster = () => {
    if (!window.confirm(t.removeMasterConfirm)) return;
    void run(async () => {
      await invoke("remove_master");
      wipeSensitiveState();
    });
  };

  const openAdd = () => {
    setEditing(null);
    setDraft(blankDraft("llm"));
    setShowValue(false);
    setShowForm(true);
  };

  const importOpencode = () => void run(async () => {
    const providers = await invoke<{ id: string; url: string; apiKey: string; models: string[] }[]>("list_opencode_providers");
    if (!providers.length) { setError(t.ocNone); return; }
    const total = providers.reduce((count, provider) => count + provider.models.length, 0);
    if (!window.confirm(t.ocConfirm.replace("{p}", String(providers.length)).replace("{m}", String(total)))) return;
    const existing = new Set(entries.map((entry) => entry.name));
    let added = 0;
    let skipped = 0;
    for (const provider of providers) {
      for (const model of provider.models) {
        const name = model ? `${provider.id}/${model}` : provider.id;
        if (existing.has(name)) { skipped += 1; continue; }
        await invoke("add", { entry: { name, type: "llm", value: provider.apiKey, url: provider.url, url_anthropic: "", note: model } });
        existing.add(name);
        added += 1;
      }
    }
    await refresh();
    window.alert(t.ocDone.replace("{a}", String(added)).replace("{s}", String(skipped)));
  });

  const openEdit = async (entry: KeyEntry) => {
    setError("");
    try {
      const value = await invoke<string>("get_value", { id: entry.id });
      setDraft({
        name: entry.name,
        type: entry.type,
        value,
        url: entry.url,
        url_anthropic: entry.url_anthropic,
        note: entry.note,
      });
      setEditing(entry.id);
      setShowValue(false);
      setShowForm(true);
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const saveEntry = (event: FormEvent) => {
    event.preventDefault();
    if (!draft.name.trim() || !draft.value.trim()) {
      setError(t.nameRequired);
      return;
    }
    void run(async () => {
      await invoke(
        editing === null ? "add" : "update",
        editing === null ? { entry: draft } : { id: editing, entry: draft },
      );
      await invoke("get_config").catch(() => {});
      wipeSensitiveState();
    });
  };

  const remove = (entry: KeyEntry) => {
    void run(async () => {
      await invoke("delete", { id: entry.id });
      setLatency((current) => {
        const next = { ...current };
        delete next[entry.id];
        return next;
      });
    });
  };

  const setSettings = (entry: KeyEntry) => {
    void run(async () => {
      await invoke("set_settings_key", { entryId: entry.id });
      setNotice(`${t.setAsSettingsDone}：${entry.name}`);
      window.setTimeout(() => setNotice(""), 3000);
    });
  };

  const copyValue = async (entry: KeyEntry) => {
    setError("");
    try {
      const value = await invoke<string>("get_value", { id: entry.id });
      await navigator.clipboard.writeText(value);
      const snapshot = value;
      window.setTimeout(async () => {
        try {
          const current = await navigator.clipboard.readText();
          if (current === snapshot) await navigator.clipboard.writeText("");
        } catch {
          /* ignore */
        }
      }, 30_000);
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  const testSpeed = async () => {
    const llm = entries.filter((entry) => entry.type === "llm");
    if (!llm.length) return;
    setTesting(true);
    setError("");
    try {
      for (const entry of llm) {
        setTestingGlyphs({ [entry.id]: matrixFrame() });
        const ticker = window.setInterval(() => setTestingGlyphs({ [entry.id]: matrixFrame() }), 70);
        let result: Latency;
        try {
          const response = await invoke<Record<string, unknown>>("test_api_connection", {
            keyEntryId: entry.id,
            model: entry.note || "glm-4v-flash",
          });
            result = response.status_code === 200
            ? {
                ms: typeof response.elapsed_ms === "number" ? response.elapsed_ms : undefined,
              }
            : {
                error: (() => {
                  const category = typeof response.error === "string" ? response.error : "generic";
                  const localized = t[category as keyof Texts];
                  return typeof localized === "string" ? localized : `${t.http_error} (${response.status_code || ""})`;
                })(),
              };
        } catch (reason) {
          result = { error: errorText(reason) };
        } finally {
          window.clearInterval(ticker);
        }
        setLatency((current) => ({ ...current, [entry.id]: result }));
        setTestingGlyphs({});
        await waitForRender();
      }
    } finally {
      setTestingGlyphs({});
      setTesting(false);
    }
  };

  const commitReorder = async (type: KeyType, orderedIds: number[]) => {
    if (reordering) return;
    const previous = entriesRef.current;
    setEntries((current) =>
      current.map((entry) => {
        const index = orderedIds.indexOf(entry.id);
        return entry.type === type && index >= 0 ? { ...entry, order: index } : entry;
      }),
    );
    setError("");
    setReordering(true);
    try {
      await invoke("reorder", { entryType: type, ids: orderedIds });
    } catch (reason) {
      setEntries(previous);
      setError(errorText(reason));
    } finally {
      setReordering(false);
    }
  };

  const beginPointerDrag = (event: PointerEvent<HTMLElement>, entry: KeyEntry) => {
    if (reordering) return;
    if ((event.target as HTMLElement).closest("button, a, input, select, textarea")) return;
    pointerDrag.current = { id: entry.id, type: entry.type, x: event.clientX, y: event.clientY, started: false, targetId: null, insertAfter: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const movePointerDrag = (event: PointerEvent<HTMLElement>, entry: KeyEntry) => {
    const drag = pointerDrag.current;
    if (!drag || drag.id !== entry.id) return;
    if (!drag.started) {
      const dragThreshold = entry.type === "llm" ? 8 : 18;
      if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < dragThreshold) return;
      drag.started = true;
      setDragging({ id: entry.id, type: entry.type });
    }
    event.preventDefault();
    const offsetX = event.clientX - drag.x;
    const offsetY = event.clientY - drag.y;
    setDragOffset({ x: offsetX, y: offsetY });
    const container = document.querySelector(`[data-key-grid="${drag.type}"]`);
    if (!container) return;
    const rows = Array.from(container.querySelectorAll<HTMLElement>("[data-key-id]"));
    if (!rows.length) return;
    const dragged = container.querySelector<HTMLElement>(`[data-key-id="${drag.id}"]`);
    if (!dragged) return;
    const dragRect = dragged.getBoundingClientRect();
    const movedRect = {
      left: dragRect.left + offsetX,
      top: dragRect.top + offsetY,
      right: dragRect.right + offsetX,
      bottom: dragRect.bottom + offsetY,
      width: dragRect.width,
      height: dragRect.height,
    };
    const dragArea = dragRect.width * dragRect.height;
    let targetId: number | null = null;
    let insertAfter = false;
    if (drag.type === "llm") {
      let nearestDistance = Number.POSITIVE_INFINITY;
      for (const row of rows) {
        const id = Number(row.dataset.keyId);
        if (id === drag.id) continue;
        const rect = row.getBoundingClientRect();
        const overlapArea =
          Math.max(0, Math.min(movedRect.right, rect.right) - Math.max(movedRect.left, rect.left)) *
          Math.max(0, Math.min(movedRect.bottom, rect.bottom) - Math.max(movedRect.top, rect.top));
        if (overlapArea <= dragArea / 2) continue;
        const dragCenterX = movedRect.left + movedRect.width / 2;
        const dragCenterY = movedRect.top + movedRect.height / 2;
        const distance = Math.hypot(dragCenterX - (rect.left + rect.width / 2), dragCenterY - (rect.top + rect.height / 2));
        if (distance < nearestDistance) {
          nearestDistance = distance;
          targetId = id;
        }
      }
    } else {
      for (const row of rows) {
        const id = Number(row.dataset.keyId);
        if (id === drag.id) continue;
        const rect = row.getBoundingClientRect();
        const overlapArea =
          Math.max(0, Math.min(movedRect.right, rect.right) - Math.max(movedRect.left, rect.left)) *
          Math.max(0, Math.min(movedRect.bottom, rect.bottom) - Math.max(movedRect.top, rect.top));
        if (overlapArea <= dragArea / 2) continue;
        targetId = id;
        insertAfter = movedRect.top + movedRect.height / 2 > rect.top + rect.height / 2;
        break;
      }
    }
    drag.targetId = targetId;
    drag.insertAfter = insertAfter;
    setOverId(targetId);
  };

  const commitDrag = (drag: { id: number; type: KeyType; targetId: number | null; insertAfter: boolean }) => {
    const group = entriesRef.current.filter((entry) => entry.type === drag.type).sort((a, b) => a.order - b.order);
    const from = group.findIndex((entry) => entry.id === drag.id);
    const target = group.findIndex((entry) => entry.id === drag.targetId);
    if (from >= 0 && target >= 0 && drag.targetId !== drag.id) {
      const ordered = group.map((entry) => entry.id);
      if (drag.type === "llm") {
        [ordered[from], ordered[target]] = [ordered[target], ordered[from]];
      } else {
        const [moved] = ordered.splice(from, 1);
        let insertion = target + (drag.insertAfter ? 1 : 0);
        if (from < insertion) insertion -= 1;
        ordered.splice(insertion, 0, moved);
      }
      void commitReorder(drag.type, ordered);
    }
  };

  const endPointerDrag = (_event: PointerEvent<HTMLElement>, _entry: KeyEntry) => {
    const drag = pointerDrag.current;
    if (!drag) return;
    if (drag.started) commitDrag(drag);
    pointerDrag.current = null;
    setDragging(null);
    setOverId(null);
    setDragOffset(null);
  };

  const handleDragKeyDown = (event: KeyboardEvent<HTMLElement>, entry: KeyEntry) => {
    const drag = pointerDrag.current;
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      if (!drag || !drag.started || drag.id !== entry.id) {
        if (reordering) return;
        pointerDrag.current = { id: entry.id, type: entry.type, x: 0, y: 0, started: true, targetId: null, insertAfter: false };
        setDragging({ id: entry.id, type: entry.type });
        setDragOffset({ x: 0, y: 0 });
      } else {
        const finished = drag;
        pointerDrag.current = null;
        setDragging(null);
        setOverId(null);
        setDragOffset(null);
        commitDrag(finished);
      }
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!drag || !drag.started || drag.id !== entry.id) {
        if (reordering) return;
        pointerDrag.current = { id: entry.id, type: entry.type, x: 0, y: 0, started: true, targetId: null, insertAfter: false };
        setDragging({ id: entry.id, type: entry.type });
        setDragOffset({ x: 0, y: 0 });
      }
      const activeDrag = pointerDrag.current!;
      const group = entriesRef.current.filter((item) => item.type === activeDrag.type).sort((a, b) => a.order - b.order);
      const from = group.findIndex((item) => item.id === activeDrag.id);
      const next = group[from + (event.key === "ArrowDown" ? 1 : -1)];
      if (next) {
        activeDrag.targetId = next.id;
        activeDrag.insertAfter = activeDrag.type === "secret" && event.key === "ArrowDown";
        setOverId(next.id);
        const finished = activeDrag;
        pointerDrag.current = null;
        setDragging(null);
        setOverId(null);
        setDragOffset(null);
        commitDrag(finished);
      }
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      pointerDrag.current = null;
      setDragging(null);
      setOverId(null);
      setDragOffset(null);
    }
  };

  const handleDragKeyUp = (_event: KeyboardEvent<HTMLElement>, _entry: KeyEntry) => {};

  if (loading && !vault) {
    return (
      <section className="keys-page">
        <div className="keys-state">{t.opening}</div>
      </section>
    );
  }
  if (vault?.load_failed) {
    return (
      <section className="keys-page">
        <div className="keys-state keys-danger">
          <h2>{t.loadFailTitle}</h2>
          <p>{t.loadFailBody}</p>
          {error && <p>{error}</p>}
        </div>
      </section>
    );
  }

  if (vault && !vault.unlocked) {
    return (
      <section className="keys-page keys-gate">
        <div className="keys-lock-card">
          <h1>{vault.has_master ? t.lockedTitle : t.setMaster}</h1>
          <p>{vault.has_master ? t.lockedBody : t.masterHint}</p>
          <input
            autoFocus
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void authenticate();
            }}
            placeholder={t.masterPh}
          />
          {!vault.has_master && (
            <input
              type="password"
              value={password2}
              onChange={(event) => setPassword2(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void authenticate();
              }}
              placeholder={t.confirmMasterPh}
            />
          )}
          <button
            onClick={() => void authenticate()}
            disabled={busy || !password || (!vault.has_master && !password2)}
          >
            {busy ? (vault.has_master ? t.unlocking : t.encrypting) : vault.has_master ? t.unlock : t.enable}
          </button>
          {error && (
            <div className="keys-inline-error" role="alert">
              {error}
            </div>
          )}
        </div>
      </section>
    );
  }

  const llmEntries = entries.filter((e) => e.type === "llm" && e.name !== "settings_api_key").sort((a, b) => a.order - b.order);
  const secretEntries = entries.filter((e) => e.type === "secret").sort((a, b) => a.order - b.order);

  return (
    <section className="keys-page">
      <header className="keys-header">
        <div className="keys-header-actions">
          {vault?.has_master ? (
            <>
              <button onClick={removeMaster} disabled={busy}>
                {t.removeMaster}
              </button>
              <button onClick={() => void lockVault()} disabled={busy}>
                {t.lock}
              </button>
            </>
          ) : (
            <button
              className="primary"
              onClick={() => {
                setPassword("");
                setPassword2("");
                setShowMaster(true);
              }}
            >
              {t.setMaster}
            </button>
          )}
          <button className="primary" onClick={openAdd} disabled={busy}>
            {t.add}
          </button>
          <button onClick={() => void importOpencode()} disabled={busy}>
            {t.importOc}
          </button>
          <button onClick={() => void testSpeed()} disabled={busy || testing || !llmEntries.length}>
            {testing ? t.testing : t.testSpeed}
          </button>
        </div>
      </header>

      {error && (
        <div className="keys-error" role="alert">
          <span>{error}</span>
          <button onClick={() => setError("")}>{t.close}</button>
        </div>
      )}

      {notice && <div className="keys-notice" role="status">{notice}</div>}

      <div className="keys-columns">
        <section className="keys-group">
          <div className="keys-group-title">
            <h2>{t.llmTitle}</h2>
          </div>
          {!loading && llmEntries.length === 0 ? (
            <div className="keys-empty">{t.empty}</div>
          ) : (
            <div className="keys-grid keys-grid-llm" data-key-grid="llm">
              {llmEntries.map((entry) => (
                <LlmCard
                  key={entry.id}
                  entry={entry}
                  latency={latency[entry.id]}
                  testingGlyph={testingGlyphs[entry.id]}
                  t={t}
                  onEdit={() => void openEdit(entry)}
                  onDelete={() => remove(entry)}
                  onSetSettings={() => setSettings(entry)}
                  isDragging={dragging?.id === entry.id}
                  isDropTarget={overId === entry.id && dragging?.id !== entry.id}
                  dragOffset={dragging?.id === entry.id ? dragOffset : null}
                  onHandleKeyDown={(event) => handleDragKeyDown(event, entry)}
                  onHandleKeyUp={(event) => handleDragKeyUp(event, entry)}
                  onPointerDown={(event) => beginPointerDrag(event, entry)}
                  onPointerMove={(event) => movePointerDrag(event, entry)}
                  onPointerUp={(event) => endPointerDrag(event, entry)}
                />
              ))}
            </div>
          )}
        </section>

        <section className="keys-group">
          <div className="keys-group-title">
            <h2>{t.secretTitle}</h2>
          </div>
          {!loading && secretEntries.length === 0 ? (
            <div className="keys-empty">{t.empty}</div>
          ) : (
            <div className="keys-grid keys-grid-secret" data-key-grid="secret">
              {secretEntries.map((entry) => (
                <SecretRow
                  key={entry.id}
                  entry={entry}
                  t={t}
                  onCopy={() => void copyValue(entry)}
                  onEdit={() => void openEdit(entry)}
                  onDelete={() => remove(entry)}
                  isDragging={dragging?.id === entry.id}
                  isDropTarget={overId === entry.id && dragging?.id !== entry.id}
                  dragOffset={dragging?.id === entry.id ? dragOffset : null}
                  onHandleKeyDown={(event) => handleDragKeyDown(event, entry)}
                  onHandleKeyUp={(event) => handleDragKeyUp(event, entry)}
                  onPointerDown={(event) => beginPointerDrag(event, entry)}
                  onPointerMove={(event) => movePointerDrag(event, entry)}
                  onPointerUp={(event) => endPointerDrag(event, entry)}
                />
              ))}
            </div>
          )}
        </section>
      </div>

      {showForm && (
        <EntryDialog
          t={t}
          draft={draft}
          editing={editing !== null}
          busy={busy}
          showValue={showValue}
          onShowValue={setShowValue}
          onChange={setDraft}
          onClose={wipeSensitiveState}
          onSubmit={saveEntry}
        />
      )}

      {showMaster && (
        <div className="keys-modal" role="presentation" onMouseDown={wipeSensitiveState}>
          <div
            role="dialog"
            aria-modal="true"
            className="keys-popover"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="keys-form-head">
              <h2>{t.masterTitle}</h2>
              <button type="button" onClick={wipeSensitiveState}>
                {t.close}
              </button>
            </div>
            <p>{t.masterHint}</p>
            <input
              autoFocus
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t.masterPh}
              autoComplete="new-password"
            />
            <input
              type="password"
              value={password2}
              onChange={(event) => setPassword2(event.target.value)}
              placeholder={t.confirmMasterPh}
              autoComplete="new-password"
            />
            <button
              className="primary"
              disabled={!password || !password2 || busy}
              onClick={() => void authenticate()}
            >
              {busy ? t.encrypting : t.enable}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function LlmCard({
  entry,
  latency,
  testingGlyph,
  t,
  onEdit,
  onDelete,
  onSetSettings,
  isDragging,
  isDropTarget,
  dragOffset,
  onHandleKeyDown,
  onHandleKeyUp,
  onPointerDown,
  onPointerMove,
  onPointerUp,
}: {
  entry: KeyEntry;
  latency?: Latency;
  testingGlyph?: string;
  t: Texts;
  onEdit: () => void;
  onDelete: () => void;
  onSetSettings: () => void;
  isDragging: boolean;
  isDropTarget: boolean;
  dragOffset: { x: number; y: number } | null;
  onHandleKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  onHandleKeyUp: (event: KeyboardEvent<HTMLElement>) => void;
  onPointerDown: (event: PointerEvent<HTMLElement>) => void;
  onPointerMove: (event: PointerEvent<HTMLElement>) => void;
  onPointerUp: (event: PointerEvent<HTMLElement>) => void;
}) {
  const vision = isVisionModel(entry.note);
  const latencyText = testingGlyph || (latency?.error
    ? latency.error
    : latency?.ms != null
      ? `${Math.round(latency.ms)} ms`
       : "--");
  const latencyClass =
    latency?.error
      ? "is-bad"
      : latency?.ms != null
        ? latency.ms < 500
          ? "is-good"
          : latency.ms < 1000
            ? "is-mid"
            : "is-bad"
        : "";

  return (
    <article
      className={`key-card key-card-llm${isDragging ? " is-dragging" : ""}${isDropTarget ? " is-drop-target" : ""}`}
      data-key-id={entry.id}
      style={isDragging && dragOffset ? { transform: `translate3d(${dragOffset.x}px, ${dragOffset.y}px, 0) scale(1.02)`, position: "relative", zIndex: 5 } : undefined}
    >
      <div className="key-card-top">
        <span
          className="key-drag-handle"
          role="button"
          aria-label={t.dragHandle}
          tabIndex={0}
          onKeyDown={onHandleKeyDown}
          onKeyUp={onHandleKeyUp}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          ⠿
        </span>
        <h3>{entry.name}</h3>
        <div className="key-link-actions">
          {entry.name !== "settings_api_key" && (
            <button type="button" className="link" onClick={onSetSettings}>
              {t.setAsSettings}
            </button>
          )}
          <button type="button" className="link" onClick={onDelete}>
            {t.delete}
          </button>
          <button type="button" className="link" onClick={onEdit}>
            {t.edit}
          </button>
        </div>
      </div>
      <p>
        {t.model}: {entry.note || "-"}
      </p>
      <p>
        {t.source}: {entry.url ? shortUrl(entry.url) : "-"}
      </p>
       <p className={`key-latency ${testingGlyph ? "is-testing" : latencyClass}`}>
        {t.latency}: {latencyText}
      </p>
      <div className="key-badges">
        {entry.url ? <span className="badge">OpenAI</span> : null}
        {entry.url_anthropic ? <span className="badge">Anthropic</span> : null}
        <span className={`badge ${vision ? "is-vision" : ""}`}>
          {vision ? t.multimodal : t.textOnly}
        </span>
      </div>
    </article>
  );
}

function SecretRow({
  entry,
  t,
  onCopy,
  onEdit,
  onDelete,
  isDragging,
  isDropTarget,
  dragOffset,
  onHandleKeyDown,
  onHandleKeyUp,
  onPointerDown,
  onPointerMove,
  onPointerUp,
}: {
  entry: KeyEntry;
  t: Texts;
  onCopy: () => void;
  onEdit: () => void;
  onDelete: () => void;
  isDragging: boolean;
  isDropTarget: boolean;
  dragOffset: { x: number; y: number } | null;
  onHandleKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  onHandleKeyUp: (event: KeyboardEvent<HTMLElement>) => void;
  onPointerDown: (event: PointerEvent<HTMLElement>) => void;
  onPointerMove: (event: PointerEvent<HTMLElement>) => void;
  onPointerUp: (event: PointerEvent<HTMLElement>) => void;
}) {
  return (
    <article
      className={`key-row-secret${isDragging ? " is-dragging" : ""}${isDropTarget ? " is-drop-target" : ""}`}
      data-key-id={entry.id}
      style={isDragging && dragOffset ? { transform: `translate3d(${dragOffset.x}px, ${dragOffset.y}px, 0) scale(1.02)`, position: "relative", zIndex: 5 } : undefined}
    >
      <span
        className="key-drag-handle"
        role="button"
        aria-label={t.dragHandle}
        tabIndex={0}
        onKeyDown={onHandleKeyDown}
        onKeyUp={onHandleKeyUp}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        ⠿
      </span>
      <strong className="key-row-name">{entry.name}</strong>
      <div className="key-row-actions">
        <button type="button" onClick={onCopy}>
          {t.copyBtn}
        </button>
        <button type="button" onClick={onEdit}>
          {t.edit}
        </button>
        <button type="button" className="danger" onClick={onDelete}>
          {t.delete}
        </button>
      </div>
    </article>
  );
}

function EntryDialog({
  t,
  draft,
  editing,
  busy,
  showValue,
  onShowValue,
  onChange,
  onClose,
  onSubmit,
}: {
  t: Texts;
  draft: Draft;
  editing: boolean;
  busy: boolean;
  showValue: boolean;
  onShowValue: (value: boolean) => void;
  onChange: (draft: Draft) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent) => void;
}) {
  const isLlm = draft.type === "llm";
  return (
    <div className="keys-modal" role="presentation" onMouseDown={onClose}>
      <form
        className="keys-dialog"
        role="dialog"
        aria-modal="true"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={onSubmit}
      >
        <div className="keys-form-head">
          <h2>{editing ? t.editKey : t.newKey}</h2>
        </div>

        <label>
          {t.name}
          <input
            required
            value={draft.name}
            onChange={(e) => onChange({ ...draft, name: e.target.value })}
            placeholder={t.name}
          />
        </label>

        <label>
          {t.typeLabel}
          <select
            value={draft.type}
            onChange={(e) => onChange({ ...draft, type: e.target.value as KeyType })}
          >
            <option value="llm">{t.llmType}</option>
            <option value="secret">{t.secretType}</option>
          </select>
        </label>

        {isLlm && (
          <>
            <label>
              {t.openaiUrl}
              <input
                value={draft.url}
                onChange={(e) => onChange({ ...draft, url: e.target.value })}
                placeholder="https://api.openai.com/v1/chat/completions"
              />
            </label>
            <label>
              {t.anthropicUrl}
              <input
                value={draft.url_anthropic}
                onChange={(e) => onChange({ ...draft, url_anthropic: e.target.value })}
                placeholder="https://api.anthropic.com/v1/messages"
              />
            </label>
            <label>
              {t.modelId}
              <input
                value={draft.note}
                onChange={(e) => onChange({ ...draft, note: e.target.value })}
                placeholder="glm-4v-flash"
              />
            </label>
          </>
        )}

        {!isLlm && (
          <label>
            {t.noteOptional}
            <input
              value={draft.note}
              onChange={(e) => onChange({ ...draft, note: e.target.value })}
              placeholder={t.note}
            />
          </label>
        )}

        <label>
          {t.value}
          <div className="keys-value-row">
            <input
              required
              type={showValue ? "text" : "password"}
              autoComplete="off"
              value={draft.value}
              onChange={(e) => onChange({ ...draft, value: e.target.value })}
            />
            <button type="button" onClick={() => onShowValue(!showValue)}>
              {showValue ? t.hideValue : t.showValue}
            </button>
            <button
              type="button"
              onClick={() => void navigator.clipboard.writeText(draft.value)}
              disabled={!draft.value}
            >
              {t.copyBtn}
            </button>
          </div>
        </label>

        <div className="keys-dialog-actions">
          <button type="button" onClick={onClose}>
            {t.cancel}
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? t.saving : t.save}
          </button>
        </div>
      </form>
    </div>
  );
}
