import { useI18n } from '../i18n';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { message, request, write } from '../api/client';
import type { CatalogueEntry, Session } from '../api/types';
import { EmptyState, ErrorNotice, Icon, Modal } from './Common';

export default function Catalogue({ session, navigate, branding, manage = false }: { session: Session; branding: string; navigate: (target: string) => void; manage?: boolean }) {
  const { t } = useI18n();
  const [items, setItems] = useState<CatalogueEntry[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [archived, setArchived] = useState(manage);
  const [search, setSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<CatalogueEntry | null>(null);
  const [lifecycle, setLifecycle] = useState<CatalogueEntry | null>(null);
  const canManage = manage && session.role === 'administrator';
  const load = useCallback(async () => {
    setBusy(true); setError('');
    try { setItems((await request<{ items: CatalogueEntry[] }>(`/projects?include_archived=${archived}`)).items); }
    catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }, [archived]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { document.title = `${branding} — ${manage ? t("Admin") : t("Systems")}`; }, [branding, manage, t]);
  const visible = items.filter((item) => `${item.name} ${item.description} ${item.project_id}`.toLowerCase().includes(search.toLowerCase()));
  return <main className="catalogue-page">
    <section className="page-heading"><div><p className="eyebrow">{manage ? t('APPLICATION ADMINISTRATION') : t('SYSTEM CATALOGUE')}</p><h1>{manage ? t("System administration") : t("Your systems, in context.")}</h1><p className="muted">{manage ? t("Create systems, edit their details and manage archived configurations.") : t("Choose a documented system. Each page opens its own independent workspace.")}</p></div>{canManage && <button className="primary" onClick={() => setCreating(true)}>{t("+ Create system")}</button>}</section>
    <section className="catalogue-controls" aria-label={t("Catalogue filters")}><label className="search-control"><span aria-hidden="true">⌕</span><input aria-label={t("Find a system")} placeholder={t("Find a system by name or identifier…")} value={search} onChange={(event) => setSearch(event.target.value)} /></label><label className="checkbox-label"><input type="checkbox" checked={archived} onChange={(event) => setArchived(event.target.checked)} />{t("Include archived systems")}</label><span className="muted">{t('Systems: {count}', { count: visible.length })}</span></section>
    {error && <ErrorNotice retry={() => { void load(); }}>{error}</ErrorNotice>}
    {busy ? <p role="status" className="loading">{t("Loading system catalogue…")}</p> : <div className="system-grid">{visible.map((item) => <article className="system-card" data-project-id={item.project_id} key={item.project_id}>
      <div className="system-card-top"><span className="system-emblem"><Icon /></span><span className="revision">{t("Revision ")}{item.revision}</span></div>
      <div className="system-card-body"><div className="card-title-row"><h2>{item.name}</h2>{item.archived && <span className="pill">{t("Archived")}</span>}</div><p className="system-description">{item.description || t("No description has been added.")}</p><code className="short-id" title={item.project_id}>{item.project_id}</code></div>
      <div className="system-card-meta"><span>{t("Topology & documentation")}</span><span>{t('Own live sessions: {count}', { count: item.own_live_sessions })}</span></div>
      <div className="system-card-actions"><a className="button primary" href={`/systems/${encodeURIComponent(item.project_id)}/topology`} onClick={(event) => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate(event.currentTarget.pathname); } }}>{t("Open system")}<Icon kind="arrow" /></a></div>
      {canManage && <div className="system-card-management"><button aria-label={t('Edit system details for {name}', { name: item.name })} disabled={item.archived} onClick={() => setEditing(item)}>{t("Edit system details")}</button><button aria-label={t(item.archived ? 'Restore system {name}' : 'Archive system {name}', { name: item.name })} onClick={() => setLifecycle(item)}>{item.archived ? t("Restore system") : t("Archive system")}</button></div>}
    </article>)}</div>}
    {!busy && !error && visible.length === 0 && <EmptyState title={items.length ? t("No matching systems") : t("No systems yet")}>{items.length ? t("Try another name or identifier.") : t("An Administrator can create a system from Admin. Synthetic demo data is loaded explicitly through the server setup command.")}</EmptyState>}
    {!manage && <aside className="workspace-explainer"><Icon /><div><h2>{t("One account. Independent windows.")}</h2><p>{t("Open another system, or the same system, in a separate tab. Selection, search and panel state stay in that page. Signing out and appearance changes are shared across your account.")}</p></div></aside>}
    {canManage && creating && <CreateSystem onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); navigate(`/systems/${encodeURIComponent(id)}/topology`); }} />}
    {canManage && editing && <EditSystem viewer={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void load(); }} />}
    {canManage && lifecycle && <Lifecycle viewer={lifecycle} onClose={() => setLifecycle(null)} onSaved={() => { setLifecycle(null); void load(); }} />}
  </main>;
}

function EditSystem({ viewer, onClose, onSaved }: { viewer: CatalogueEntry; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError(''); try { await write(`/projects/${encodeURIComponent(viewer.project_id)}/metadata`, { name: String(data.get('name')), description: String(data.get('description')), expected_revision: viewer.revision }, 'PATCH'); onSaved(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  return <Modal title={t("Edit system details")} onClose={onClose}><p className="target-system">{t("Target system: ")}<strong>{viewer.name}</strong><code>{viewer.project_id}</code></p>{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={event => { void submit(event); }}><label>{t("System name")}<input name="name" defaultValue={viewer.name} maxLength={256} required /></label><label>{t("Description")}<textarea name="description" defaultValue={viewer.description} maxLength={10000} rows={4} /></label><div className="form-actions"><button type="button" onClick={onClose}>{t("Cancel")}</button><button className="primary" disabled={busy}>{busy ? t("Saving…") : t("Save system details")}</button></div></form></Modal>;
}

function Lifecycle({ viewer, onClose, onSaved }: { viewer: CatalogueEntry; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const action = viewer.archived ? t('Restore system') : t('Archive system');
  async function apply() { setBusy(true); setError(''); try { await write(`/projects/${encodeURIComponent(viewer.project_id)}/${viewer.archived ? 'restore' : 'archive'}`, { expected_revision: viewer.revision }); onSaved(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  return <Modal title={action} onClose={onClose}><p className="target-system">{t("Target system: ")}<strong>{viewer.name}</strong><code>{viewer.project_id}</code></p><p>{viewer.archived ? t("Restore this system to the active catalogue. This does not start collection.") : t("Hide this system from the active catalogue and retain its configuration. No other system is changed.")}</p>{error && <ErrorNotice>{error}</ErrorNotice>}<div className="form-actions"><button onClick={onClose}>{t("Cancel")}</button><button className={viewer.archived ? 'primary' : 'danger-button'} disabled={busy} onClick={() => { void apply(); }}>{busy ? t("Saving…") : action}</button></div></Modal>;
}

function CreateSystem({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError('');
    try { const result = await write<{ project_id: string }>('/projects', { name: String(data.get('name')), description: String(data.get('description')) }); onCreated(result.project_id); }
    catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }
  return <Modal title={t("Create system")} onClose={onClose}><p className="muted">{t("Create an empty, named system configuration. This does not connect to a host.")}</p>{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={(event) => { void submit(event); }}><label>{t("System name")}<input name="name" required maxLength={256} autoFocus /></label><label>{t("Description")}<textarea name="description" maxLength={10000} rows={4} /></label><div className="form-actions"><button type="button" onClick={onClose}>{t("Cancel")}</button><button className="primary" disabled={busy}>{busy ? t("Creating…") : t("Create system")}</button></div></form></Modal>;
}
