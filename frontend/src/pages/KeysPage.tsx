import { FormEvent, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import "./KeysPage.css";

type KeyType = "llm" | "secret";
interface VaultStatus { has_master: boolean; unlocked: boolean; load_failed: boolean; version: number }
interface KeyEntry { id: number; name: string; type: KeyType; url: string; url_anthropic: string; note: string; order: number; created: string }
interface Draft { name: string; type: KeyType; value: string; url: string; url_anthropic: string; note: string }
const blankDraft = (type: KeyType = "secret"): Draft => ({ name: "", type, value: "", url: "", url_anthropic: "", note: "" });
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

export function KeysPage() {
  const [vault, setVault] = useState<VaultStatus | null>(null);
  const [entries, setEntries] = useState<KeyEntry[]>([]);
  const [revealed, setRevealed] = useState<Record<number, string>>({});
  const [password, setPassword] = useState("");
  const [draft, setDraft] = useState<Draft>(blankDraft());
  const [editing, setEditing] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [showMaster, setShowMaster] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const wipeSensitiveState = () => {
    setDraft(blankDraft());
    setPassword("");
    setRevealed({});
    setEditing(null);
    setShowForm(false);
    setShowMaster(false);
  };

  const refresh = async () => {
    setLoading(true); setError("");
    try {
      const status = await invoke<VaultStatus>("status");
      setVault(status);
      setEntries(status.unlocked ? await invoke<KeyEntry[]>("list") : []);
      if (!status.unlocked) wipeSensitiveState();
    } catch (reason) { setError(errorText(reason)); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    let active = true;
    void refresh();
    const unlisten = listen("vault-locked", () => {
      if (!active) return;
      wipeSensitiveState();
      setEntries([]);
      setVault((current) => current ? { ...current, unlocked: false } : current);
    });
    return () => {
      active = false;
      void unlisten.then((stop) => stop());
      wipeSensitiveState();
    };
  }, []);

  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true); setError("");
    try { await operation(); await refresh(); }
    catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  };

  const authenticate = () => run(async () => {
    if (vault?.has_master) {
      if (!await invoke<boolean>("unlock", { password })) throw new Error("主密码错误");
    } else await invoke("set_master", { password });
    wipeSensitiveState();
  });

  const lockVault = () => run(async () => { await invoke("lock"); wipeSensitiveState(); });
  const removeMaster = () => {
    if (!window.confirm("移除主密码后，密钥将以明文写入本机文件。确定继续吗？")) return;
    void run(async () => { await invoke("remove_master"); wipeSensitiveState(); });
  };

  const reveal = async (entry: KeyEntry, copy = false) => {
    setError("");
    try {
      const value = await invoke<string>("get_value", { id: entry.id });
      if (copy) {
        await navigator.clipboard.writeText(value);
        window.setTimeout(() => void navigator.clipboard.writeText(""), 30_000);
      } else setRevealed((current) => ({ ...current, [entry.id]: value }));
    } catch (reason) { setError(errorText(reason)); }
  };

  const startEdit = async (entry: KeyEntry) => {
    setError("");
    try {
      const value = await invoke<string>("get_value", { id: entry.id });
      setDraft({ name: entry.name, type: entry.type, value, url: entry.url, url_anthropic: entry.url_anthropic, note: entry.note });
      setEditing(entry.id); setShowForm(true);
    } catch (reason) { setError(errorText(reason)); }
  };

  const save = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      await invoke(editing === null ? "add" : "update", editing === null ? { entry: draft } : { id: editing, entry: draft });
      wipeSensitiveState();
    });
  };

  const remove = (entry: KeyEntry) => {
    if (!window.confirm(`删除“${entry.name}”？此操作无法撤销。`)) return;
    void run(async () => { await invoke("delete", { id: entry.id }); setRevealed((current) => { const next = { ...current }; delete next[entry.id]; return next; }); });
  };

  if (loading && !vault) return <section className="keys-page"><div className="keys-state">正在打开密钥库…</div></section>;
  if (vault?.load_failed) return <section className="keys-page"><div className="keys-state keys-danger"><h2>密钥库无法读取</h2><p>为防止覆盖原文件，当前保持锁定且禁止写入。</p>{error && <p>{error}</p>}</div></section>;
  if (vault && !vault.unlocked) return <section className="keys-page keys-gate"><div className="keys-lock-card"><h1>密钥库已锁定</h1><p>输入主密码后才能查看条目元数据。</p><input autoFocus type="password" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void authenticate(); }} placeholder="主密码" /><button onClick={() => void authenticate()} disabled={busy || !password}>{busy ? "解锁中…" : "解锁密钥库"}</button>{error && <div className="keys-inline-error" role="alert">{error}</div>}</div></section>;

  const groups: { type: KeyType; title: string; hint: string }[] = [{ type: "llm", title: "🤖 大模型密钥", hint: "API 密钥与服务端点" }, { type: "secret", title: "🔑 普通密钥", hint: "账号、令牌与其他秘密" }];
   return <section className="keys-page">
     <header className="keys-header">
       <div className="keys-header-actions">
         {vault?.has_master ? (
           <>
             <button onClick={removeMaster} disabled={busy}>移除主密码</button>
             <button onClick={() => void lockVault()} disabled={busy}>锁定</button>
           </>
         ) : (
           <button className="primary" onClick={() => { setPassword(""); setShowMaster(true); }}>设置主密码</button>
         )}
         <button className="primary" onClick={() => { setEditing(null); setDraft(blankDraft()); setShowForm(true); }}>添加密钥</button>
         <button onClick={() => void run(async () => { for (const entry of entries.filter((e) => e.type === "llm")) { try { await invoke<string>("get_value", { id: entry.id }); } catch { /* skip */ } } })}>测试速度</button>
       </div>
     </header>
    {error && <div className="keys-error" role="alert"><span>{error}</span><button onClick={() => setError("")}>关闭</button></div>}
    {showForm && <form className="keys-form" onSubmit={save}><div className="keys-form-head"><h2>{editing === null ? "新建密钥" : "编辑密钥"}</h2><button type="button" onClick={wipeSensitiveState}>关闭</button></div><div className="keys-form-grid"><label>名称<input required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label><label>分组<select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value as KeyType })}><option value="secret">私密凭据</option><option value="llm">模型服务</option></select></label><label className="wide">密钥值<input required type="password" autoComplete="off" value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} /></label><label>服务地址<input value={draft.url} onChange={(e) => setDraft({ ...draft, url: e.target.value })} /></label><label>Anthropic 地址<input value={draft.url_anthropic} onChange={(e) => setDraft({ ...draft, url_anthropic: e.target.value })} /></label><label className="wide">备注<textarea value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.target.value })} /></label></div><button className="primary" disabled={busy}>{busy ? "保存中…" : "保存密钥"}</button></form>}
     <div className="keys-columns">{groups.map((meta) => { const group = entries.filter((entry) => entry.type === meta.type).sort((a, b) => a.order - b.order); return <section className="keys-group" key={meta.type}><div className="keys-group-title"><h2>{meta.title}</h2></div>{!loading && group.length === 0 ? <div className="keys-empty">暂无密钥</div> : <div className="keys-grid">{group.map((entry) => <article className="key-card" key={entry.id}><div className="key-card-top"><div><h3>{entry.name}</h3><p>{entry.type === "llm" ? `模型: ${entry.note || "-"}` : (entry.note || "")}</p><p>{entry.url ? `来源: ${entry.url}` : ""}</p></div><div className="key-actions"><button type="button" onClick={() => remove(entry)}>删除</button><button type="button" onClick={() => void startEdit(entry)}>编辑</button></div></div>{entry.type === "secret" ? <div className="key-secret"><code>{revealed[entry.id] ?? "••••••••••••••••"}</code><button onClick={() => void reveal(entry, true)}>复制</button></div> : null}<div className="key-actions">{entry.type === "llm" ? null : <button onClick={() => void reveal(entry)}>显示</button>}{entry.type === "secret" ? <button onClick={() => void startEdit(entry)}>编辑</button> : null}{entry.type === "secret" ? <button className="danger" onClick={() => remove(entry)}>删除</button> : null}</div></article>)}</div>}</section>; })}</div>
    {showMaster && <div className="keys-modal" role="presentation" onMouseDown={wipeSensitiveState}><div role="dialog" aria-modal="true" aria-labelledby="master-title" className="keys-popover" onMouseDown={(event) => event.stopPropagation()}><div className="keys-form-head"><h2 id="master-title">设置主密码</h2><button onClick={wipeSensitiveState}>关闭</button></div><p>新密钥库使用 scrypt 与 AES-256-GCM。</p><input autoFocus type="password" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && password) void authenticate(); }} placeholder="新主密码" autoComplete="new-password" /><button className="primary" disabled={!password || busy} onClick={() => void authenticate()}>{busy ? "加密中…" : "启用加密"}</button></div></div>}
  </section>;
}
