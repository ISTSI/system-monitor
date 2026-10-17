import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { message, request, write } from '../api/client';
import type { CatalogueEntry, Session } from '../api/types';
import { EmptyState, ErrorNotice, Icon, Modal } from './Common';

export default function Catalogue({ session, navigate, branding, manage = false }: { session: Session; branding: string; navigate: (target: string) => void; manage?: boolean }) {
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
  useEffect(() => { document.title = `${branding} — ${manage ? 'Admin' : 'Systems'}`; }, [branding, manage]);
  const visible = items.filter((item) => `${item.name} ${item.description} ${item.project_id}`.toLowerCase().includes(search.toLowerCase()));
  return <main className="catalogue-page">
    <section className="page-heading"><div><p className="eyebrow">{manage ? 'APPLICATION ADMINISTRATION' : 'SYSTEM CATALOGUE'}</p><h1>{manage ? 'System administration' : 'Your systems, in context.'}</h1><p className="muted">{manage ? 'Create systems, edit their details and manage archived configurations.' : 'Choose a documented system. Each page opens its own independent workspace.'}</p></div>{canManage && <button className="primary" onClick={() => setCreating(true)}>+ Create system</button>}</section>
    <section className="catalogue-controls" aria-label="Catalogue filters"><label className="search-control"><span aria-hidden="true">⌕</span><input aria-label="Find a system" placeholder="Find a system by name or identifier…" value={search} onChange={(event) => setSearch(event.target.value)} /></label><label className="checkbox-label"><input type="checkbox" checked={archived} onChange={(event) => setArchived(event.target.checked)} />Include archived systems</label><span className="muted">{visible.length} {visible.length === 1 ? 'system' : 'systems'}</span></section>
    {error && <ErrorNotice retry={() => { void load(); }}>{error}</ErrorNotice>}
    {busy ? <p role="status" className="loading">Loading system catalogue…</p> : <div className="system-grid">{visible.map((item) => <article className="system-card" data-project-id={item.project_id} key={item.project_id}>
      <div className="system-card-top"><span className="system-emblem"><Icon /></span><span className="revision">Revision {item.revision}</span></div>
      <div className="system-card-body"><div className="card-title-row"><h2>{item.name}</h2>{item.archived && <span className="pill">Archived</span>}</div><p className="system-description">{item.description || 'No description has been added.'}</p><code className="short-id" title={item.project_id}>{item.project_id}</code></div>
      <div className="system-card-meta"><span>Topology & documentation</span><span>{item.own_live_sessions} own live sessions</span></div>
      <div className="system-card-actions"><a className="button primary" href={`/systems/${encodeURIComponent(item.project_id)}/topology`} onClick={(event) => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate(event.currentTarget.pathname); } }}>Open system<Icon kind="arrow" /></a></div>
      {canManage && <div className="system-card-management"><button aria-label={`Edit system details for ${item.name}`} disabled={item.archived} onClick={() => setEditing(item)}>Edit system details</button><button aria-label={`${item.archived ? 'Restore' : 'Archive'} system ${item.name}`} onClick={() => setLifecycle(item)}>{item.archived ? 'Restore system' : 'Archive system'}</button></div>}
    </article>)}</div>}
    {!busy && !error && visible.length === 0 && <EmptyState title={items.length ? 'No matching systems' : 'No systems yet'}>{items.length ? 'Try another name or identifier.' : 'An Administrator can create a system from Admin. Synthetic demo data is loaded explicitly through the server setup command.'}</EmptyState>}
    {!manage && <aside className="workspace-explainer"><Icon /><div><h2>One account. Independent windows.</h2><p>Open another system, or the same system, in a separate tab. Selection, search and panel state stay in that page. Signing out and appearance changes are shared across your account.</p></div></aside>}
    {canManage && creating && <CreateSystem onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); navigate(`/systems/${encodeURIComponent(id)}/topology`); }} />}
    {canManage && editing && <EditSystem viewer={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void load(); }} />}
    {canManage && lifecycle && <Lifecycle viewer={lifecycle} onClose={() => setLifecycle(null)} onSaved={() => { setLifecycle(null); void load(); }} />}
  </main>;
}

function EditSystem({ viewer, onClose, onSaved }: { viewer: CatalogueEntry; onClose: () => void; onSaved: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError(''); try { await write(`/projects/${encodeURIComponent(viewer.project_id)}/metadata`, { name: String(data.get('name')), description: String(data.get('description')), expected_revision: viewer.revision }, 'PATCH'); onSaved(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  return <Modal title="Edit system details" onClose={onClose}><p className="target-system">Target system: <strong>{viewer.name}</strong><code>{viewer.project_id}</code></p>{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={event => { void submit(event); }}><label>System name<input name="name" defaultValue={viewer.name} maxLength={256} required /></label><label>Description<textarea name="description" defaultValue={viewer.description} maxLength={10000} rows={4} /></label><div className="form-actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save system details'}</button></div></form></Modal>;
}

function Lifecycle({ viewer, onClose, onSaved }: { viewer: CatalogueEntry; onClose: () => void; onSaved: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const action = viewer.archived ? 'Restore' : 'Archive';
  async function apply() { setBusy(true); setError(''); try { await write(`/projects/${encodeURIComponent(viewer.project_id)}/${viewer.archived ? 'restore' : 'archive'}`, { expected_revision: viewer.revision }); onSaved(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  return <Modal title={`${action} system`} onClose={onClose}><p className="target-system">Target system: <strong>{viewer.name}</strong><code>{viewer.project_id}</code></p><p>{viewer.archived ? 'Restore this system to the active catalogue. This does not start collection.' : 'Hide this system from the active catalogue and retain its configuration. No other system is changed.'}</p>{error && <ErrorNotice>{error}</ErrorNotice>}<div className="form-actions"><button onClick={onClose}>Cancel</button><button className={viewer.archived ? 'primary' : 'danger-button'} disabled={busy} onClick={() => { void apply(); }}>{busy ? 'Saving…' : `${action} system`}</button></div></Modal>;
}

function CreateSystem({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError('');
    try { const result = await write<{ project_id: string }>('/projects', { name: String(data.get('name')), description: String(data.get('description')) }); onCreated(result.project_id); }
    catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }
  return <Modal title="Create system" onClose={onClose}><p className="muted">Create an empty, named system configuration. This does not connect to a host.</p>{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={(event) => { void submit(event); }}><label>System name<input name="name" required maxLength={256} autoFocus /></label><label>Description<textarea name="description" maxLength={10000} rows={4} /></label><div className="form-actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Creating…' : 'Create system'}</button></div></form></Modal>;
}
