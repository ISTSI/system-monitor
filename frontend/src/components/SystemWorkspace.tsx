import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { detachOnPageHide, message, request, write } from '../api/client';
import type { CatalogueEntry, Process, Session, Viewer, Workspace } from '../api/types';
import { EmptyState, ErrorNotice, Icon, Modal } from './Common';

export default function SystemWorkspace({ projectId, session, navigate, branding }: { projectId: string; session: Session; branding: string; navigate: (target: string) => void }) {
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [systems, setSystems] = useState<CatalogueEntry[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Process | null>(null);
  const [compact, setCompact] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [editing, setEditing] = useState(false);
  const [lifecycle, setLifecycle] = useState(false);
  const workspaceRef = useRef<Workspace | null>(null);
  const alive = useRef(true);
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const load = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const [project, catalogue] = await Promise.all([request<Viewer>(base), request<{ items: CatalogueEntry[] }>('/projects?include_archived=true')]);
      if (!alive.current) return;
      setViewer(project); setSystems(catalogue.items);
      if (!workspaceRef.current && !project.archived) {
        const created = await write<Workspace>(`${base}/workspaces`, { project_id: projectId });
        if (!alive.current) { void write(`${base}/workspaces/${encodeURIComponent(created.workspace_id)}/detach`).catch(() => {}); return; }
        workspaceRef.current = created; setWorkspace(created);
      }
    } catch (cause) { if (alive.current) setError(message(cause)); } finally { if (alive.current) setBusy(false); }
  }, [base, projectId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (viewer) document.title = `${branding} — ${viewer.name} — Topology`; }, [viewer, branding]);
  useEffect(() => {
    const detachPage = () => { const current = workspaceRef.current; if (current) detachOnPageHide(projectId, current.workspace_id); };
    const restorePage = (event: PageTransitionEvent) => { if (event.persisted) window.location.reload(); };
    window.addEventListener('pagehide', detachPage);
    window.addEventListener('pageshow', restorePage);
    const timer = window.setInterval(() => {
      const current = workspaceRef.current;
      if (current?.state === 'active') void request<Workspace>(`${base}/workspaces/${encodeURIComponent(current.workspace_id)}`).then((updated) => { workspaceRef.current = updated; setWorkspace(updated); }).catch((cause: unknown) => setError(message(cause)));
    }, 60000);
    return () => { alive.current = false; window.removeEventListener('pagehide', detachPage); window.removeEventListener('pageshow', restorePage); window.clearInterval(timer); const current = workspaceRef.current; if (current) void write(`${base}/workspaces/${encodeURIComponent(current.workspace_id)}/detach`).catch(() => { /* Server lease expiry handles an unavailable detach. */ }); };
  }, [base, projectId]);

  if (busy && !viewer) return <main className="workspace-loading"><p role="status">Opening independent workspace…</p></main>;
  if (!viewer) return <main className="catalogue-page"><ErrorNotice retry={() => { void load(); }}>{error || 'The system could not be opened.'}</ErrorNotice><a href="/" onClick={(event) => { event.preventDefault(); navigate('/'); }}>Back to systems</a></main>;
  const needle = search.toLowerCase();
  const matches = (process: Process) => `${process.name} ${process.description} ${process.id}`.toLowerCase().includes(needle);
  const matchCount = viewer.subsystems.reduce((sum, subsystem) => sum + subsystem.servers.reduce((total, server) => total + server.processes.filter(matches).length, 0), 0);
  return <main className="workspace-page"><div className="workspace-heading"><div><p className="eyebrow">SYSTEM WORKSPACE <code>{projectId}</code></p><h1>{viewer.name}</h1><p className="muted">{viewer.description}</p></div><div className="workspace-heading-controls"><label>System selector<select aria-label="System selector" value={projectId} onChange={(event) => navigate(`/systems/${encodeURIComponent(event.target.value)}/topology`)}>{systems.map((system) => <option key={system.project_id} value={system.project_id}>{system.name}{system.archived ? ' (archived)' : ''}</option>)}</select></label><a href={`/systems/${encodeURIComponent(projectId)}/topology`} target="_blank" rel="noopener noreferrer" className="button" aria-label="Open this system in a new tab">Open separately ↗</a></div></div>{error && <ErrorNotice retry={() => { void load(); }}>{error}</ErrorNotice>}<div className="workspace-toolbar"><div className="workspace-tabs"><span className="active">Topology</span><span title="Log collection arrives in a later stage" aria-disabled="true">Logs · later stage</span></div><span className="revision">Revision {viewer.revision}</span>{viewer.archived && <span className="pill">Archived · read-only</span>}{viewer.demo && <span className="demo-label">SYNTHETIC DEMO</span>}{session.role === 'administrator' && <div className="toolbar-end"><button onClick={() => setEditing(true)} disabled={viewer.archived}>Edit system details</button><button onClick={() => setLifecycle(true)}>{viewer.archived ? 'Restore system' : 'Archive system'}</button></div>}</div><div className="workspace-body"><aside className="explorer"><div className="panel-heading"><h2>System explorer</h2><span className="count-badge">{viewer.subsystems.length}</span></div><label className="explorer-search">Search this system<input aria-label="Search this system" placeholder="Process name or documentation…" value={search} onChange={(event) => setSearch(event.target.value)} /></label><p className="search-count" aria-live="polite">{matchCount} matching processes</p><div className="tree">{viewer.subsystems.map((subsystem) => <details key={subsystem.id} open><summary><Icon /><span>{subsystem.name}</span></summary>{subsystem.servers.map((server) => <details key={server.id} open><summary><Icon kind="server" /><span>{server.name}</span></summary>{server.processes.filter(matches).map((process) => <button className={selected?.id === process.id ? 'tree-process selected' : 'tree-process'} key={process.id} onClick={() => { setSelected(process); setDetailsOpen(true); }}><Icon kind="process" />{process.name}</button>)}</details>)}</details>)}</div><div className="explorer-footer"><span className="status-dot" />Page-local selection</div></aside><section className="topology-area"><div className="canvas-toolbar"><div><h2>Documented topology</h2><p>Health unknown · log access not checked</p></div><div className="view-controls"><button aria-pressed={compact} onClick={() => setCompact(!compact)}>Compact cards</button><button aria-pressed={detailsOpen} onClick={() => setDetailsOpen(!detailsOpen)}>{detailsOpen ? 'Hide details' : 'Show details'}</button></div></div><div className={compact ? 'topology-canvas compact' : 'topology-canvas'}>{viewer.subsystems.length ? viewer.subsystems.map((subsystem) => <section className="subsystem-card" key={subsystem.id}><header><Icon /><div><h3>{subsystem.name}</h3><p>{subsystem.description}</p></div><span className="pill">Documented</span></header><div className="server-grid">{subsystem.servers.map((server) => <section className="server-card" key={server.id}><header><Icon kind="server" /><h4>{server.name}</h4><span className="unknown-state">Unknown health</span></header><div className="process-list">{server.processes.filter(matches).map((process) => <button className={selected?.id === process.id ? 'process-card selected' : 'process-card'} aria-pressed={selected?.id === process.id} aria-label={`Select process ${process.name}`} key={process.id} onClick={() => { setSelected(process); setDetailsOpen(true); }}><Icon kind="process" /><span><strong>{process.name}</strong><small>{process.description || process.id}</small></span><span className="access-state">Not checked</span></button>)}{server.processes.filter(matches).length === 0 && <p className="small-empty">{server.processes.length ? 'No matching processes' : 'No configured processes'}</p>}</div></section>)}</div></section>) : <EmptyState title="Your system starts here">This empty system is saved in MariaDB. Topology editing and inventory import arrive in their implementation stages.</EmptyState>}</div>{detailsOpen && <section className="process-details" aria-label="Process details"><div className="panel-heading"><h2>{selected ? 'Process details' : 'Select a process'}</h2><span className="pill">{viewer.name}</span></div>{selected ? <div className="details-content"><div className="details-title"><Icon kind="process" /><div><h3>{selected.name}</h3><code>{selected.id}</code></div></div><dl><div><dt>Documentation</dt><dd className="documentation-text">{selected.description || 'No documentation supplied.'}</dd></div><div><dt>Process health</dt><dd>Unknown · no health probe</dd></div><div><dt>Log access</dt><dd>Not checked</dd></div>{selected.log_path && <div><dt>Documented log path</dt><dd><code>{selected.log_path}</code></dd></div>}</dl><div className="future-note"><Icon kind="process" /><p>Log investigation is a later stage. Selecting this process does not open an SSH connection.</p></div></div> : <p className="details-placeholder">Choose a process in the explorer or topology to read its documented properties.</p>}</section>}</section></div><div className="workspace-status"><span>Workspace <code data-testid="workspace-id">{workspace?.workspace_id ?? (viewer.archived ? 'archived view' : 'unavailable')}</code></span><span>{workspace?.state === 'active' ? 'Independent page · no collection started' : 'No active collection'}</span></div>{editing && <EditSystem viewer={viewer} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); void load(); }} />}{lifecycle && <Lifecycle viewer={viewer} onClose={() => setLifecycle(false)} onSaved={() => { setLifecycle(false); navigate('/'); }} />}</main>;
}

function EditSystem({ viewer, onClose, onSaved }: { viewer: Viewer; onClose: () => void; onSaved: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError(''); try { await write(`/projects/${encodeURIComponent(viewer.project_id)}/metadata`, { name: String(data.get('name')), description: String(data.get('description')), expected_revision: viewer.revision }, 'PATCH'); onSaved(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  return <Modal title="Edit system details" onClose={onClose}><p className="target-system">Target system: <strong>{viewer.name}</strong><code>{viewer.project_id}</code></p>{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={(event) => { void submit(event); }}><label>System name<input name="name" defaultValue={viewer.name} maxLength={256} required /></label><label>Description<textarea name="description" defaultValue={viewer.description} maxLength={10000} rows={4} /></label><div className="form-actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save system details'}</button></div></form></Modal>;
}

function Lifecycle({ viewer, onClose, onSaved }: { viewer: Viewer; onClose: () => void; onSaved: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const action = viewer.archived ? 'Restore' : 'Archive';
  async function apply() { setBusy(true); setError(''); try { await write(`/projects/${encodeURIComponent(viewer.project_id)}/${viewer.archived ? 'restore' : 'archive'}`, { expected_revision: viewer.revision }); onSaved(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  return <Modal title={`${action} system`} onClose={onClose}><p className="target-system">Target system: <strong>{viewer.name}</strong><code>{viewer.project_id}</code></p><p>{viewer.archived ? 'Restore this system to the active catalogue. This does not start collection.' : 'Hide this system from the active catalogue and retain its configuration. No other system is changed.'}</p>{error && <ErrorNotice>{error}</ErrorNotice>}<div className="form-actions"><button onClick={onClose}>Cancel</button><button className={viewer.archived ? 'primary' : 'danger-button'} disabled={busy} onClick={() => { void apply(); }}>{busy ? 'Saving…' : `${action} system`}</button></div></Modal>;
}
