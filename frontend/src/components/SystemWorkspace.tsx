import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { detachOnPageHide, message, request, write } from '../api/client';
import type { CatalogueEntry, Session, Viewer, Workspace } from '../api/types';
import { ancestors, defaultGeometry, entity, entityList, parentId, withEntity, type Config, type Connection, type DeleteImpact, type EditEntity, type EntityKind, type Flow, type Geometry, type Process, type SearchResult, type Selection, type Server, type Topology } from '../topology';
import { EmptyState, ErrorNotice, Icon, Modal } from './Common';
import TopologyGraph from './TopologyGraph';
import TopologyEditor, { MoveDialog } from './TopologyEditor';
import ConfigImport, { exportConfig } from './ConfigTransfer';
import SafeMarkdown from './SafeMarkdown';
import HistoricalViewer from './HistoricalViewer';
import ConnectionAccess from './ConnectionAccess';

type Editor = { kind: EntityKind; item?: EditEntity; defaults?: Partial<Flow> };

export default function SystemWorkspace({ projectId, session, navigate, branding, section = 'topology', investigationId }: { projectId: string; session: Session; branding: string; navigate: (target: string) => void; section?: 'topology' | 'logs'; investigationId?: string }) {
  const [topology, setTopology] = useState<Topology | null>(null); const [viewer, setViewer] = useState<Viewer | null>(null);
  const [systems, setSystems] = useState<CatalogueEntry[]>([]); const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(true); const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState(''); const [results, setResults] = useState<SearchResult[]>([]); const [searchBusy, setSearchBusy] = useState(false);
  const [selection, setSelection] = useState<Selection | null>(null); const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [viewId, setViewId] = useState(''); const [personalCollapsed, setPersonalCollapsed] = useState<Record<string, boolean>>({}); const [reveal, setReveal] = useState(0);
  const [detailsOpen, setDetailsOpen] = useState(true); const [explorerOpen, setExplorerOpen] = useState(true);
  const [editing, setEditing] = useState(false); const [lifecycle, setLifecycle] = useState(false); const [editor, setEditor] = useState<Editor | null>(null);
  const [accessConnectionId, setAccessConnectionId] = useState('');
  const [manager, setManager] = useState<'connection' | 'parser' | null>(null); const [importing, setImporting] = useState(false);
  const [moving, setMoving] = useState<{ kind: 'server' | 'process'; id: string } | null>(null);
  const [deleting, setDeleting] = useState<{ selection: Selection; impact: DeleteImpact } | null>(null);
  const [dependency, setDependency] = useState<'upstream' | 'downstream' | ''>('');
  const [historySelection, setHistorySelection] = useState<{ ids: string[]; version: number }>({ ids: [], version: 0 });
  const [collecting, setCollecting] = useState(false); const [switchTarget, setSwitchTarget] = useState('');
  const workspaceRef = useRef<Workspace | null>(null); const alive = useRef(true);
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const load = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const [project, model, catalogue] = await Promise.all([request<Viewer>(base), request<Topology>(`${base}/topology`), request<{ items: CatalogueEntry[] }>('/projects?include_archived=true')]);
      if (!alive.current) return;
      setViewer(project); setTopology(model); setSystems(catalogue.items);
      setViewId(current => model.config.views.some(view => view.id === current) ? current : model.config.views[0]?.id ?? '');
      if (!workspaceRef.current && !project.archived) {
        const created = await write<Workspace>(`${base}/workspaces`, { project_id: projectId });
        if (!alive.current) { void write(`${base}/workspaces/${encodeURIComponent(created.workspace_id)}/detach`).catch(() => {}); return; }
        workspaceRef.current = created; setWorkspace(created);
      }
    } catch (cause) { if (alive.current) setError(message(cause)); } finally { if (alive.current) setBusy(false); }
  }, [base, projectId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (topology) document.title = `${branding} — ${topology.config.project.name} — ${section === 'logs' ? 'Historical investigation' : 'Topology'}`; }, [topology, branding, section]);
  useEffect(() => {
    const detachPage = () => { const current = workspaceRef.current; if (current) detachOnPageHide(projectId, current.workspace_id); };
    const restorePage = (event: PageTransitionEvent) => { if (event.persisted) window.location.reload(); };
    window.addEventListener('pagehide', detachPage); window.addEventListener('pageshow', restorePage);
    const timer = window.setInterval(() => {
      const current = workspaceRef.current;
      if (current?.state === 'active') void request<Workspace>(`${base}/workspaces/${encodeURIComponent(current.workspace_id)}`).then(updated => { if (alive.current) { workspaceRef.current = updated; setWorkspace(updated); } }).catch((cause: unknown) => { if (alive.current) setError(message(cause)); });
    }, 60000);
    return () => { alive.current = false; window.removeEventListener('pagehide', detachPage); window.removeEventListener('pageshow', restorePage); window.clearInterval(timer); const current = workspaceRef.current; if (current) void write(`${base}/workspaces/${encodeURIComponent(current.workspace_id)}/detach`).catch(() => {}); };
  }, [base, projectId]);
  useEffect(() => {
    if (!search.trim()) { setResults([]); setSearchBusy(false); return; }
    let active = true; setSearchBusy(true);
    const timer = window.setTimeout(() => { void write<{ results: SearchResult[] }>(`${base}/search`, { q: search }).then(value => { if (active) setResults(value.results); }).catch((cause: unknown) => { if (active) setError(message(cause)); }).finally(() => { if (active) setSearchBusy(false); }); }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [base, search, topology?.revision]);
  const config = topology?.config;
  const personalView = viewId === '__search_reveal__';
  const currentView = useMemo(() => config && personalView ? { id: '__search_reveal__', name: 'Search reveal (personal)', nodes: defaultGeometry(config), flow_ids: config.flows.map(flow => flow.id) } : config?.views.find(view => view.id === viewId) ?? config?.views[0], [config, personalView, viewId]);
  const displayedView = useMemo(() => currentView ? { ...currentView, nodes: currentView.nodes.map(node => ({ ...node, collapsed: personalCollapsed[`${currentView.id}:${node.element_id}`] ?? node.collapsed })) } : undefined, [currentView, personalCollapsed]);
  const editable = !!topology?.editable && session.role === 'administrator' && !topology.archived;
  const selected = config ? entity(config, selection) : undefined;
  const selectedConnection = session.role === 'administrator' ? selection?.kind === 'server' ? config?.connections?.find(item => item.id === (selected as Server | undefined)?.connection_id) : selection?.kind === 'connection' ? selected as Connection | undefined : undefined : undefined;
  const accessConnection = config?.connections?.find(item => item.id === accessConnectionId);
  const selectedProcesses = useMemo(() => config?.processes.filter(process => selectedIds.includes(process.id)) ?? [], [config, selectedIds]);
  const highlighted = useMemo(() => {
    const ids = new Set<string>(); if (!config || !dependency) return ids;
    selectedProcesses.forEach(process => ids.add(process.id)); let changed = true;
    while (changed) { changed = false; for (const flow of config.flows) {
      const from = dependency === 'downstream' ? flow.source_process_id : flow.target_process_id;
      const to = dependency === 'downstream' ? flow.target_process_id : flow.source_process_id;
      if (ids.has(from) && !ids.has(to)) { ids.add(to); changed = true; }
    } }
    return ids;
  }, [config, dependency, selectedProcesses]);
  const select = useCallback((value: Selection, additive = false) => {
    setSelection(current => current?.kind === value.kind && current.id === value.id ? current : value); setDetailsOpen(true);
    if (['subsystem', 'server', 'process'].includes(value.kind)) setSelectedIds(current => {
      const next = additive ? current.includes(value.id) ? current : [...current, value.id] : [value.id];
      return next.length === current.length && next.every((id, index) => id === current[index]) ? current : next;
    });
  }, []);
  const multiSelect = useCallback((ids: string[]) => { setSelectedIds(current => current.length === ids.length && current.every(id => ids.includes(id)) ? current : ids); }, []);
  const commit = useCallback(async (next: Config, flags: { confirmed_deletions?: boolean; reparent?: boolean } = {}) => {
    if (!topology || !editable || saving) throw new Error('Shared configuration is not currently editable.');
    setSaving(true); setError('');
    try {
      const saved = await write<Topology>(`${base}/topology`, { expected_revision: topology.revision, config: next, ...flags }, 'PUT');
      if (alive.current) { setTopology(saved); setViewId(current => saved.config.views.some(view => view.id === current) ? current : saved.config.views[0]?.id ?? ''); }
    } finally { if (alive.current) setSaving(false); }
  }, [base, topology, editable, saving]);
  const geometry = useCallback((id: string, values: Partial<Geometry>, moved: { id: string; position: { x: number; y: number } }[] = []) => {
    if (!config || !currentView || !editable || saving || personalView) return;
    const next = structuredClone(config); const view = next.views.find(view => view.id === currentView.id);
    const node = view?.nodes.find(node => node.element_id === id);
    if (node && view) {
      Object.assign(node, values);
      for (const item of moved) { const other = view.nodes.find(node => node.element_id === item.id); if (other) Object.assign(other, item.position); }
      for (const changed of [node, ...moved.map(item => view.nodes.find(node => node.element_id === item.id)!).filter(Boolean)]) {
        if (parentId(next, changed.element_id)) { changed.x = Math.max(10, changed.x); changed.y = Math.max(50, changed.y); }
        for (const ancestor of ancestors(next, changed.element_id).reverse()) {
          const group = view.nodes.find(node => node.element_id === ancestor)!;
          const children = view.nodes.filter(node => parentId(next, node.element_id) === ancestor);
          group.width = Math.max(group.width, ...children.map(node => node.x + node.width + 15));
          group.height = Math.max(group.height, ...children.map(node => node.y + node.height + 15));
        }
      }
      void commit(next).catch((cause: unknown) => setError(message(cause)));
    }
  }, [config, currentView, editable, saving, personalView, commit]);
  const collapse = useCallback((id: string) => {
    if (!config || !displayedView) return;
    const node = displayedView.nodes.find(node => node.element_id === id); if (!node) return;
    if (editable && !personalView) {
      const next = structuredClone(config); next.views.find(view => view.id === displayedView.id)!.nodes.find(node => node.element_id === id)!.collapsed = !node.collapsed;
      setPersonalCollapsed(current => { const next = { ...current }; delete next[`${displayedView.id}:${id}`]; return next; });
      void commit(next).catch((cause: unknown) => setError(message(cause)));
    } else setPersonalCollapsed(current => ({ ...current, [`${displayedView.id}:${id}`]: !node.collapsed }));
  }, [config, displayedView, editable, personalView, commit]);
  const connect = useCallback((source: string, target: string) => { setEditor({ kind: 'flow', defaults: { source_process_id: source, target_process_id: target } }); }, []);
  async function history(action: 'undo' | 'redo') {
    if (!topology) return; setSaving(true); setError('');
    try { const saved = await write<Topology>(`${base}/topology/${action}`, { expected_revision: topology.revision }); setTopology(saved); setViewId(current => saved.config.views.some(view => view.id === current) ? current : saved.config.views[0]?.id ?? ''); } catch (cause) { setError(message(cause)); } finally { setSaving(false); }
  }
  async function previewDelete(value: Selection) {
    setError(''); try { setDeleting({ selection: value, impact: await write<DeleteImpact>(`${base}/topology/delete-preview`, value) }); } catch (cause) { setError(message(cause)); }
  }
  async function deleteSelected() {
    if (!config || !deleting) return;
    const next = structuredClone(config); const remove = new Set(deleting.impact.entities.map(item => item.id)); const flows = new Set([...deleting.impact.flows, ...remove]);
    next.subsystems = next.subsystems.filter(item => !remove.has(item.id)); next.servers = next.servers.filter(item => !remove.has(item.id)); next.processes = next.processes.filter(item => !remove.has(item.id));
    next.connections = next.connections?.filter(item => !remove.has(item.id)); next.parsers = next.parsers?.filter(item => !remove.has(item.id)); next.flows = next.flows.filter(item => !flows.has(item.id));
    next.views = next.views.filter(item => !remove.has(item.id)).map(view => ({ ...view, nodes: view.nodes.filter(node => !remove.has(node.element_id)), flow_ids: view.flow_ids.filter(id => !flows.has(id)) }));
    await commit(next, { confirmed_deletions: true }); setDeleting(null); setSelection(null); setSelectedIds([]);
  }
  async function move(parent: string) {
    if (!config || !moving) return;
    const next = structuredClone(config);
    if (moving.kind === 'server') next.servers.find(item => item.id === moving.id)!.subsystem_id = parent;
    else next.processes.find(item => item.id === moving.id)!.server_id = parent;
    const defaultNodes = defaultGeometry(next);
    for (const view of next.views) if (view.nodes.some(node => node.element_id === moving.id)) {
      for (const id of ancestors(next, moving.id)) if (!view.nodes.some(node => node.element_id === id)) view.nodes.push(defaultNodes.find(node => node.element_id === id)!);
      const moved = view.nodes.find(node => node.element_id === moving.id)!; moved.x = 20;
      moved.y = Math.max(60, ...view.nodes.filter(node => node.element_id !== moving.id && parentId(next, node.element_id) === parent).map(node => node.y + node.height + 20));
      for (const id of ancestors(next, moving.id).reverse()) {
        const geometry = view.nodes.find(node => node.element_id === id)!; geometry.collapsed = false; const children = view.nodes.filter(node => parentId(next, node.element_id) === id);
        geometry.width = Math.max(geometry.width, ...children.map(node => node.x + node.width + 20)); geometry.height = Math.max(geometry.height, ...children.map(node => node.y + node.height + 20));
      }
    }
    await commit(next, { reparent: true });
  }
  function inspectHistory(ids: string[]) {
    setHistorySelection(current => ({ ids, version: current.version + 1 }));
    navigate(`/systems/${encodeURIComponent(projectId)}/logs`);
  }
  function switchSystem(target: string) {
    if (collecting) setSwitchTarget(target);
    else navigate(target);
  }
  function revealResult(result: SearchResult) {
    if (!config) return;
    const contains = (view: NonNullable<typeof currentView>) => view.nodes.some(node => node.element_id === result.id) || view.flow_ids.includes(result.id);
    const view = config.views.find(view => view.id === result.view_id && contains(view)) ?? config.views.find(contains);
    const revealViewId = view?.id ?? '__search_reveal__';
    const flow = result.kind === 'flow' ? config.flows.find(flow => flow.id === result.id) : undefined;
    const targets = flow ? [flow.source_process_id, flow.target_process_id] : [result.id];
    setViewId(revealViewId); setPersonalCollapsed(current => ({ ...current, ...Object.fromEntries(targets.flatMap(id => ancestors(config, id)).map(id => [`${revealViewId}:${id}`, false])) }));
    select(result); setReveal(current => current + 1);
  }

  if (busy && !topology) return <main className="workspace-loading"><p role="status">Opening independent workspace…</p></main>;
  if (!topology || !config || !viewer) return <main className="catalogue-page"><ErrorNotice retry={() => { void load(); }}>{error || 'The system could not be opened.'}</ErrorNotice><a href="/" onClick={event => { event.preventDefault(); navigate('/'); }}>Back to systems</a></main>;
  const metadata = { ...viewer, name: config.project.name, description: config.project.description, revision: topology.revision, archived: topology.archived };
  return <main className="workspace-page">
    <div className="workspace-heading"><div><p className="eyebrow">SYSTEM WORKSPACE <code>{projectId}</code></p><h1>{config.project.name}</h1><p className="muted">{config.project.description}</p></div><div className="workspace-heading-controls"><label>System selector<select aria-label="System selector" value={projectId} onChange={event => switchSystem(`/systems/${encodeURIComponent(event.target.value)}/${section}`)}>{systems.map(system => <option key={system.project_id} value={system.project_id}>{system.name}{system.archived ? ' (archived)' : ''}</option>)}</select></label><a href={`/systems/${encodeURIComponent(projectId)}/${section}`} target="_blank" rel="noopener noreferrer" className="button" aria-label="Open this system in a new tab">Open separately ↗</a></div></div>
    {error && <ErrorNotice retry={() => { void load(); }}>{error}</ErrorNotice>}
    <div className="workspace-toolbar"><nav className="workspace-tabs" aria-label="System section"><a className={section === 'topology' ? 'active' : ''} href={`/systems/${encodeURIComponent(projectId)}/topology`} onClick={event => { if (!event.ctrlKey && !event.metaKey) { event.preventDefault(); navigate(`/systems/${encodeURIComponent(projectId)}/topology`); } }}>Topology</a><a className={section === 'logs' ? 'active' : ''} href={`/systems/${encodeURIComponent(projectId)}/logs`} onClick={event => { if (!event.ctrlKey && !event.metaKey) { event.preventDefault(); navigate(`/systems/${encodeURIComponent(projectId)}/logs`); } }}>Log history</a></nav><span className="revision">Revision {topology.revision}</span><span className="save-state" role="status">{saving ? 'Saving…' : editable ? 'Saved to server' : 'Read-only shared configuration'}</span>{topology.archived && <span className="pill">Archived · read-only</span>}{viewer.demo && <span className="demo-label">SYNTHETIC DEMO</span>}{session.role === 'administrator' && <div className="toolbar-end"><button onClick={() => setEditing(true)} disabled={!editable}>Edit system details</button><button onClick={() => setLifecycle(true)}>{topology.archived ? 'Restore system' : 'Archive system'}</button></div>}</div>
    <div hidden={section !== 'topology'}>
    {editable && <div className="topology-edit-toolbar" aria-label="Shared topology editing"><button onClick={() => setEditor({ kind: 'subsystem' })} disabled={saving}>Add subsystem</button><button onClick={() => setEditor({ kind: 'server' })} disabled={saving || !config.subsystems.length}>Add server</button><button onClick={() => setEditor({ kind: 'process' })} disabled={saving || !config.servers.length || !config.parsers?.length}>Add process</button><button onClick={() => setEditor({ kind: 'flow' })} disabled={saving || config.processes.length < 2}>Add flow</button><span className="toolbar-divider" /><button onClick={() => setManager('connection')}>Connections</button><button onClick={() => setManager('parser')}>Parsers</button><span className="toolbar-divider" /><button onClick={() => { void history('undo'); }} disabled={saving || topology.can_undo === false}>Undo</button><button onClick={() => { void history('redo'); }} disabled={saving || topology.can_redo === false}>Redo</button><div className="config-actions"><button onClick={() => setImporting(true)}>Import configuration</button><button onClick={() => { void exportConfig(projectId, 'json').catch((cause: unknown) => setError(message(cause))); }}>Export JSON</button><button onClick={() => { void exportConfig(projectId, 'yaml').catch((cause: unknown) => setError(message(cause))); }}>Export YAML</button></div></div>}
    <div className={`workspace-body ${!explorerOpen ? 'explorer-hidden' : ''}`}>
      {explorerOpen && <aside className="explorer"><div className="panel-heading"><h2>System explorer</h2><span className="count-badge">{config.subsystems.length}</span></div><label className="explorer-search">Search this system<input aria-label="Search this system" placeholder="Name, PCS, tags, documentation…" value={search} maxLength={256} onChange={event => setSearch(event.target.value)} /></label>{search.trim() ? <div className="search-results"><p className="search-count" aria-live="polite">{searchBusy ? 'Searching…' : `${results.length} results in this system`}</p>{results.map(result => <button key={`${result.kind}:${result.id}`} onClick={() => revealResult(result)}><strong>{result.name}</strong><small>{result.kind}</small></button>)}</div> : <p className="search-count">{config.processes.length} configured processes</p>}<div className="tree">{config.subsystems.map(subsystem => <details key={subsystem.id} open><summary><Icon /><button className="tree-label" onClick={() => { select({ kind: 'subsystem', id: subsystem.id }); setReveal(current => current + 1); }}>{subsystem.name}</button></summary>{config.servers.filter(server => server.subsystem_id === subsystem.id).map(server => <details key={server.id} open><summary><Icon kind="server" /><button className="tree-label" onClick={() => { select({ kind: 'server', id: server.id }); setReveal(current => current + 1); }}>{server.name}</button></summary>{config.processes.filter(process => process.server_id === server.id).map(process => <button className={selectedIds.includes(process.id) ? 'tree-process selected' : 'tree-process'} key={process.id} onClick={() => revealResult({ kind: 'process', id: process.id, name: process.name, view_id: currentView?.id ?? null })}><Icon kind="process" />{process.name}</button>)}</details>)}</details>)}</div><div className="explorer-footer"><span className="status-dot" />Page-local selection · {selectedProcesses.length} processes</div></aside>}
      <section className="topology-area"><div className="canvas-toolbar"><div><h2>Documented topology</h2><p>Health unknown · log access not checked</p></div><div className="view-controls"><button aria-pressed={explorerOpen} onClick={() => setExplorerOpen(!explorerOpen)}>{explorerOpen ? 'Hide explorer' : 'Show explorer'}</button>{config.views.length > 0 && <select aria-label="Named view" value={currentView?.id ?? ''} onChange={event => { setViewId(event.target.value); setPersonalCollapsed({}); }}>{personalView && <option value="__search_reveal__">Search reveal (personal)</option>}{config.views.map(view => <option key={view.id} value={view.id}>{view.name}</option>)}</select>}{editable && <><button onClick={() => setEditor({ kind: 'view' })}>Add view</button>{currentView && !personalView && <><button onClick={() => setEditor({ kind: 'view', item: currentView })}>Edit view</button><button onClick={() => { void previewDelete({ kind: 'view', id: currentView.id }); }}>Delete view</button></>}</>}<button aria-pressed={detailsOpen} onClick={() => setDetailsOpen(!detailsOpen)}>{detailsOpen ? 'Hide details' : 'Show details'}</button></div></div>
        {displayedView ? <TopologyGraph config={config} view={displayedView} editable={editable && !personalView} selection={selection} selectedIds={selectedIds} highlighted={highlighted} reveal={reveal} saving={saving} onSelect={select} onMultiSelect={multiSelect} onGeometry={geometry} onCollapse={collapse} onConnect={connect} /> : <EmptyState title={config.subsystems.length ? 'Create a named view' : 'Your system starts here'}>{editable ? 'Add a subsystem, connection, server, parser and process; then create a view to arrange your topology.' : 'No named topology view is configured.'}</EmptyState>}
        {selectedProcesses.length > 0 && <div className="dependency-toolbar"><span>{selectedProcesses.length} processes selected</span><button className="primary" onClick={() => inspectHistory(selectedProcesses.map(process => process.id))}>{selectedProcesses.length > 1 ? 'Inspect selected history' : 'Inspect history'}</button><button aria-pressed={dependency === 'upstream'} onClick={() => setDependency(dependency === 'upstream' ? '' : 'upstream')}>Highlight upstream</button><button aria-pressed={dependency === 'downstream'} onClick={() => setDependency(dependency === 'downstream' ? '' : 'downstream')}>Highlight downstream</button><button disabled={!highlighted.size} onClick={() => setSelectedIds(current => [...new Set([...current, ...highlighted])])}>Add highlighted neighbours</button><small>Possible transfers, not observed causality</small></div>}
        {detailsOpen && <section className="process-details" aria-label="Process details"><div className="panel-heading"><h2>{selected ? `${selection?.kind === 'process' ? 'Process' : 'Element'} details` : 'Select a process'}</h2><span className="pill">{config.project.name}</span></div>{selected && selection ? <div className="details-content"><div className="details-title"><Icon kind={selection.kind === 'server' ? 'server' : selection.kind === 'process' ? 'process' : 'system'} /><div><h3>{selected.name}</h3><code>{selected.id}</code></div><span className="pill">{selection.kind}</span>{editable && <div className="selection-actions"><button onClick={() => setEditor({ kind: selection.kind, item: selected })}>Edit selected</button>{(selection.kind === 'process' || selection.kind === 'server') && <button onClick={() => setMoving({ kind: selection.kind as 'server' | 'process', id: selection.id })}>Move to {selection.kind === 'process' ? 'server' : 'subsystem'}</button>}<button onClick={() => { void previewDelete(selection); }}>Delete selected</button></div>}</div>{'description' in selected && <SafeMarkdown text={selected.description} />}{'tags' in selected && selected.tags.length > 0 && <div className="tag-list">{selected.tags.map(tag => <span className="pill" key={tag}>{tag}</span>)}</div>}<dl>{selection.kind === 'process' && <><div><dt>Process health</dt><dd>Unknown · no health probe</dd></div><div><dt>Log access</dt><dd>Not checked</dd></div>{(selected as Process).pcs_resource_name && <div><dt>PCS resource name</dt><dd>{(selected as Process).pcs_resource_name}</dd></div>}{(selected as Process).log_source && <><div><dt>Documented log path</dt><dd><code>{(selected as Process).log_source?.active_path}</code></dd></div><div><dt>Parser / encoding</dt><dd>{(selected as Process).log_source?.parser_id} · {(selected as Process).log_source?.encoding}</dd></div></>}</>}{selection.kind === 'server' && <div><dt>Subsystem</dt><dd>{config.subsystems.find(item => item.id === (selected as Server).subsystem_id)?.name}</dd></div>}{selectedConnection && <><div><dt>SSH profile</dt><dd>{selectedConnection.name}</dd></div><div><dt>SSH host</dt><dd><code>{selectedConnection.host}</code></dd></div><div><dt>SSH port</dt><dd>{selectedConnection.port}</dd></div>{editable && <div><dt>Connection settings</dt><dd><button onClick={() => setEditor({ kind: 'connection', item: selectedConnection })}>Edit SSH connection</button><button onClick={() => setAccessConnectionId(selectedConnection.id)}>Password &amp; connection test</button></dd></div>}</>}{selection.kind === 'flow' && <><div><dt>Source → target</dt><dd>{config.processes.find(item => item.id === (selected as Flow).source_process_id)?.name} → {config.processes.find(item => item.id === (selected as Flow).target_process_id)?.name}</dd></div><div><dt>Protocol</dt><dd>{(selected as Flow).protocol || 'Unspecified'}</dd></div></>}</dl>{selection.kind === 'process' && <><div className="related-flows"><strong>Related flows</strong>{config.flows.filter(flow => [flow.source_process_id, flow.target_process_id].includes(selection.id)).map(flow => <button key={flow.id} onClick={() => select({ kind: 'flow', id: flow.id })}>{flow.name} →</button>)}</div><div className="history-entry"><button className="primary" onClick={() => inspectHistory([selection.id])}>Inspect this process history</button><p className="muted">Preview configured local sources before collection. Selecting a process starts no connection.</p></div></>}</div> : <p className="details-placeholder">Choose an element or flow in the explorer or diagram to read its documentation and properties.</p>}</section>}
      </section>
    </div></div><div hidden={section !== 'logs'}><HistoricalViewer projectId={projectId} config={config} workspaceId={workspace?.workspace_id} selection={historySelection} archived={topology.archived} investigationId={investigationId} onOpen={id => navigate(`/systems/${encodeURIComponent(projectId)}/investigations/${encodeURIComponent(id)}`)} onCaptureChange={setCollecting} /></div><div className="workspace-status"><span>Workspace <code data-testid="workspace-id">{workspace?.workspace_id ?? (topology.archived ? 'archived view' : 'unavailable')}</code></span><span>{collecting ? 'Historical collection running for this page' : workspace?.state === 'active' ? 'Independent page workspace' : 'No active collection'}</span></div>
    {switchTarget && <Modal title="Switch system while collecting" onClose={() => setSwitchTarget('')}><p>The historical collection for <strong>{config.project.name}</strong> continues on the server. Its retained results remain available in this system. The new system opens an independent workspace; other pages keep their controls.</p><div className="form-actions"><button onClick={() => setSwitchTarget('')}>Stay in this system</button><button className="primary" onClick={() => { const target = switchTarget; setSwitchTarget(''); navigate(target); }}>Continue collection and switch</button></div></Modal>}
    {editing && <EditSystem viewer={metadata} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); void load(); }} />}{lifecycle && <Lifecycle viewer={metadata} onClose={() => setLifecycle(false)} onSaved={() => { setLifecycle(false); navigate('/'); }} />}
    {editor && <TopologyEditor key={`${editor.kind}:${editor.item?.id ?? 'new'}`} {...editor} config={config} currentView={currentView} onClose={() => setEditor(null)} onSave={async (kind, value, connection) => { const next = connection ? withEntity(config, 'connection', connection) : config; await commit(withEntity(next, kind, value)); if (kind === 'view') setViewId(value.id); else select({ kind, id: value.id }); }} />}
    {manager && <Modal title={manager === 'connection' ? 'Connection profiles' : 'Parser profiles'} onClose={() => setManager(null)}><p className="target-system">Target system: <strong>{config.project.name}</strong><code>{projectId}</code></p><button className="primary" onClick={() => { setEditor({ kind: manager }); setManager(null); }}>Add {manager}</button><div className="profile-list">{entityList(config, manager).map(item => <div key={item.id}><span><strong>{item.name}</strong><code>{item.id}</code></span><button aria-label={`Edit ${manager} ${item.name}`} onClick={() => { setEditor({ kind: manager, item }); setManager(null); }}>Edit</button>{manager === 'connection' && <button aria-label={`Password and test ${item.name}`} onClick={() => { setAccessConnectionId(item.id); setManager(null); }}>Password &amp; test</button>}<button aria-label={`Delete ${manager} ${item.name}`} onClick={() => { void previewDelete({ kind: manager, id: item.id }); setManager(null); }}>Delete</button></div>)}</div></Modal>}
    {accessConnection && session.role === 'administrator' && <ConnectionAccess key={accessConnection.id} config={config} connection={accessConnection} onClose={() => setAccessConnectionId('')} onJump={setAccessConnectionId} />}
    {moving && <MoveDialog config={config} selection={moving} onClose={() => setMoving(null)} onMove={move} />}
    {deleting && <DeleteDialog impact={deleting.impact} kind={deleting.selection.kind} name={entity(config, deleting.selection)?.name ?? deleting.selection.id} onClose={() => setDeleting(null)} onConfirm={deleteSelected} />}
    {importing && <ConfigImport config={config} revision={topology.revision} onClose={() => setImporting(false)} onCommitted={load} />}
  </main>;
}

function DeleteDialog({ impact, name, kind, onClose, onConfirm }: { impact: DeleteImpact; name: string; kind: EntityKind; onClose: () => void; onConfirm: () => Promise<void> }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function confirm() { setBusy(true); setError(''); try { await onConfirm(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  return <Modal title="Delete impact preview" onClose={onClose}><p>Delete {kind} <strong>{name}</strong> with the following impact:</p>{error && <ErrorNotice>{error}</ErrorNotice>}<ul>{impact.entities.map(item => <li key={`${item.kind}:${item.id}`}>{item.kind}: {item.name} <code>{item.id}</code></li>)}</ul><dl><div><dt>Removed flows</dt><dd>{impact.flows.length}</dd></div><div><dt>Affected views</dt><dd>{impact.views.length}</dd></div><div><dt>Saved investigations</dt><dd>{impact.investigations.length}</dd></div><div><dt>Active sessions</dt><dd>{impact.active_sessions.length}</dd></div></dl><p className="muted">Historical identities and name snapshots are preserved.</p><div className="form-actions"><button onClick={onClose}>Cancel</button><button className="danger-button" disabled={busy} onClick={() => { void confirm(); }}>{busy ? 'Deleting…' : 'Confirm deletion'}</button></div></Modal>;
}

function EditSystem({ viewer, onClose, onSaved }: { viewer: Viewer; onClose: () => void; onSaved: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError(''); try { await write(`/projects/${encodeURIComponent(viewer.project_id)}/metadata`, { name: String(data.get('name')), description: String(data.get('description')), expected_revision: viewer.revision }, 'PATCH'); onSaved(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  return <Modal title="Edit system details" onClose={onClose}><p className="target-system">Target system: <strong>{viewer.name}</strong><code>{viewer.project_id}</code></p>{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={event => { void submit(event); }}><label>System name<input name="name" defaultValue={viewer.name} maxLength={256} required /></label><label>Description<textarea name="description" defaultValue={viewer.description} maxLength={10000} rows={4} /></label><div className="form-actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save system details'}</button></div></form></Modal>;
}

function Lifecycle({ viewer, onClose, onSaved }: { viewer: Viewer; onClose: () => void; onSaved: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const action = viewer.archived ? 'Restore' : 'Archive';
  async function apply() { setBusy(true); setError(''); try { await write(`/projects/${encodeURIComponent(viewer.project_id)}/${viewer.archived ? 'restore' : 'archive'}`, { expected_revision: viewer.revision }); onSaved(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  return <Modal title={`${action} system`} onClose={onClose}><p className="target-system">Target system: <strong>{viewer.name}</strong><code>{viewer.project_id}</code></p><p>{viewer.archived ? 'Restore this system to the active catalogue. This does not start collection.' : 'Hide this system from the active catalogue and retain its configuration. No other system is changed.'}</p>{error && <ErrorNotice>{error}</ErrorNotice>}<div className="form-actions"><button onClick={onClose}>Cancel</button><button className={viewer.archived ? 'primary' : 'danger-button'} disabled={busy} onClick={() => { void apply(); }}>{busy ? 'Saving…' : `${action} system`}</button></div></Modal>;
}
