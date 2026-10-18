import { useI18n } from '../i18n';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { detachOnPageHide, message, request, write } from '../api/client';
import type { CatalogueEntry, Session, Viewer, Workspace } from '../api/types';
import { ancestors, defaultGeometry, entity, entityList, parentId, withEntity, type Config, type Connection, type DeleteImpact, type EditEntity, type EntityKind, type Flow, type Geometry, type Process, type SearchResult, type Selection, type Server, type Topology } from '../topology';
import { EmptyState, ErrorNotice, Icon, Modal } from './Common';
import TopologyGraph from './TopologyGraph';
import TopologyEditor, { MoveDialog } from './TopologyEditor';
import ConfigImport, { exportConfig } from './ConfigTransfer';
import SafeMarkdown from './SafeMarkdown';
import HistoricalViewer from './HistoricalViewer';
import LiveViewer from './LiveViewer';
import ConnectionAccess from './ConnectionAccess';
import ActionMenu from './ActionMenu';
import InventoryImport from './InventoryImport';

const entityNames: Record<EntityKind, string> = { subsystem: 'Subsystem', server: 'Server', process: 'Process', flow: 'Flow', connection: 'Connection', parser: 'Parser', view: 'View' };

type Editor = { kind: EntityKind; item?: EditEntity; defaults?: Partial<Flow> };

export default function SystemWorkspace({ projectId, session, navigate, branding, historicalDemoEnabled, section = 'topology', investigationId }: { projectId: string; session: Session; branding: string; historicalDemoEnabled: boolean; navigate: (target: string) => void; section?: 'topology' | 'logs'; investigationId?: string }) {
  const { t } = useI18n();
  const [topology, setTopology] = useState<Topology | null>(null); const [viewer, setViewer] = useState<Viewer | null>(null);
  const [systems, setSystems] = useState<CatalogueEntry[]>([]); const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(true); const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState(''); const [results, setResults] = useState<SearchResult[]>([]); const [searchBusy, setSearchBusy] = useState(false);
  const [selection, setSelection] = useState<Selection | null>(null); const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [viewId, setViewId] = useState(''); const [personalCollapsed, setPersonalCollapsed] = useState<Record<string, boolean>>({}); const [reveal, setReveal] = useState(0);
  const [detailsOpen, setDetailsOpen] = useState(true); const [explorerOpen, setExplorerOpen] = useState(true);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [accessConnectionId, setAccessConnectionId] = useState('');
  const [manager, setManager] = useState<'connection' | 'parser' | null>(null); const [importing, setImporting] = useState(false);
  const [inventoryImporting, setInventoryImporting] = useState(false);
  const [moving, setMoving] = useState<{ kind: 'server' | 'process'; id: string } | null>(null);
  const [deleting, setDeleting] = useState<{ selection: Selection; impact: DeleteImpact } | null>(null);
  const [dependency, setDependency] = useState<'upstream' | 'downstream' | ''>('');
  const [historySelection, setHistorySelection] = useState<{ ids: string[]; version: number }>({ ids: [], version: 0 });
  const [monitorSelection, setMonitorSelection] = useState<{ ids: string[]; version: number }>({ ids: [], version: 0 });
  const [logMode, setLogMode] = useState<'history' | 'live'>('history'); const [monitoring, setMonitoring] = useState(false);
  const [collecting, setCollecting] = useState(false); const [switchTarget, setSwitchTarget] = useState('');
  const workspaceRef = useRef<Workspace | null>(null); const alive = useRef(true);
  const searchRef = useRef<HTMLInputElement | null>(null);
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
  useEffect(() => { if (topology) document.title = `${branding} — ${topology.config.project.name} — ${section === 'logs' ? logMode === 'live' ? t("Live monitor") : t("Historical investigation") : t("Topology")}`; }, [topology, branding, section, logMode, t]);
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
    setLogMode('history');
    setHistorySelection(current => ({ ids, version: current.version + 1 }));
    navigate(`/systems/${encodeURIComponent(projectId)}/logs`);
  }
  function monitor(ids: string[]) {
    setLogMode('live'); setMonitorSelection(current => ({ ids, version: current.version + 1 }));
    navigate(`/systems/${encodeURIComponent(projectId)}/logs`);
  }
  function switchSystem(target: string) {
    if (collecting || monitoring) setSwitchTarget(target);
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
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || document.querySelector('dialog[open]') || section !== 'topology') return;
      const target = event.target;
      const typing = target instanceof HTMLElement && (target.isContentEditable || !!target.closest('input,textarea,select,[role="textbox"]'));
      if (typing) return;
      if (event.key === '/' && !event.ctrlKey && !event.metaKey || event.key.toLowerCase() === 'k' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault(); setExplorerOpen(true); window.requestAnimationFrame(() => { searchRef.current?.focus(); searchRef.current?.select(); });
      } else if (event.key.toLowerCase() === 'z' && (event.ctrlKey || event.metaKey) && editable && !saving) {
        const action = event.shiftKey ? 'redo' : 'undo';
        if (action === 'redo' ? topology?.can_redo : topology?.can_undo) { event.preventDefault(); void history(action); }
      }
    };
    window.addEventListener('keydown', shortcut); return () => window.removeEventListener('keydown', shortcut);
  });

  if (busy && !topology) return <main className="workspace-loading"><p role="status">{t("Opening independent workspace…")}</p></main>;
  if (!topology || !config || !viewer) return <main className="catalogue-page"><ErrorNotice retry={() => { void load(); }}>{t(error || "The system could not be opened.")}</ErrorNotice><a href="/" onClick={event => { event.preventDefault(); navigate('/'); }}>{t("Back to systems")}</a></main>;
  return <main className="workspace-page">
    <div className="system-bar" aria-label={t("Current system")}>
      <div className="system-bar-title">{editable && <ActionMenu label={t("System")} items={[
        { label: t("Add subsystem"), onSelect: () => setEditor({ kind: 'subsystem' }), disabled: saving },
        { label: t("Add server"), onSelect: () => setEditor({ kind: 'server' }), disabled: saving || !config.subsystems.length },
        { label: t("Add process"), onSelect: () => setEditor({ kind: 'process' }), disabled: saving || !config.servers.length || !config.parsers?.length },
        { label: t("Add flow"), onSelect: () => setEditor({ kind: 'flow' }), disabled: saving || config.processes.length < 2 },
        { label: t("List connections"), onSelect: () => setManager('connection'), dividerBefore: true },
        { label: t("List Parsers"), onSelect: () => setManager('parser') },
        { label: t("Import configuration"), onSelect: () => setImporting(true), dividerBefore: true },
        { label: t("Import Ansible inventory files"), onSelect: () => setInventoryImporting(true) },
        { label: t("Export JSON"), onSelect: () => { void exportConfig(projectId, 'json').catch((cause: unknown) => setError(message(cause))); } },
        { label: t("Export YAML"), onSelect: () => { void exportConfig(projectId, 'yaml').catch((cause: unknown) => setError(message(cause))); } },
      ]} />}<h1 title={config.project.description}><a href={`/systems/${encodeURIComponent(projectId)}/${section}`} onClick={event => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) event.preventDefault(); }}>{config.project.name}</a></h1><code className="system-id" title={projectId}>{projectId}</code></div>
      <label className="system-selector">{t("System selector")}<select aria-label={t("System selector")} value={projectId} onChange={event => switchSystem(`/systems/${encodeURIComponent(event.target.value)}/${section}`)}>{systems.map(system => <option key={system.project_id} value={system.project_id}>{system.name}{system.archived ? t(" (archived)") : ''}</option>)}</select></label>
    </div>
    {error && <ErrorNotice retry={() => { void load(); }}>{t(error)}</ErrorNotice>}
    <div className="workspace-toolbar"><nav className="workspace-tabs" aria-label={t("System section")}><a className={section === 'topology' ? 'active' : ''} href={`/systems/${encodeURIComponent(projectId)}/topology`} onClick={event => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate(`/systems/${encodeURIComponent(projectId)}/topology`); } }}>{t("Topology")}</a><a className={section === 'logs' && logMode === 'history' ? 'active' : ''} href={`/systems/${encodeURIComponent(projectId)}/logs`} onClick={event => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); setLogMode('history'); navigate(`/systems/${encodeURIComponent(projectId)}/logs`); } }}>{t("Log history")}</a><button className={section === 'logs' && logMode === 'live' ? 'active' : ''} onClick={() => { setLogMode('live'); navigate(`/systems/${encodeURIComponent(projectId)}/logs`); }}>{t("Live monitor")}{monitoring ? t(" · collecting") : ''}</button></nav><span className="revision">{t("Revision")} {topology.revision}</span><span className="save-state" role="status">{saving ? t("Saving…") : editable ? t("Saved to server") : t("Read-only shared configuration")}</span>{topology.archived && <span className="pill">{t("Archived · read-only")}</span>}</div>
    <div hidden={section !== 'topology'}>
    <div className={`workspace-body ${!explorerOpen ? 'explorer-hidden' : ''}`}>
      {explorerOpen && <aside className="explorer"><div className="panel-heading"><h2>{t("System explorer")}</h2><span className="count-badge">{config.subsystems.length}</span></div><label className="explorer-search">{t("Search this system")}<input ref={searchRef} aria-label={t("Search this system")} placeholder={t("Name, PCS, tags, documentation…")} value={search} maxLength={256} onChange={event => setSearch(event.target.value)} /></label>{search.trim() ? <div className="search-results"><p className="search-count" aria-live="polite">{searchBusy ? t("Searching…") : t("{count} results in this system", { count: results.length })}</p>{results.map(result => <button key={`${result.kind}:${result.id}`} onClick={() => revealResult(result)}><strong>{result.name}</strong><small>{t(entityNames[result.kind])}</small></button>)}</div> : <p className="search-count">{config.processes.length} {t("configured processes")}</p>}<div className="tree">{config.subsystems.map(subsystem => <details key={subsystem.id} open><summary><Icon /><button className="tree-label" onClick={() => { select({ kind: 'subsystem', id: subsystem.id }); setReveal(current => current + 1); }}>{subsystem.name}</button></summary>{config.servers.filter(server => server.subsystem_id === subsystem.id).map(server => <details key={server.id} open><summary><Icon kind="server" /><button className="tree-label" onClick={() => { select({ kind: 'server', id: server.id }); setReveal(current => current + 1); }}>{server.name}</button></summary>{config.processes.filter(process => process.server_id === server.id).map(process => <button className={selectedIds.includes(process.id) ? 'tree-process selected' : 'tree-process'} key={process.id} onClick={() => revealResult({ kind: 'process', id: process.id, name: process.name, view_id: currentView?.id ?? null })}><Icon kind="process" />{process.name}</button>)}</details>)}</details>)}</div><details className="keyboard-help"><summary>{t("Keyboard shortcuts")}</summary><p>{t("Press / or Ctrl/Cmd+K to focus system search. Use Tab and Shift+Tab to move between controls. Menus support arrow keys, Home, End and Escape. Escape closes dialogs.")}</p>{editable && <p>{t("Ctrl/Cmd+Z undoes the last saved topology change; Ctrl/Cmd+Shift+Z redoes it. Text fields retain their normal editing shortcuts.")}</p>}<p>{t("Use the browser zoom controls (Ctrl/Cmd+plus, minus or 0). Graph controls provide separate diagram zoom.")}</p></details><div className="explorer-footer"><span className="status-dot" />{t("Page-local selection ·")} {selectedProcesses.length} {t("processes")}</div></aside>}
      <section className="topology-area"><div className="canvas-toolbar"><div><h2>{t("Documented topology")}</h2><p>{t("Health unknown · log access not checked")}</p></div><div className="view-controls">{editable && <div className="topology-history" aria-label={t("Topology history")}><button onClick={() => { void history('undo'); }} disabled={saving || topology.can_undo === false}>{t("Undo")}</button><button onClick={() => { void history('redo'); }} disabled={saving || topology.can_redo === false}>{t("Redo")}</button></div>}<button aria-pressed={explorerOpen} onClick={() => setExplorerOpen(!explorerOpen)}>{explorerOpen ? t("Hide explorer") : t("Show explorer")}</button>{config.views.length > 0 && <select aria-label={t("Named view")} value={currentView?.id ?? ''} onChange={event => { setViewId(event.target.value); setPersonalCollapsed({}); }}>{personalView && <option value="__search_reveal__">{t("Search reveal (personal)")}</option>}{config.views.map(view => <option key={view.id} value={view.id}>{view.name}</option>)}</select>}{editable && <><button onClick={() => setEditor({ kind: 'view' })}>{t("Add view")}</button>{currentView && !personalView && <><button onClick={() => setEditor({ kind: 'view', item: currentView })}>{t("Edit view")}</button><button onClick={() => { void previewDelete({ kind: 'view', id: currentView.id }); }}>{t("Delete view")}</button></>}</>}<button aria-pressed={detailsOpen} onClick={() => setDetailsOpen(!detailsOpen)}>{detailsOpen ? t("Hide details") : t("Show details")}</button></div></div>
        {displayedView ? <TopologyGraph config={config} view={displayedView} editable={editable && !personalView} selection={selection} selectedIds={selectedIds} highlighted={highlighted} reveal={reveal} saving={saving} onSelect={select} onMultiSelect={multiSelect} onGeometry={geometry} onCollapse={collapse} onConnect={connect} /> : <EmptyState title={config.subsystems.length ? t("Create a named view") : t("Your system starts here")}>{editable ? t("Add a subsystem, connection, server, parser and process; then create a view to arrange your topology.") : t("No named topology view is configured.")}</EmptyState>}
        {selectedProcesses.length > 0 && <div className="dependency-toolbar"><span>{selectedProcesses.length} {t("processes selected")}</span><button className="primary" onClick={() => inspectHistory(selectedProcesses.map(process => process.id))}>{selectedProcesses.length > 1 ? t("Inspect selected history") : t("Inspect history")}</button><button className="primary" disabled={!workspace || topology.archived} onClick={() => monitor(selectedProcesses.map(process => process.id))}>{selectedProcesses.length > 1 ? t("Monitor selected") : t("Monitor")}</button><button aria-pressed={dependency === 'upstream'} onClick={() => setDependency(dependency === 'upstream' ? '' : 'upstream')}>{t("Highlight upstream")}</button><button aria-pressed={dependency === 'downstream'} onClick={() => setDependency(dependency === 'downstream' ? '' : 'downstream')}>{t("Highlight downstream")}</button><button disabled={!highlighted.size} onClick={() => setSelectedIds(current => [...new Set([...current, ...highlighted])])}>{t("Add highlighted neighbours")}</button><button disabled={!highlighted.size} onClick={() => inspectHistory([...highlighted])}>{t("Inspect highlighted neighbours")}</button><button disabled={!highlighted.size || !workspace || topology.archived} onClick={() => monitor([...highlighted])}>{t("Monitor highlighted neighbours")}</button><small>{t("Possible transfers, not observed causality")}</small></div>}
        {detailsOpen && <section className="process-details" aria-label={t("Process details")}><div className="panel-heading"><h2>{selected ? selection?.kind === 'process' ? t("Process details") : t("Element details") : t("Select a process")}</h2><span className="pill">{config.project.name}</span></div>{selected && selection ? <div className="details-content"><div className="details-title"><Icon kind={selection.kind === 'server' ? 'server' : selection.kind === 'process' ? 'process' : 'system'} /><div><h3>{selected.name}</h3><code>{selected.id}</code></div><span className="pill">{t(entityNames[selection.kind])}</span>{editable && <div className="selection-actions"><button onClick={() => setEditor({ kind: selection.kind, item: selected })}>{t("Edit selected")}</button>{(selection.kind === 'process' || selection.kind === 'server') && <button onClick={() => setMoving({ kind: selection.kind as 'server' | 'process', id: selection.id })}>{selection.kind === 'process' ? t("Move to server") : t("Move to subsystem")}</button>}<button onClick={() => { void previewDelete(selection); }}>{t("Delete selected")}</button></div>}</div>{'description' in selected && <SafeMarkdown text={selected.description} />}{'tags' in selected && selected.tags.length > 0 && <div className="tag-list">{selected.tags.map(tag => <span className="pill" key={tag}>{tag}</span>)}</div>}<dl>{selection.kind === 'process' && <><div><dt>{t("Process health")}</dt><dd>{t("Unknown · no health probe")}</dd></div><div><dt>{t("Log access")}</dt><dd>{t("Not checked")}</dd></div>{(selected as Process).pcs_resource_name && <div><dt>{t("PCS resource name")}</dt><dd>{(selected as Process).pcs_resource_name}</dd></div>}{(selected as Process).log_source && <><div><dt>{t("Documented log path")}</dt><dd><code>{(selected as Process).log_source?.active_path}</code></dd></div><div><dt>{t("Parser / encoding")}</dt><dd>{(selected as Process).log_source?.parser_id} · {(selected as Process).log_source?.encoding}</dd></div></>}</>}{selection.kind === 'server' && <div><dt>{t("Subsystem")}</dt><dd>{config.subsystems.find(item => item.id === (selected as Server).subsystem_id)?.name}</dd></div>}{selectedConnection && <><div><dt>{t("SSH profile")}</dt><dd>{selectedConnection.name}</dd></div><div><dt>{t("SSH host")}</dt><dd><code>{selectedConnection.host}</code></dd></div><div><dt>{t("SSH port")}</dt><dd>{selectedConnection.port}</dd></div>{editable && <div><dt>{t("Connection settings")}</dt><dd><button onClick={() => setEditor({ kind: 'connection', item: selectedConnection })}>{t("Edit SSH connection")}</button><button onClick={() => setAccessConnectionId(selectedConnection.id)}>{t("Password & connection test")}</button></dd></div>}</>}{selection.kind === 'flow' && <><div><dt>{t("Source → target")}</dt><dd>{config.processes.find(item => item.id === (selected as Flow).source_process_id)?.name} → {config.processes.find(item => item.id === (selected as Flow).target_process_id)?.name}</dd></div><div><dt>{t("Protocol")}</dt><dd>{(selected as Flow).protocol || t("Unspecified")}</dd></div></>}</dl>{selection.kind === 'process' && <><div className="related-flows"><strong>{t("Related flows")}</strong>{config.flows.filter(flow => [flow.source_process_id, flow.target_process_id].includes(selection.id)).map(flow => <button key={flow.id} onClick={() => select({ kind: 'flow', id: flow.id })}>{flow.name} →</button>)}</div><div className="history-entry"><button className="primary" onClick={() => inspectHistory([selection.id])}>{t("Inspect this process history")}</button><button className="primary" disabled={!workspace || topology.archived} onClick={() => monitor([selection.id])}>{t("Monitor this process")}</button><p className="muted">{t("Collect configured log history, with an optional source-plan preview. Selecting a process starts no connection.")}</p></div></>}</div> : <p className="details-placeholder">{t("Choose an element or flow in the explorer or diagram to read its documentation and properties.")}</p>}</section>}
      </section>
    </div></div><div hidden={section !== 'logs' || logMode !== 'history'}><HistoricalViewer projectId={projectId} config={config} workspaceId={workspace?.workspace_id} selection={historySelection} archived={topology.archived} historicalDemoEnabled={historicalDemoEnabled} investigationId={investigationId} onOpen={id => navigate(id ? `/systems/${encodeURIComponent(projectId)}/investigations/${encodeURIComponent(id)}` : `/systems/${encodeURIComponent(projectId)}/logs`)} onCaptureChange={setCollecting} /></div><div hidden={section !== 'logs' || logMode !== 'live'}><LiveViewer projectId={projectId} config={config} workspaceId={workspace?.workspace_id} selection={monitorSelection} archived={topology.archived} visible={section === 'logs' && logMode === 'live'} onCaptureChange={setMonitoring} onOpenRecording={id => { setLogMode('history'); navigate(`/systems/${encodeURIComponent(projectId)}/investigations/${encodeURIComponent(id)}`); }} /></div><div className="workspace-status"><span>{t("Workspace")} <code data-testid="workspace-id">{workspace?.workspace_id ?? (topology.archived ? t("archived view") : t("Unavailable"))}</code></span><span>{monitoring ? t("Live capture running for this page") : collecting ? t("Historical collection running for this page") : workspace?.state === 'active' ? t("Independent page workspace") : t("No active collection")}</span></div>
    {switchTarget && <Modal title={t("Switch system while collecting")} onClose={() => setSwitchTarget('')}><p>{t("Collection for")} <strong>{config.project.name}</strong> {t("remains associated with this system. Live capture detaches for its bounded reconnect lease; reopen this system and explicitly resume to regain control. Historical collection continues on the server. Other pages keep their controls.")}</p><div className="form-actions"><button onClick={() => setSwitchTarget('')}>{t("Stay in this system")}</button><button className="primary" onClick={() => { const target = switchTarget; setSwitchTarget(''); navigate(target); }}>{t("Detach this page and switch")}</button></div></Modal>}
    {editor && <TopologyEditor key={`${editor.kind}:${editor.item?.id ?? 'new'}`} {...editor} config={config} currentView={currentView} onClose={() => setEditor(null)} onSave={async (kind, value, connection) => { const next = connection ? withEntity(config, 'connection', connection) : config; await commit(withEntity(next, kind, value)); if (kind === 'view') setViewId(value.id); else select({ kind, id: value.id }); }} />}
    {manager && <Modal title={manager === 'connection' ? t("Connection profiles") : t("Parser profiles")} onClose={() => setManager(null)}><p className="target-system">{t("Target system:")} <strong>{config.project.name}</strong><code>{projectId}</code></p><button className="primary" onClick={() => { setEditor({ kind: manager }); setManager(null); }}>{manager === 'connection' ? t("Add connection") : t("Add parser")}</button><div className="profile-list">{entityList(config, manager).map(item => <div key={item.id}><span><strong>{item.name}</strong><code>{item.id}</code></span><button aria-label={t("Edit {kind} {name}", { kind: t(entityNames[manager]), name: item.name })} onClick={() => { setEditor({ kind: manager, item }); setManager(null); }}>{t("Edit")}</button>{manager === 'connection' && <button aria-label={t("Password and test {name}", { name: item.name })} onClick={() => { setAccessConnectionId(item.id); setManager(null); }}>{t("Password & test")}</button>}<button aria-label={t("Delete {kind} {name}", { kind: t(entityNames[manager]), name: item.name })} onClick={() => { void previewDelete({ kind: manager, id: item.id }); setManager(null); }}>{t("Delete")}</button></div>)}</div></Modal>}
    {accessConnection && session.role === 'administrator' && <ConnectionAccess key={accessConnection.id} config={config} connection={accessConnection} onClose={() => setAccessConnectionId('')} onJump={setAccessConnectionId} />}
    {moving && <MoveDialog config={config} selection={moving} onClose={() => setMoving(null)} onMove={move} />}
    {deleting && <DeleteDialog impact={deleting.impact} kind={deleting.selection.kind} name={entity(config, deleting.selection)?.name ?? deleting.selection.id} onClose={() => setDeleting(null)} onConfirm={deleteSelected} />}
    {importing && <ConfigImport config={config} revision={topology.revision} onClose={() => setImporting(false)} onCommitted={load} />}
    {inventoryImporting && editable && <InventoryImport config={config} revision={topology.revision} onClose={() => setInventoryImporting(false)} onCommitted={load} />}
  </main>;
}

function DeleteDialog({ impact, name, kind, onClose, onConfirm }: { impact: DeleteImpact; name: string; kind: EntityKind; onClose: () => void; onConfirm: () => Promise<void> }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function confirm() { setBusy(true); setError(''); try { await onConfirm(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  return <Modal title={t("Delete impact preview")} onClose={onClose}><p>{t("Delete")} {t(entityNames[kind])} <strong>{name}</strong> {t("with the following impact:")}</p>{error && <ErrorNotice>{t(error)}</ErrorNotice>}<ul>{impact.entities.map(item => <li key={`${item.kind}:${item.id}`}>{t(entityNames[item.kind])}: {item.name} <code>{item.id}</code></li>)}</ul><dl><div><dt>{t("Removed flows")}</dt><dd>{impact.flows.length}</dd></div><div><dt>{t("Affected views")}</dt><dd>{impact.views.length}</dd></div><div><dt>{t("Saved investigations")}</dt><dd>{impact.investigations.length}</dd></div><div><dt>{t("Active sessions")}</dt><dd>{impact.active_sessions.length}</dd></div></dl><p className="muted">{t("Historical identities and name snapshots are preserved.")}</p><div className="form-actions"><button onClick={onClose}>{t("Cancel")}</button><button className="danger-button" disabled={busy} onClick={() => { void confirm(); }}>{busy ? t("Deleting…") : t("Confirm deletion")}</button></div></Modal>;
}
