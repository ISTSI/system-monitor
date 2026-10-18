import { useI18n } from '../i18n';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { csrf, message, request, write } from '../api/client';
import type { components } from '../api/schema';
import type { Config } from '../topology';
import { compareEvents, emptyFilter, filterDraft, literalFilter, mergeEvents, terminal, validEvents, validFrame, type FilterDraft, type LiveEvent, type LiveSession, type LiveSnapshot } from '../live';
import { EmptyState, ErrorNotice } from './Common';
import type { HighlightContext } from '../logHighlight';
import { LOG_ROW_HEIGHT, LogColumnHeadings, LogEventCells, logTableStyle } from './LogTablePresentation';

const MAX_BROWSER_EVENTS = 20000;
const MAX_BROWSER_BYTES = 32 * 1024 * 1024;
const LIVE_COLUMNS = { timestamp: true, process: true, host: true };
function viewportRows(pane: HTMLElement | null | undefined): number {
  const headerHeight = pane?.querySelector<HTMLElement>('.log-column-headings')?.offsetHeight ?? 0;
  return Math.min(500, Math.max(1, Math.ceil(((pane?.clientHeight ?? 0) - headerHeight) / LOG_ROW_HEIGHT)));
}
function bounded(events: LiveEvent[]): LiveEvent[] {
  let size = 0; let first = events.length;
  while (first > 0 && events.length - first < MAX_BROWSER_EVENTS) {
    const bytes = new TextEncoder().encode(events[first - 1].raw_line).length;
    if (size + bytes > MAX_BROWSER_BYTES) break;
    size += bytes; first -= 1;
  }
  return events.slice(first);
}
function count(snapshot: LiveSnapshot | null, field: string): number { const value = snapshot?.counters?.[field]; return typeof value === 'number' ? value : 0; }
function safeValue(value: unknown): string { return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? String(value) : value === null ? 'unknown' : JSON.stringify(value); }

export default function LiveViewer({ projectId, config, workspaceId, selection, archived, visible, onCaptureChange, onOpenRecording }: {
  projectId: string; config: Config; workspaceId?: string; selection: { ids: string[]; version: number }; archived: boolean; visible: boolean;
  onCaptureChange: (active: boolean) => void; onOpenRecording: (id: string) => void;
}) {
  const { t } = useI18n();
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const [processIds, setProcessIds] = useState<string[]>([]);
  const [draft, setDraft] = useState(emptyFilter); const [overrides, setOverrides] = useState<Record<string, FilterDraft>>({});
  const [layout, setLayout] = useState<'merged' | 'split'>('merged'); const [lane, setLane] = useState<'events' | 'diagnostics'>('events');
  const [session, setSession] = useState<LiveSession | null>(null); const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [display, setDisplay] = useState<{ events: LiveEvent[]; diagnostics: LiveEvent[]; highlights: HighlightContext | null }>({ events: [], diagnostics: [], highlights: null });
  const retainedHighlights = useRef<HighlightContext | null>(null);
  const [paused, setPaused] = useState(false); const [detached, setDetached] = useState<LiveSession[]>([]);
  const [busy, setBusy] = useState(''); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [errorCode, setErrorCode] = useState(''); const [noticeProcessId, setNoticeProcessId] = useState('');
  const [noticeDetail, setNoticeDetail] = useState<string | null>(null);
  const [transport, setTransport] = useState('Not connected'); const [filterState, setFilterState] = useState('Ready');
  const [usage, setUsage] = useState<components['schemas']['LiveUsageResponse'] | null>(null);
  const [requestedRows, setRequestedRows] = useState(1); const [rendered, setRendered] = useState<Record<string, number>>({}); const [copied, setCopied] = useState(false);
  const [rowsByProcess, setRowsByProcess] = useState<Record<string, number>>({});
  const alive = useRef(true); const current = useRef<LiveSession | null>(null); const retained = useRef(snapshot); const pauseRef = useRef(false);
  const socket = useRef<WebSocket | null>(null); const lastSequence = useRef(0); const body = useRef<HTMLDivElement>(null);
  const awaitingSnapshot = useRef(false);
  const filterRequest = useRef(0); const lastFilter = useRef(''); const selectedAction = useRef(0); const busyRef = useRef(false);
  const applying = useRef(false); const desiredFilter = useRef(''); const [filterEpoch, setFilterEpoch] = useState(0);
  const active = !!session && !terminal(session.status);
  const systemLabel = `${config.project.name} (${projectId})`;
  const processLabel = (id: string) => {
    const process = config.processes.find(item => item.id === id);
    if (!process) return t('Unavailable process');
    return `${config.servers.find(server => server.id === process.server_id)?.name ?? t('Unavailable server')}: ${process.name}`;
  };

  const refresh = useCallback(() => {
    if (!workspaceId) return;
    void request<{ project_id: string; items: LiveSession[] }>(`${base}/live-sessions`).then(value => {
      if (alive.current && value.project_id === projectId) {
        setDetached(value.items.filter(item => item.detached && !terminal(item.status) && item.session_id !== current.current?.session_id));
        if (!current.current && value.items.some(item => item.status === 'interrupted')) setNotice('A previous monitor was interrupted. Start a new monitor explicitly; retained recordings remain available in log history.');
      }
    }).catch((cause: unknown) => { if (alive.current) setError(message(cause)); });
    void request<components['schemas']['LiveUsageResponse']>(`${base}/usage?workspace_id=${encodeURIComponent(workspaceId)}`).then(value => { if (alive.current && value.project_id === projectId) setUsage(value); }).catch(() => {});
  }, [base, projectId, workspaceId]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { if (visible) refresh(); }, [visible, refresh]);
  useEffect(() => { onCaptureChange(active); return () => onCaptureChange(false); }, [active, onCaptureChange]);
  useEffect(() => {
    if (!visible || !body.current) return;
    const measure = () => {
      const pane = body.current?.querySelector<HTMLElement>('.live-log-scroll');
      if (pane?.clientHeight) setRequestedRows(viewportRows(pane));
    };
    const observer = new ResizeObserver(measure); observer.observe(body.current); measure();
    return () => observer.disconnect();
  }, [visible, layout]);

  const applySnapshot = useCallback((value: LiveSnapshot) => {
    if (!validEvents(value.events, projectId, current.current?.process_ids ?? []) || !validEvents(value.diagnostics, projectId, current.current?.process_ids ?? [])) return;
    const limited = { ...value, events: bounded(value.events), diagnostics: bounded(value.diagnostics) };
    const owned = current.current;
    retainedHighlights.current = owned ? { global_filter: owned.global_filter, per_process_filters: owned.per_process_filters } : null;
    retained.current = limited; setSnapshot(limited);
    if (!pauseRef.current) setDisplay({ events: limited.events, diagnostics: limited.diagnostics, highlights: retainedHighlights.current });
  }, [projectId]);
  const adopt = useCallback((value: LiveSession) => {
    if (value.project_id !== projectId || value.workspace_id !== workspaceId) throw new Error('The monitor belongs to a different page workspace.');
    current.current = value; setSession(value); lastSequence.current = 0; awaitingSnapshot.current = false;
    lastFilter.current = JSON.stringify({ global_filter: literalFilter(filterDraft(value.global_filter)), per_process_filters: Object.fromEntries(Object.entries(value.per_process_filters).map(([id, filter]) => [id, literalFilter(filterDraft(filter))])), requested_rows: value.requested_rows, layout: value.layout, seed_rows_by_process: value.seed_rows_by_process ?? {} });
    setProcessIds(value.process_ids); setLayout(value.layout); setDraft(filterDraft(value.global_filter));
    setRowsByProcess(value.seed_rows_by_process ?? {});
    setOverrides(Object.fromEntries(Object.entries(value.per_process_filters).map(([id, filter]) => [id, filterDraft(filter)])));
    setPaused(false); pauseRef.current = false; setError(''); setErrorCode(''); setNotice(''); setNoticeDetail(null); setNoticeProcessId(''); setFilterState('Applied version {version}');
    applySnapshot(value.snapshot); refresh();
  }, [projectId, workspaceId, applySnapshot, refresh]);

  useEffect(() => {
    if (!session || terminal(session.status) || !workspaceId) return;
    const identity = session.session_id; const lease = session.lease_revision;
    let disposed = false; let reconnect: number | undefined; let attempts = 0;
    const connect = async () => {
      if (disposed || current.current?.session_id !== identity) return;
      try {
        const token = await csrf();
        if (disposed) return;
        const url = new URL(`/api/v1${base}/live-sessions/${encodeURIComponent(identity)}/stream`, window.location.href); url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(url); socket.current = ws; setTransport(attempts ? 'Reconnecting stream' : 'Connecting stream');
        ws.onopen = () => {
          if (disposed || !current.current) { ws.close(); return; }
          ws.send(JSON.stringify({ protocol_version: 2, type: 'hello', project_id: projectId, workspace_id: workspaceId, session_id: identity, filter_version: current.current.filter_version, payload: { csrf_token: token, last_seq: lastSequence.current || null, lease_revision: lease } }));
        };
        ws.onmessage = event => {
          if (disposed || typeof event.data !== 'string' || event.data.length > 4 * 1024 * 1024 || !current.current) return;
          let frame: unknown; try { frame = JSON.parse(event.data); } catch { ws.close(1008, 'Invalid frame'); return; }
          const controller = current.current;
          if (!validFrame(frame, controller, projectId, workspaceId) || frame.filter_version !== controller.filter_version || frame.seq < lastSequence.current || (frame.seq === lastSequence.current && !(frame.type === 'snapshot' && awaitingSnapshot.current))) return;
          const payload = frame.payload as Record<string, unknown>;
          if (frame.type === 'snapshot') {
            if (!validEvents(payload.events, projectId, controller.process_ids) || !validEvents(payload.diagnostics, projectId, controller.process_ids) || !payload.counters || !Array.isArray(payload.sources)) { ws.close(1008, 'Invalid snapshot'); return; }
            applySnapshot(payload as LiveSnapshot);
            awaitingSnapshot.current = false;
          } else if (frame.type === 'events') {
            if (!validEvents(payload.items, projectId, controller.process_ids) || (payload.diagnostics !== undefined && !validEvents(payload.diagnostics, projectId, controller.process_ids))) { ws.close(1008, 'Invalid events'); return; }
            const items = payload.items.map(event => ({ ...event, late_arrival: event.late_arrival || event.metadata?.late_arrival === 'true' }));
            const old = retained.current;
            if (old) applySnapshot({ ...old, events: mergeEvents(old.events ?? [], items.filter(event => event.timestamp_utc !== null)), diagnostics: mergeEvents(old.diagnostics ?? [], [...items.filter(event => event.timestamp_utc === null), ...(payload.diagnostics ?? []) as LiveEvent[]]) });
          } else if (frame.type === 'counters') {
            if (retained.current && payload.counters && typeof payload.counters === 'object') {
              const counters = payload.counters as NonNullable<LiveSnapshot['counters']>;
              const previousEvicted = count(retained.current, 'evicted');
              const updated = { ...retained.current, counters, ...(Array.isArray(payload.sources) ? { sources: payload.sources as LiveSnapshot['sources'] } : {}) }; retained.current = updated; setSnapshot(updated);
              if (typeof counters.evicted === 'number' && counters.evicted > previousEvicted) void request<LiveSession>(`${base}/live-sessions/${encodeURIComponent(identity)}?workspace_id=${encodeURIComponent(workspaceId)}&lease_revision=${lease}`).then(value => {
                if (!disposed && value.project_id === projectId && value.workspace_id === workspaceId && value.filter_version === current.current?.filter_version && (value.snapshot.seq ?? 0) >= lastSequence.current) { applySnapshot(value.snapshot); lastSequence.current = value.snapshot.seq ?? lastSequence.current; }
              }).catch((cause: unknown) => { if (!disposed) setError(message(cause)); });
            }
          } else if (frame.type === 'gap' || frame.type === 'resync_required') {
            if (frame.type === 'resync_required') awaitingSnapshot.current = true;
            setNotice(frame.type === 'gap' ? 'Continuity gap' : 'Replay unavailable; replacing retained view');
            setNoticeDetail(typeof payload.reason === 'string' ? payload.reason : '');
            setNoticeProcessId(typeof payload.process_id === 'string' && controller.process_ids.includes(payload.process_id) ? payload.process_id : '');
            if (payload.snapshot && typeof payload.snapshot === 'object') applySnapshot(payload.snapshot as LiveSnapshot);
          } else if (frame.type === 'stopped') {
            const stopped = { ...controller, status: 'stopped' }; current.current = stopped; setSession(stopped); setTransport('Stopped'); refresh();
          } else if (frame.type === 'error') {
            setError(typeof payload.message === 'string' ? payload.message : 'The live stream reported an error.');
            setErrorCode(typeof payload.code === 'string' ? payload.code : '');
          } else if (frame.type === 'status' && Array.isArray(payload.sources) && retained.current) {
            const updated = { ...retained.current, sources: payload.sources as LiveSnapshot['sources'] }; retained.current = updated; setSnapshot(updated);
          }
          lastSequence.current = frame.seq; attempts = 0; setTransport(frame.type === 'stopped' ? 'Stopped' : 'Stream connected');
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ protocol_version: 2, type: 'ack', project_id: projectId, workspace_id: workspaceId, session_id: identity, filter_version: controller.filter_version, payload: { last_seq: frame.seq } }));
        };
        ws.onclose = event => {
          if (socket.current === ws) socket.current = null;
          if (disposed || terminal(current.current?.status ?? 'stopped')) return;
          setTransport('Stream disconnected');
          if ([1008, 4401, 4403].includes(event.code)) { setError('The stream authorization or control lease ended. Reopen this workspace and explicitly resume if available.'); return; }
          attempts += 1;
          reconnect = window.setTimeout(() => { void connect(); }, Math.min(15000, 750 * 2 ** Math.min(attempts - 1, 5)));
        };
      } catch (cause) { if (!disposed) { setError(message(cause)); setTransport('Stream unavailable'); } }
    };
    void connect();
    return () => { disposed = true; window.clearTimeout(reconnect); socket.current?.close(1000, 'Page detached'); socket.current = null; };
  }, [session?.session_id, session?.lease_revision, !!session && terminal(session.status), base, projectId, workspaceId, applySnapshot, refresh]);

  const filters = useMemo(() => {
    try { return { global_filter: literalFilter(draft), per_process_filters: Object.fromEntries(Object.entries(overrides).filter(([id]) => processIds.includes(id)).map(([id, value]) => [id, literalFilter(value)])), requested_rows: requestedRows, layout, seed_rows_by_process: layout === 'split' ? Object.fromEntries(processIds.map(id => [id, rowsByProcess[id] ?? requestedRows])) : {} }; }
    catch (cause) { return { error: message(cause) }; }
  }, [draft, overrides, processIds, requestedRows, layout, rowsByProcess]);
  const serializedFilter = JSON.stringify(filters);
  desiredFilter.current = serializedFilter;
  useEffect(() => {
    if (!active || !workspaceId || !session || 'error' in filters || serializedFilter === lastFilter.current || applying.current) return;
    const version = ++filterRequest.current; setFilterState('Applying literal filter…');
    const timer = window.setTimeout(() => {
      const owned = current.current; if (!owned) return;
      applying.current = true;
      void write<LiveSession>(`${base}/live-sessions/${encodeURIComponent(owned.session_id)}/filters`, { workspace_id: workspaceId, lease_revision: owned.lease_revision, expected_filter_version: owned.filter_version, ...filters }, 'PUT').then(value => {
        if (!alive.current || value.session_id !== current.current?.session_id || value.lease_revision !== current.current.lease_revision || value.project_id !== projectId || value.workspace_id !== workspaceId || terminal(current.current.status)) return;
        current.current = value; setSession(value); lastFilter.current = serializedFilter;
        if (desiredFilter.current === serializedFilter) { applySnapshot(value.snapshot); setFilterState('Applied version {version}'); setError(''); }
      }).catch((cause: unknown) => { if (alive.current && version === filterRequest.current) { setError(message(cause)); setFilterState('Filter failed; previous view remains'); lastFilter.current = serializedFilter; } }).finally(() => { applying.current = false; if (alive.current) setFilterEpoch(value => value + 1); });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [serializedFilter, active, base, projectId, workspaceId, applySnapshot, filterEpoch]);

  async function start(ids = processIds) {
    if (busyRef.current) return;
    if (active) { setError('This page already controls a monitor. Stop it before monitoring a new selection, or open an independent page.'); return; }
    if (!workspaceId || archived) { setError('An active page workspace is required.'); return; }
    if (!ids.length) { setError('Select at least one configured process.'); return; }
    if ('error' in filters) { setError(filters.error ?? 'Invalid literal filter.'); return; }
    busyRef.current = true; setBusy('Starting monitor'); setError('');
    try {
      const rows = viewportRows(body.current?.querySelector<HTMLElement>('.live-log-scroll'));
      setRequestedRows(rows);
      const input: components['schemas']['LiveCreateInput'] = { project_id: projectId, project_revision: config.project.revision, workspace_id: workspaceId, process_ids: ids, mode: layout, seed_rows: rows, seed_rows_by_process: layout === 'split' ? Object.fromEntries(ids.map(id => [id, rowsByProcess[id] ?? rows])) : {}, filter: filters.global_filter, per_process_filters: Object.fromEntries(Object.entries(filters.per_process_filters).filter(([id]) => ids.includes(id))), record: false };
      const value = await write<LiveSession>(`${base}/live-sessions`, input); if (alive.current) adopt(value);
    } catch (cause) { if (alive.current) setError(message(cause)); } finally { busyRef.current = false; if (alive.current) setBusy(''); }
  }
  useEffect(() => {
    if (!selection.version || selection.version === selectedAction.current || !visible || !workspaceId) return;
    selectedAction.current = selection.version; if (!active) setProcessIds(selection.ids); void start(selection.ids);
  }, [selection.version, visible, workspaceId]);
  async function control(action: 'stop' | 'history' | 'save') {
    const owned = current.current; if (!owned || !workspaceId || busyRef.current) return;
    busyRef.current = true; setBusy(action === 'stop' ? 'Stopping monitor' : action === 'save' ? 'Starting recording' : 'Loading older retained history'); setError('');
    try {
      const value = await write<LiveSession>(`${base}/live-sessions/${encodeURIComponent(owned.session_id)}/${action}`, { workspace_id: workspaceId, lease_revision: owned.lease_revision, ...(action === 'history' ? { requested_rows: Math.min(500, requestedRows * 2) } : {}) });
      if (alive.current && value.session_id === current.current?.session_id && value.lease_revision === current.current.lease_revision && value.project_id === projectId && value.workspace_id === workspaceId && (!terminal(current.current.status) || terminal(value.status))) { current.current = value; setSession(value); applySnapshot(value.snapshot); refresh(); }
    } catch (cause) { if (alive.current) setError(message(cause)); } finally { busyRef.current = false; if (alive.current) setBusy(''); }
  }
  async function attach(item: LiveSession) {
    if (!workspaceId || busyRef.current || active) return;
    busyRef.current = true; setBusy('Resuming in this window'); setError('');
    try { const value = await write<LiveSession>(`${base}/live-sessions/${encodeURIComponent(item.session_id)}/attach`, { workspace_id: workspaceId, expected_lease_revision: item.lease_revision }); if (alive.current) adopt(value); }
    catch (cause) { if (alive.current) setError(message(cause)); } finally { busyRef.current = false; if (alive.current) setBusy(''); }
  }
  function pause() { pauseRef.current = !pauseRef.current; setPaused(pauseRef.current); if (!pauseRef.current && retained.current) setDisplay({ events: retained.current.events ?? [], diagnostics: retained.current.diagnostics ?? [], highlights: retainedHighlights.current }); }
  const reportVisible = useCallback((id: string, amount: number) => setRendered(current => current[id] === amount ? current : { ...current, [id]: amount }), []);
  const reportHeight = useCallback((id: string, rows: number) => {
    if (id === 'merged') setRequestedRows(rows);
    else setRowsByProcess(current => current[id] === rows ? current : { ...current, [id]: rows });
  }, []);
  const selectedEvents = (lane === 'diagnostics' ? display.diagnostics : display.events).toSorted(compareEvents);
  const paneIds = layout === 'merged' ? ['merged'] : (session?.process_ids ?? processIds);
  const visibleRows = Object.entries(rendered).filter(([id]) => paneIds.includes(id)).reduce((total, [, amount]) => total + amount, 0);

  return <section className="live-workspace" aria-label={t("Live monitor")}>
    <div className="history-heading"><div><h2>{t("Live monitor")}</h2><p className="muted">{systemLabel} {t("· Read-only SFTP capture · Process health unknown")}</p></div><span className="pill">{t(transport)}</span></div>
    {error && <ErrorNotice>{systemLabel}: {t(error)}{errorCode && error === 'The live stream reported an error.' && <> ({errorCode})</>}</ErrorNotice>}
    {notice && <p className="live-notice" role="status">{systemLabel}: {noticeProcessId && <>{processLabel(noticeProcessId)} · </>}{t(notice)}{noticeDetail !== null && <>: {noticeDetail || t('Coverage is uncertain.')}{noticeDetail === 'TRANSPORT_DISCONNECTED' && <> — {t('Reading the log source was interrupted; some log entries may be missing. This does not indicate process health.')}</>}</>}</p>}
    <details className="live-selection" open={!active}><summary>{session ? active ? t('Process selection (monitoring {count})', { count: session.process_ids.length }) : t('Process selection (previous monitor: {count} sources)', { count: session.process_ids.length }) : t('Process selection')}</summary><div className="live-setup"><fieldset className="history-processes"><legend>{t("Processes to monitor")}</legend>{config.processes.map(process => <label className="checkbox-label" key={`${projectId}:${process.id}`} title={process.id}><input type="checkbox" data-process-id={process.id} disabled={active || !!busy} checked={processIds.includes(process.id)} onChange={event => setProcessIds(current => event.target.checked ? [...current, process.id] : current.filter(id => id !== process.id))} /><span>{processLabel(process.id)}</span></label>)}</fieldset><div className="live-start"><p>{t("Opening this tab or selecting processes starts no capture. Choose Monitor to start. Capture continues when switching tabs; Stop this monitor ends it. Detached capture has a bounded reconnect lease.")}</p><button className="primary" disabled={active || !!busy || archived || !workspaceId} onClick={() => { void start(); }}>{processIds.length > 1 ? t("Monitor selected") : t("Monitor")}</button><span role="status">{t(busy)}</span>{usage && <details className="live-usage"><summary>{t("Own live usage and limits")}</summary><pre>{JSON.stringify(usage, null, 2)}</pre></details>}</div></div></details>
    {detached.length > 0 && <section className="live-detached" aria-label={t("Your detached monitors")}><h3>{t("Your detached monitors in")} {config.project.name}</h3><p>{t("Resume explicitly to transfer a detached controller to this page.")}</p>{detached.map(item => <div key={`${projectId}:${item.session_id}`}><span title={item.session_id}>{item.process_ids.map(processLabel).join(', ')}</span><span>{item.process_ids.length} {t("sources ·")} {t(item.status)}</span><button disabled={active || !!busy} onClick={() => { void attach(item); }}>{t("Resume in this window")}</button></div>)}</section>}
    <div className="history-filter"><FilterControls value={draft} onChange={setDraft} /><div className="live-filter-state" role="status">{'error' in filters ? t(filters.error ?? '') : t(filterState, { version: session?.filter_version ?? '' })} {t("· Literal substrings of original text; global and per-process predicates are ANDed.")}</div><details className="advanced-filter"><summary>{t("Per-process literal filters")}</summary>{(session?.process_ids ?? processIds).map(id => <fieldset className="live-override" key={`${projectId}:${id}`}><legend>{processLabel(id)}</legend><FilterControls value={overrides[id] ?? emptyFilter()} onChange={value => setOverrides(current => ({ ...current, [id]: value }))} processLabel={processLabel(id)} /></fieldset>)}</details></div>
    <div className="live-toolbar"><button disabled={!active} aria-pressed={paused} onClick={pause}>{paused ? t("Resume display") : t("Pause display")}</button><button disabled={!active || !!busy} onClick={() => { void control('stop'); }}>{t("Stop this monitor")}</button><button disabled={!active || !!busy || session?.recording} onClick={() => { void control('save'); }}>{session?.recording ? t("Recording") : t("Record")}</button><button disabled={!session || !!busy || !active} onClick={() => { void control('history'); }}>{t("Load older")}</button><label>{t("Pane layout")}<select aria-label={t("Live pane layout")} value={layout} onChange={event => setLayout(event.target.value as 'merged' | 'split')}><option value="merged">{t("Merged")}</option><option value="split">{t("Separate process panes")}</option></select></label><button onClick={() => { document.querySelectorAll<HTMLElement>('.live-log-scroll').forEach(pane => { pane.scrollTop = pane.scrollHeight; }); }}>{t("Jump to latest")}</button><button disabled={!selectedEvents.length} onClick={() => { void navigator.clipboard.writeText(selectedEvents.map(event => `[System: ${systemLabel}] [${event.server_name_snapshot}: ${event.process_name_snapshot}] ${event.raw_line}`).join('\n')).then(() => setCopied(true)).catch(() => setError('Clipboard access failed. Select and copy the log text.')); }}>{copied ? t("Copied retained view") : t("Copy retained view")}</button></div>
    {session && <div className="live-identity"><span>{t("Monitor")} <code data-testid="live-session-id">{session.session_id}</code></span><span data-testid="live-session-state">{t(session.status)}</span><span>{t("Filter")} <strong data-testid="live-filter-version">{session.filter_version}</strong></span>{session.recording && <span>{t("Recording to")} <button disabled={!session.investigation_id} onClick={() => { if (session.investigation_id) onOpenRecording(session.investigation_id); }}>{session.investigation_id ?? t("Preparing investigation")}</button></span>}</div>}
    <div className="live-counters" aria-label={t("Live event counters")}><span>{t("Received")} <strong data-testid="live-received">{count(snapshot, 'received')}</strong></span><span>{t("Matching")} <strong data-testid="live-matched">{count(snapshot, 'matched')}</strong></span><span>{t("Filtered")} <strong data-testid="live-filtered">{count(snapshot, 'filtered')}</strong></span><span>{t("Retained")} <strong data-testid="live-retained">{count(snapshot, 'retained')}</strong></span><span>{t("Evicted")} <strong data-testid="live-evicted">{count(snapshot, 'evicted')}</strong></span><span>{t("Rendered / visible")} <strong data-testid="live-visible">{visibleRows}</strong></span><span>{paused ? t("Display paused; receipt and recording continue") : t("Display follows retained capture")}</span></div>
    <p className="live-counter-help">{t("Received includes seed and new records. Matching and filtered counts describe retained raw data; rendered / visible counts the current pane viewports.")}</p>
    {snapshot && <ul className="live-source-summary" aria-label={t("Live source states")}>{(snapshot.sources ?? []).map((source, index) => <li key={`${projectId}:${index}`}><strong>{typeof source.process_id === 'string' ? processLabel(source.process_id) : t("Configured source")}</strong><span>{t(safeValue(source.state))} · {t(safeValue(source.seed_status))}</span>{!!source.error && <strong className="history-warning">{safeValue(source.error)}</strong>}</li>)}</ul>}
    {!!snapshot?.coverage?.view_limit_reached && <p className="live-notice" role="status">{t("The view reached its byte or row limit. Retained raw data may include more matches; narrow the literal filter or request older history.")}</p>}
    {count(snapshot, 'evicted') > 0 && <p className="live-notice" role="status">{t("Retention evicted")} {count(snapshot, 'evicted')} {t("raw events. Refiltering and resume cover retained data only.")}</p>}
    <nav className="workspace-tabs live-lanes" aria-label={t("Live event lane")}><button className={lane === 'events' ? 'active' : ''} onClick={() => setLane('events')}>{t("Timestamped events")}</button><button className={lane === 'diagnostics' ? 'active' : ''} onClick={() => setLane('diagnostics')}>{t("Unknown timestamps (")}{display.diagnostics.length})</button></nav>
    <div className={`live-panes ${layout}`} ref={body}>{paneIds.length ? paneIds.map(id => <LivePane highlights={display.highlights} key={`${projectId}:${id}`} paneId={id} events={selectedEvents.filter(event => id === 'merged' || event.process_id === id)} systemLabel={systemLabel} label={id === 'merged' ? t('Merged live logs') : t('{name} live logs', { name: processLabel(id) })} onVisible={reportVisible} onHeight={reportHeight} />) : <LivePane highlights={display.highlights} paneId="merged" events={[]} systemLabel={systemLabel} label={t('Merged live logs')} onVisible={reportVisible} onHeight={reportHeight} />}</div>
    {!session && <EmptyState title={t("Ready to monitor")}>{t("Select configured processes and choose Monitor. Filters, display pause and controls belong to this page.")}</EmptyState>}
    {snapshot && <details className="live-source-status"><summary>{t("Source access, seed coverage and continuity")}</summary><p>{t("Connection state is separate from process health. Silence is not a failure. SFTP rotation/truncation recovery may leave uncertain continuity.")}</p>{(snapshot.sources ?? []).map((source, index) => <div className="live-source" key={`${projectId}:${index}`}>{Object.entries(source).map(([key, value]) => <span key={key}><strong>{key === 'process_id' ? t('Process') : key.replaceAll('_', ' ')}:</strong> {key === 'process_id' && typeof value === 'string' ? processLabel(value) : safeValue(value)}</span>)}</div>)}{'coverage' in snapshot && <pre>{JSON.stringify(snapshot.coverage, null, 2)}</pre>}</details>}
  </section>;
}

function FilterControls({ value, onChange, processLabel }: { value: FilterDraft; onChange: (value: FilterDraft) => void; processLabel?: string }) {
  const { t } = useI18n();
  const prefix = processLabel ? `${processLabel} ` : '';
  return <><div className="literal-filter"><label>{prefix}{t("Contains string")}<input aria-label={`${prefix}${t('Live contains string')}`} value={value.contains} onChange={event => onChange({ ...value, contains: event.target.value })} placeholder={t("Literal text, including punctuation")} /></label><button aria-label={`${prefix}${t('Clear live filter')}`} onClick={() => onChange({ ...emptyFilter(), sensitive: value.sensitive })}>{t("Clear filter")}</button><label className="checkbox-label"><input aria-label={`${prefix}${t('Live case sensitive')}`} type="checkbox" checked={value.sensitive} onChange={event => onChange({ ...value, sensitive: event.target.checked })} />{t("Case sensitive")}</label></div><details className="advanced-filter"><summary>{prefix}{t("Advanced literal filters")}</summary><div className="form-grid"><label>{t("Additional include terms (one per line)")}<textarea aria-label={`${prefix}${t('Live additional includes')}`} value={value.includes} rows={2} onChange={event => onChange({ ...value, includes: event.target.value })} /></label><label>{t("Exclude terms (one per line)")}<textarea aria-label={`${prefix}${t('Live excludes')}`} value={value.excludes} rows={2} onChange={event => onChange({ ...value, excludes: event.target.value })} /></label></div><label>{t("Include mode")}<select aria-label={`${prefix}${t('Live include mode')}`} value={value.mode} onChange={event => onChange({ ...value, mode: event.target.value as 'any' | 'all' })}><option value="any">{t("Any included term")}</option><option value="all">{t("All included terms")}</option></select></label><p>{t("Empty terms are ignored; whitespace is preserved. Case-insensitive matching uses the server's Unicode casefold contract.")}</p></details></>;
}

function LivePane({ paneId, events, systemLabel, label, onVisible, onHeight, highlights }: { paneId: string; events: LiveEvent[]; systemLabel: string; label: string; onVisible: (id: string, count: number) => void; onHeight: (id: string, rows: number) => void; highlights: HighlightContext | null }) {
  const { t } = useI18n();
  const scroll = useRef<HTMLDivElement>(null); const follow = useRef(true); const anchor = useRef<{ id: string; offset: number } | null>(null);
  const virtual = useVirtualizer({ count: events.length, getScrollElement: () => scroll.current, estimateSize: () => LOG_ROW_HEIGHT, overscan: 5, getItemKey: index => `${events[index].project_id}:${events[index].event_id}` });
  const rows = virtual.getVirtualItems();
  useEffect(() => {
    if (!scroll.current) return;
    const measure = () => { if (scroll.current?.clientHeight) onHeight(paneId, viewportRows(scroll.current)); };
    const observer = new ResizeObserver(measure); observer.observe(scroll.current); measure();
    return () => observer.disconnect();
  }, [paneId, onHeight]);
  useLayoutEffect(() => {
    if (follow.current) { if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight; }
    else if (anchor.current) { const index = events.findIndex(event => `${event.project_id}:${event.event_id}` === anchor.current?.id); if (index >= 0 && scroll.current) scroll.current.scrollTop = index * LOG_ROW_HEIGHT + anchor.current.offset; }
  }, [events, virtual]);
  const headerHeight = scroll.current?.querySelector<HTMLElement>('.log-column-headings')?.offsetHeight ?? 0;
  const visibleCount = rows.filter(row => row.end > (scroll.current?.scrollTop ?? 0) && row.start < (scroll.current?.scrollTop ?? 0) + Math.max(0, (scroll.current?.clientHeight ?? 0) - headerHeight)).length;
  useEffect(() => { onVisible(paneId, visibleCount); }, [paneId, visibleCount, onVisible]);
  return <section className="live-pane" aria-label={label}>
    <div className="live-pane-heading"><strong>{label}</strong><span>{systemLabel}</span><span>{events.length} {t('retained matching rows')}</span></div>
    <div ref={scroll} className="live-log-scroll" style={logTableStyle(LIVE_COLUMNS)} tabIndex={0} role="table" aria-label={label} aria-rowcount={events.length + 1} aria-colcount={4} onScroll={() => {
      const element = scroll.current; if (!element) return;
      follow.current = element.scrollHeight - element.scrollTop - element.clientHeight <= LOG_ROW_HEIGHT * 2;
      const index = Math.max(0, Math.floor(element.scrollTop / LOG_ROW_HEIGHT));
      anchor.current = events[index] ? { id: `${events[index].project_id}:${events[index].event_id}`, offset: element.scrollTop - index * LOG_ROW_HEIGHT } : null;
    }}>
      <LogColumnHeadings columns={LIVE_COLUMNS} className="live-log-columns live-column-headings" />
      <div className="virtual-log-content live-log-content" style={{ height: virtual.getTotalSize() }}>{rows.map(row => {
        const event = events[row.index];
        return <div role="row" aria-rowindex={row.index + 2} key={row.key} className="log-columns log-event live-log-columns live-event" data-event-id={event.event_id} data-received-at={event.received_at} data-event-time={event.timestamp_utc ?? undefined} style={{ height: row.size, transform: `translateY(${row.start}px)` }}>
          <LogEventCells event={event} columns={LIVE_COLUMNS} highlights={highlights} messageClassName="live-message" notice={event.late_arrival && <span className="live-late">{t('Late arrival')} · </span>} />
        </div>;
      })}</div>
    </div>
  </section>;
}
