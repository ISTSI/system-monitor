import { useCallback, useEffect, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { message, request, write } from '../api/client';
import type { components } from '../api/schema';
import type { Config } from '../topology';
import { EmptyState, ErrorNotice, Modal } from './Common';
import UtcDateTimeInput from './UtcDateTimeInput';
import { defaultTimes, utc } from '../utcDateTime';

type Plan = components['schemas']['HistoricalPlanResponse'];
type Job = components['schemas']['HistoricalJobResponse'];
type Query = components['schemas']['HistoricalQueryInput'];
type Results = components['schemas']['HistoricalQueryResponse'];
type Context = components['schemas']['HistoricalContextResponse'];
type LogEvent = Results['items'][number];
type Scope = components['schemas']['HistoricalScopeInput'];
const runningStates = new Set(['queued', 'planning', 'collecting', 'indexing', 'cancel_requested']);

function bytes(value: number) { return value < 1024 ? `${value} B` : value < 1048576 ? `${(value / 1024).toFixed(1)} KiB` : `${(value / 1048576).toFixed(1)} MiB`; }

export default function HistoricalViewer({ projectId, config, workspaceId, selection, archived, historicalDemoEnabled, investigationId, onOpen, onCaptureChange }: {
  projectId: string; config: Config; workspaceId?: string; selection: { ids: string[]; version: number }; archived: boolean;
  historicalDemoEnabled: boolean;
  investigationId?: string; onOpen: (id?: string) => void; onCaptureChange: (active: boolean) => void;
}) {
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const [defaults] = useState(defaultTimes);
  const [transport, setTransport] = useState<'local_demo' | 'ssh'>(historicalDemoEnabled ? 'local_demo' : 'ssh');
  const [processIds, setProcessIds] = useState<string[]>(selection.ids);
  const [from, setFrom] = useState(defaults[0]); const [to, setTo] = useState(defaults[1]);
  const [contains, setContains] = useState(''); const [includes, setIncludes] = useState(''); const [excludes, setExcludes] = useState('');
  const [includeMode, setIncludeMode] = useState<'any' | 'all'>('all'); const [caseSensitive, setCaseSensitive] = useState(true);
  const [processFilters, setProcessFilters] = useState<Record<string, { contains: string; excludes: string }>>({});
  const [plan, setPlan] = useState<Plan | null>(null);
  const [job, setJob] = useState<Job | null>(null); const [recent, setRecent] = useState<Job[]>([]);
  const [results, setResults] = useState<Results | null>(null); const [applied, setApplied] = useState<Query | null>(null);
  const [lane, setLane] = useState<'events' | 'diagnostic'>('events'); const [layout, setLayout] = useState('merged');
  const [pageSize, setPageSize] = useState(0);
  const [previous, setPrevious] = useState<(string | null)[]>([]); const [pageNumber, setPageNumber] = useState(1);
  const [details, setDetails] = useState<LogEvent | null>(null); const [context, setContext] = useState<Context | null>(null);
  const [contextBusy, setContextBusy] = useState(false); const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  const [copied, setCopied] = useState(false); const [loadingResults, setLoadingResults] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Job | null>(null);
  const [pendingCleanup, setPendingCleanup] = useState<string[]>([]);
  const alive = useRef(true); const queryVersion = useRef(0); const contextVersion = useRef(0); const visibleBody = useRef<HTMLDivElement>(null);
  const recentVersion = useRef(0); const planVersion = useRef(0); const automaticallyLoaded = useRef<string | null>(null);
  const selectedInvestigation = useRef<string | null>(null);
  const active = !!job && runningStates.has(job.status);

  useEffect(() => { if (selection.version > 0) { setProcessIds(selection.ids); setPlan(null); planVersion.current += 1; } }, [selection]);
  useEffect(() => { onCaptureChange(active); return () => onCaptureChange(false); }, [active, onCaptureChange]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; queryVersion.current += 1; contextVersion.current += 1; }; }, []);
  const refreshRecent = useCallback(() => {
    const version = ++recentVersion.current;
    void request<{ project_id: string; items: Job[] }>(`${base}/investigations`).then(value => { if (alive.current && version === recentVersion.current && value.project_id === projectId) setRecent(value.items); }).catch((cause: unknown) => { if (alive.current && version === recentVersion.current) setError(message(cause)); });
  }, [base, projectId]);
  useEffect(() => { refreshRecent(); }, [refreshRecent]);
  useEffect(() => {
    if (!investigationId || job?.investigation_id === investigationId) return;
    let current = true;
    queryVersion.current += 1; contextVersion.current += 1;
    planVersion.current += 1; setPlan(null);
    selectedInvestigation.current = investigationId; automaticallyLoaded.current = null;
    setJob(null); setLoadingResults(false); setDetails(null); setContext(null); setResults(null); setApplied(null); setDeleteTarget(null); setLane('events');
    setBusy('Opening collection'); setError('');
    void request<Job>(`${base}/investigations/${encodeURIComponent(investigationId)}`).then(value => {
      if (current && value.project_id === projectId && value.investigation_id === investigationId) { setJob(value); setProcessIds(value.process_ids); setFrom(value.from); setTo(value.to); setResults(null); setApplied(null); setPrevious([]); }
    }).catch((cause: unknown) => { if (current) setError(message(cause)); }).finally(() => { if (current) setBusy(''); });
    return () => { current = false; };
  // A completed load must not cancel its own cleanup/finally when setJob runs.
  // Loading follows navigation; status changes are handled by the job poller.
  }, [base, investigationId, projectId]);
  useEffect(() => {
    if (!active || !job) return;
    let current = true; let timer: number;
    const poll = async () => {
      try {
        const value = await request<Job>(`${base}/jobs/${encodeURIComponent(job.job_id)}`);
        if (!current || value.project_id !== projectId || value.investigation_id !== selectedInvestigation.current) return;
        setJob(value);
        if (runningStates.has(value.status)) timer = window.setTimeout(() => { void poll(); }, 400);
        else refreshRecent();
      } catch (cause) { if (current) { setError(message(cause)); timer = window.setTimeout(() => { void poll(); }, 2000); } }
    };
    timer = window.setTimeout(() => { void poll(); }, 250);
    return () => { current = false; window.clearTimeout(timer); };
  }, [active, base, job?.job_id, projectId, refreshRecent]);
  useEffect(() => {
    if (!job || runningStates.has(job.status) || (investigationId && job.investigation_id !== investigationId)) return;
    const identity = `${projectId}:${job.investigation_id}`;
    if (automaticallyLoaded.current === identity) return;
    let current = true;
    // Defer until after effect setup so StrictMode's discarded setup cannot consume
    // the one automatic load. Filter edits never trigger this effect.
    void Promise.resolve().then(() => {
      if (!current || selectedInvestigation.current !== job.investigation_id) return;
      automaticallyLoaded.current = identity;
      void query(undefined, 'events', 1, [], job);
    });
    return () => { current = false; };
  }, [projectId, investigationId, job?.investigation_id, job?.status]);

  function scope(): Scope {
    if (!workspaceId) throw new Error('An active page workspace is required to collect. Reopen this system and retry.');
    if (!processIds.length) throw new Error('Select at least one configured process.');
    const start = utc(from); const end = utc(to);
    if (start >= end) throw new Error('From must be earlier than the exclusive To bound.');
    return { workspace_id: workspaceId, process_ids: processIds, from: start, to: end, transport };
  }
  function queryFilter(): Query['filter'] {
    const include = [...(contains === '' ? [] : [contains]), ...includes.split('\n').filter(term => term !== '')];
    const exclude = excludes.split('\n').filter(term => term !== '');
    if (include.length > 20 || exclude.length > 20 || [...include, ...exclude].some(term => Array.from(term).length > 512)) throw new Error('Use at most 20 include and 20 exclude terms, each at most 512 Unicode characters.');
    return { include, include_mode: includeMode, exclude, case_sensitive: caseSensitive };
  }
  function perProcessFilters(ids = processIds): Query['per_process_filters'] {
    const selected = ids.filter(id => processFilters[id]?.contains || processFilters[id]?.excludes);
    if (selected.some(id => [processFilters[id].contains, processFilters[id].excludes].some(term => Array.from(term).length > 512))) throw new Error('Each per-process filter term may contain at most 512 Unicode characters.');
    return Object.fromEntries(selected.map(id => [id, {
      include: processFilters[id].contains === '' ? [] : [processFilters[id].contains],
      exclude: processFilters[id].excludes === '' ? [] : [processFilters[id].excludes], include_mode: 'all', case_sensitive: caseSensitive,
    }]));
  }
  async function preview() {
    const version = ++planVersion.current;
    setBusy('Planning sources'); setError(''); setPlan(null);
    try { const input = scope(); const value = await write<Plan>(`${base}/collections/plan`, input); if (alive.current && version === planVersion.current && value.project_id === projectId) setPlan(value); }
    catch (cause) { if (alive.current) setError(message(cause)); } finally { if (alive.current) setBusy(''); }
  }
  async function start() {
    if (active || busy) return;
    setBusy('Starting collection'); setError('');
    try {
      const input = scope();
      const value = await write<Job>(`${base}/collections`, input);
      if (alive.current && value.project_id === projectId) {
        queryVersion.current += 1; contextVersion.current += 1;
        selectedInvestigation.current = value.investigation_id; automaticallyLoaded.current = null;
        setJob(value); setResults(null); setApplied(null); setPrevious([]); setDetails(null); setContext(null); setDeleteTarget(null); setLoadingResults(false); setLane('events');
        onOpen(value.investigation_id); refreshRecent();
      }
    } catch (cause) { if (alive.current) setError(message(cause)); } finally { if (alive.current) setBusy(''); }
  }
  async function cancel() {
    if (!job) return;
    setBusy('Cancelling collection'); setError('');
    try { const value = await write<Job>(`${base}/jobs/${encodeURIComponent(job.job_id)}/cancel`); if (alive.current && value.project_id === projectId) setJob(value); }
    catch (cause) { if (alive.current) setError(message(cause)); } finally { if (alive.current) setBusy(''); }
  }
  async function removeCollection() {
    if (!deleteTarget || busy || runningStates.has(deleteTarget.status)) return;
    const id = deleteTarget.investigation_id;
    setBusy('Deleting collection'); setError('');
    try {
      const value = await request<components['schemas']['HistoricalDeleteResponse']>(`${base}/investigations/${encodeURIComponent(id)}`, { method: 'DELETE' });
      if (!alive.current || value.project_id !== projectId || value.investigation_id !== id) return;
      if (value.cache_cleanup_pending) setPendingCleanup(current => current.includes(id) ? current : [...current, id]);
      recentVersion.current += 1;
      setRecent(current => current.filter(item => item.investigation_id !== id));
      setDeleteTarget(null);
      if (selectedInvestigation.current === id) {
        selectedInvestigation.current = null; automaticallyLoaded.current = null;
        queryVersion.current += 1; contextVersion.current += 1;
        setJob(null); setResults(null); setApplied(null); setPrevious([]); setPageNumber(1); setDetails(null); setContext(null); setLoadingResults(false); setLane('events');
        onOpen();
      }
      refreshRecent();
    } catch (cause) { if (alive.current) setError(message(cause)); } finally { if (alive.current) setBusy(''); }
  }
  async function query(input?: Query, nextLane = lane, nextPage = 1, history: (string | null)[] = [], initialJob?: Job) {
    if (!job || job.investigation_id !== selectedInvestigation.current) return;
    const investigation = job.investigation_id;
    const version = ++queryVersion.current; setLoadingResults(true); setError('');
    try {
      const start = input?.from ?? initialJob?.from ?? utc(from); const end = input?.to ?? initialJob?.to ?? utc(to);
      const ids = input?.process_ids ?? initialJob?.process_ids ?? processIds;
      if (start >= end) throw new Error('From must be earlier than the exclusive To bound.');
      if (!ids.length) throw new Error('Select at least one configured process.');
      const body: Query = input ?? { process_ids: ids, from: start, to: end, filter: queryFilter(), per_process_filters: perProcessFilters(ids), limit: pageSize || Math.min(1000, Math.max(40, Math.ceil((visibleBody.current?.clientHeight ?? 340) / 34) * 4)), cursor: null, lane: nextLane };
      const value = await write<Results>(`${base}/investigations/${encodeURIComponent(investigation)}/query`, body);
      if (alive.current && version === queryVersion.current && investigation === selectedInvestigation.current && value.project_id === projectId && value.items.every(item => item.project_id === projectId)) { setResults(current => ({ ...value, matched_count: value.matched_count ?? (input?.cursor ? current?.matched_count ?? null : null) })); setApplied(body); setLane(nextLane); setPrevious(history); setPageNumber(nextPage); }
    } catch (cause) { if (alive.current && version === queryVersion.current) setError(message(cause)); } finally { if (alive.current && version === queryVersion.current) setLoadingResults(false); }
  }
  async function inspect(event: LogEvent) {
    if (!job || !applied || event.project_id !== projectId) return;
    setDetails(event); setContext(null); setContextBusy(true); setCopied(false); setError(''); const version = ++contextVersion.current;
    try {
      const value = await write<Context>(`${base}/investigations/${encodeURIComponent(job.investigation_id)}/events/${encodeURIComponent(event.event_id)}/context`, { before: 5, after: 5, from: applied.from, to: applied.to, filter: applied.filter, per_process_filters: applied.per_process_filters });
      if (alive.current && version === contextVersion.current && value.project_id === projectId && value.items.every(item => item.event.project_id === projectId)) setContext(value);
    } catch (cause) { if (alive.current && version === contextVersion.current) setError(message(cause)); } finally { if (alive.current && version === contextVersion.current) setContextBusy(false); }
  }
  async function download(event: LogEvent) {
    if (!job || event.project_id !== projectId) return;
    setError('');
    try {
      const value = await write<components['schemas']['HistoricalDownloadResponse']>(`${base}/investigations/${encodeURIComponent(job.investigation_id)}/sources/${encodeURIComponent(event.source.source_revision_id)}/download`);
      if (!alive.current || value.project_id !== projectId || !value.url.startsWith(`/api/v1${base}/downloads/`)) return;
      const link = document.createElement('a'); link.href = value.url; link.download = event.source.source_revision_id; link.click();
    } catch (cause) { if (alive.current) setError(message(cause)); }
  }
  const invalidatePlan = () => { planVersion.current += 1; setPlan(null); };
  const systemLabel = `${config.project.name} (${projectId})`;
  return <section className="history-workspace" aria-label="Historical investigation">
    <div className="history-heading"><div><h2>Historical investigation</h2><p className="muted">{systemLabel} · Retained raw events, exact UTC bounds and literal filters</p></div><span className="pill">{(plan?.demo_mode ?? job?.demo_mode ?? transport === 'local_demo') ? 'Synthetic local fixtures · no SSH' : plan || job ? 'Approved SSH/SFTP' : 'SSH/SFTP · configured sources'}</span></div>
    {error && <ErrorNotice>{systemLabel}: {error}</ErrorNotice>}
    {pendingCleanup.map(id => <div className="notice history-warning" role="status" key={`${projectId}:${id}`}><span>{systemLabel}: Collection <code>{id}</code> was deleted. Cleanup of its captured files is still pending.</span><button aria-label={`Dismiss cleanup notice for collection ${id}`} onClick={() => setPendingCleanup(current => current.filter(value => value !== id))}>Dismiss</button></div>)}
    <div className="history-setup">
      <fieldset className="history-processes"><legend>Configured processes</legend>{config.processes.length ? config.processes.map(process => <label className="checkbox-label" key={`${projectId}:${process.id}`}><input type="checkbox" checked={processIds.includes(process.id)} onChange={event => { setProcessIds(current => event.target.checked ? [...current, process.id] : current.filter(id => id !== process.id)); invalidatePlan(); }} /> <span>{process.name}<small>{config.servers.find(server => server.id === process.server_id)?.name} · {process.id}</small></span></label>) : <p className="muted">This system has no configured processes.</p>}</fieldset>
      <div className="history-controls">{historicalDemoEnabled && <label className="history-transport">Collection transport<select aria-label="Collection transport" value={transport} disabled={active || !!busy} onChange={event => { setTransport(event.target.value as 'local_demo' | 'ssh'); invalidatePlan(); }}><option value="local_demo">Synthetic local fixtures</option><option value="ssh">Approved SSH/SFTP</option></select></label>}<div className="form-grid"><UtcDateTimeInput bound="From" value={from} onChange={value => { setFrom(value); invalidatePlan(); }} /><UtcDateTimeInput bound="To" value={to} onChange={value => { setTo(value); invalidatePlan(); }} /></div><p className="history-time-help">Interval [from, to): From is included; To is excluded. Unknown timestamps stay in a separate diagnostic lane.</p><div className="history-plan-actions"><button onClick={() => { void preview(); }} disabled={!!busy || active || archived || !workspaceId}>Preview collection plan</button><button className="primary" onClick={() => { void start(); }} disabled={!!busy || active || archived || !workspaceId}>Collect sources</button><span role="status">{busy}</span></div>{archived && <p className="muted">Archived system: retained collections remain readable.</p>}
      </div>
    </div>
    {plan && <section className="history-plan" aria-label="Collection plan"><div className="panel-heading"><h3>Collection plan · {config.project.name}</h3><strong>{plan.source_count} sources · approximately {bytes(plan.estimated_bytes)}</strong></div>{plan.demo_mode ? <p className="demo-label">SYNTHETIC LOCAL FIXTURES</p> : <p className="muted">Approved SSH/SFTP · read-only remote collection</p>}<p>Scans retain raw events for later refiltering and source context. Candidate date coverage is unproven until scanned.</p>{plan.warnings.map((warning, index) => <p className="history-warning" key={index}>{warning}</p>)}<ul>{plan.sources.map(source => <li key={`${projectId}:${source.source_revision_id}`}><code>{source.remote_path}</code><span>{source.process_id} · {source.kind} · {bytes(source.estimated_bytes)}</span></li>)}</ul></section>}
    {recent.length > 0 && <label className="history-recent">Open your retained collection<select aria-label="Open your retained collection" value={job?.investigation_id ?? ''} disabled={!!busy || active} onChange={event => { if (event.target.value) onOpen(event.target.value); }}><option value="">Choose a collection…</option>{recent.map(item => <option key={`${projectId}:${item.investigation_id}`} value={item.investigation_id}>{item.investigation_id.slice(0, 12)} · {item.status} · {item.event_count} events</option>)}</select></label>}
    {job && <section className="history-status" aria-label="Collection progress"><div className="panel-heading"><h3>{config.project.name} · Collection <span data-testid="collection-state">{job.status}</span></h3>{active ? <button onClick={() => { void cancel(); }} disabled={!!busy || job.status === 'cancel_requested'}>Cancel collection</button> : <button className="danger-button" onClick={() => setDeleteTarget(job)} disabled={!!busy}>Delete collection</button>}<code data-testid="investigation-id">{job.investigation_id}</code></div><progress aria-label="Scanned sources" value={job.scanned_sources} max={Math.max(job.source_count, 1)} /><p aria-live="polite">{job.scanned_sources} / {job.source_count} sources scanned · {job.event_count} indexed events · {job.parse_issue_count} parse issues · {bytes(job.downloaded_bytes)} read · {bytes(job.expanded_bytes)} expanded</p><p className="coverage-label">Coverage: <strong>{job.coverage_status}</strong>. Observed first/last timestamps do not establish continuous coverage.</p>{job.errors.map((issue, index) => <p className="history-warning" key={index}>{typeof issue === 'string' ? issue : JSON.stringify(issue)}</p>)}<details><summary>Per-source coverage and failures</summary><div className="coverage-table">{job.coverage.map(source => <div key={`${projectId}:${source.source_revision_id}`}><code>{source.remote_path}</code><span>{source.process_id} · {source.status} · {source.events} events · {bytes(source.bytes)} | byte [{source.byte_start}, {source.byte_end})</span>{source.checksum && <code>SHA-256 {source.checksum}</code>}{source.error_code && <strong>{source.error_code}</strong>}</div>)}</div></details></section>}
    <div className="history-filter"><div className="literal-filter"><label>Contains string<input value={contains} onChange={event => setContains(event.target.value)} placeholder="Literal text, including punctuation" /></label><button onClick={() => { setContains(''); setIncludes(''); setExcludes(''); setProcessFilters({}); }} disabled={contains === '' && includes === '' && excludes === '' && !Object.values(processFilters).some(value => value.contains || value.excludes)}>Clear filter</button><label className="checkbox-label"><input type="checkbox" checked={caseSensitive} onChange={event => setCaseSensitive(event.target.checked)} />Case sensitive</label><button className="primary" onClick={() => { void query(); }} disabled={!job || loadingResults}>Apply filter</button></div><details className="advanced-filter"><summary>Advanced literal filters</summary><div className="form-grid"><label>Additional include terms (one per line)<textarea aria-label="Additional include terms (one per line)" value={includes} onChange={event => setIncludes(event.target.value)} rows={3} /></label><label>Exclude terms (one per line)<textarea aria-label="Exclude terms (one per line)" value={excludes} onChange={event => setExcludes(event.target.value)} rows={3} /></label></div><label>Include mode<select aria-label="Include mode" value={includeMode} onChange={event => setIncludeMode(event.target.value as 'any' | 'all')}><option value="all">All include terms</option><option value="any">Any include term</option></select></label><p className="muted">Up to 20 include and 20 exclude terms, 512 characters each. Spaces and punctuation are literal; exclusions always reject. Case-insensitive matching uses backend Unicode casefold.</p></details><details className="advanced-filter"><summary>Per-process literal filters</summary><p className="muted">Each process filter is combined with the global filter. Blank terms add no restriction; case sensitivity follows the control above.</p>{config.processes.filter(process => processIds.includes(process.id)).map(process => <div className="form-grid process-filter-row" key={`${projectId}:${process.id}`}><label>Contains string for {process.name}<input value={processFilters[process.id]?.contains ?? ''} onChange={event => setProcessFilters(current => ({ ...current, [process.id]: { contains: event.target.value, excludes: current[process.id]?.excludes ?? '' } }))} /></label><label>Exclude string for {process.name}<input value={processFilters[process.id]?.excludes ?? ''} onChange={event => setProcessFilters(current => ({ ...current, [process.id]: { contains: current[process.id]?.contains ?? '', excludes: event.target.value } }))} /></label></div>)}</details></div>
    <div className="history-results-heading"><div className="workspace-tabs" aria-label="Result lane"><button className={lane === 'events' ? 'active' : ''} aria-pressed={lane === 'events'} onClick={() => { void query(undefined, 'events'); }} disabled={!job || loadingResults}>Timestamped events</button><button className={lane === 'diagnostic' ? 'active' : ''} aria-pressed={lane === 'diagnostic'} onClick={() => { void query(undefined, 'diagnostic'); }} disabled={!job || loadingResults}>Diagnostic lane{job ? ` (${job.parse_issue_count})` : ''}</button></div><label>Result layout<select aria-label="Result layout" value={layout} onChange={event => setLayout(event.target.value)}><option value="merged">Merged</option><option value="split">Separate process panes</option></select></label><label>Rows per result page<select aria-label="Rows per result page" value={pageSize} onChange={event => setPageSize(Number(event.target.value))}><option value={0}>Measured viewport</option><option value={10}>10</option><option value={50}>50</option><option value={200}>200</option></select></label></div>
    {results && <div className="history-result-summary" role="status"><span>{config.project.name} · {projectId}</span><strong data-testid="match-count">{results.matched_count ?? 'Count unknown'} {lane === 'diagnostic' ? 'diagnostic records' : 'matches'}</strong><span>{results.items.length} rows on page {pageNumber} · snapshot {results.source_snapshot_revision}{results.partial ? ' · Partial coverage' : ''}</span>{loadingResults && <span>Applying query…</span>}</div>}
    {applied && <p className="history-time-help">Applied UTC [{applied.from}, {applied.to}) · {applied.filter?.include?.length ?? 0} include / {applied.filter?.exclude?.length ?? 0} exclude terms · {applied.filter?.case_sensitive ? 'Case sensitive' : 'Unicode casefold'}. Edit controls and apply to replace this query.</p>}
    {lane === 'diagnostic' && <p className="history-time-help">These records have no usable event timestamp. The process predicate applies; oversized previews remain visible when their literal match is unknown. No time is invented and these records are excluded from timestamped match totals.</p>}
    <div ref={visibleBody} className="history-result-body" aria-busy={loadingResults}>{results ? results.items.length ? layout === 'merged' ? <VirtualLog events={results.items} label={`${systemLabel} · ${lane}`} onInspect={event => { void inspect(event); }} /> : <div className="history-split">{[...new Set(results.items.map(event => event.process_id))].map(id => <section key={`${projectId}:${id}`}><h3>{config.project.name} · {results.items.find(event => event.process_id === id)?.process_name_snapshot}</h3><VirtualLog events={results.items.filter(event => event.process_id === id)} label={`${systemLabel} · ${id}`} compact onInspect={event => { void inspect(event); }} /></section>)}</div> : <EmptyState title="No matching records">{job?.event_count ? 'Captured data is available. Change the literal filter, time interval or result lane.' : 'No indexed data is available. Review source coverage and collection errors.'}</EmptyState> : <EmptyState title={loadingResults ? 'Loading timestamped events' : active ? 'Collection in progress' : job ? 'Indexed data is ready to query' : 'Inspect configured log history'}>{loadingResults ? 'Loading retained events for the selected collection.' : active ? 'Timestamped events load automatically when collection finishes. You can also query the data collected so far.' : job ? 'Apply a literal filter or open the diagnostic lane to query this retained collection.' : 'Select configured processes, set UTC bounds, then collect. Preview the bounded source plan if needed.'}</EmptyState>}</div>
    {results && applied && <div className="history-pagination"><button disabled={!previous.length || loadingResults} onClick={() => { const history = previous.slice(0, -1); void query({ ...applied, cursor: previous.at(-1) ?? null }, lane, pageNumber - 1, history); }}>Previous result page</button><span>Pagination is bound to this collection, filter and source snapshot. Each page keeps the browser cache bounded.</span><button disabled={!results.next_cursor || loadingResults} onClick={() => { void query({ ...applied, cursor: results.next_cursor }, lane, pageNumber + 1, [...previous, applied.cursor ?? null]); }}>Next result page</button></div>}
    {deleteTarget && <Modal title="Delete retained collection" onClose={() => { if (!busy) setDeleteTarget(null); }}><p className="target-system">System: <strong>{config.project.name}</strong><code>{projectId}</code></p><p>Collection: <code>{deleteTarget.investigation_id}</code></p><p>Permanently delete this retained collection and its indexed events, source context and captured-source downloads. Other collections and remote log files remain available.</p><p>This cannot be undone.</p>{error && <ErrorNotice>{error}</ErrorNotice>}<div className="form-actions"><button disabled={!!busy} onClick={() => setDeleteTarget(null)}>Keep collection</button><button className="danger-button" disabled={!!busy} onClick={() => { void removeCollection(); }}>{busy === 'Deleting collection' ? 'Deleting…' : 'Delete collection'}</button></div></Modal>}
    {details && <Modal title="Event provenance and source context" onClose={() => { setDetails(null); contextVersion.current += 1; }}><p className="target-system">System: <strong>{config.project.name}</strong><code>{projectId}</code></p><p>{details.server_name_snapshot} / {details.process_name_snapshot}</p><pre className="event-raw">{details.raw_line}</pre>{details.parse_status === 'oversized_line' && <p className="history-warning">This line exceeded the configured limit. The displayed text is a bounded preview; its full literal match is unknown. The captured source download preserves the original bytes when complete.</p>}<dl className="provenance"><div><dt>Event ID</dt><dd><code>{details.event_id}</code></dd></div><div><dt>UTC / parse status</dt><dd>{details.timestamp_utc ?? 'Unknown timestamp'} · {details.parse_status}</dd></div><div><dt>Original timestamp</dt><dd><code>{details.timestamp_original ?? 'Not parsed'}</code></dd></div><div><dt>Source revision</dt><dd><code>{details.source.source_revision_id}</code></dd></div><div><dt>Original path / member</dt><dd><code>{details.source.remote_path}{details.source.archive_member ? ` :: ${details.source.archive_member} (ordinal ${details.source.member_ordinal})` : ''}</code></dd></div><div><dt>Physical position</dt><dd>Line {details.source.line_number ?? 'unknown'} · byte [{details.source.byte_start}, {details.source.byte_end})</dd></div><div><dt>Content SHA-256</dt><dd><code>{details.source.content_sha256}</code></dd></div></dl><div className="history-context-heading"><h3>Source-order context</h3><button onClick={() => { void download(details); }}>Download captured source</button><button onClick={() => { void navigator.clipboard.writeText(`[System: ${systemLabel}] [${details.server_name_snapshot}/${details.process_name_snapshot}] ${details.raw_line}`).then(() => setCopied(true)).catch(() => setError('Clipboard access failed. Select and copy the original text above.')); }}>{copied ? 'Copied' : 'Copy event text'}</button></div><p className="muted">Five physical lines before/after in the same source member, independent of the merged ordering. Context does not increase match totals.</p>{contextBusy && <p role="status">Loading source context…</p>}<ol className="source-context">{context?.items.map(item => <li className={item.is_anchor ? 'context-anchor' : ''} key={`${projectId}:${item.event.event_id}`}><div><strong>{item.is_anchor ? 'Selected event' : 'Context'}</strong><span>line {item.event.source.line_number ?? '?'}{item.outside_time_bounds ? ' · Outside time bounds' : ''}{item.matches_filter === null ? ' | Literal match unknown (truncated record)' : !item.matches_filter ? ' · Outside literal filter' : ''}{item.event.timestamp_utc === null ? ' · Unknown timestamp' : ''}</span></div><pre>{item.event.raw_line}</pre></li>)}</ol></Modal>}
  </section>;
}

function VirtualLog({ events, label, compact = false, onInspect }: { events: LogEvent[]; label: string; compact?: boolean; onInspect: (event: LogEvent) => void }) {
  const scroll = useRef<HTMLDivElement>(null);
  const virtual = useVirtualizer({ count: events.length, getScrollElement: () => scroll.current, estimateSize: () => 34, overscan: 6, getItemKey: index => `${events[index].project_id}:${events[index].event_id}` });
  useEffect(() => { virtual.scrollToOffset(0); if (scroll.current) scroll.current.scrollLeft = 0; }, [events, virtual]);
  return <div ref={scroll} className={`virtual-logs ${compact ? 'compact' : ''}`} tabIndex={0} role="table" aria-label={label} aria-rowcount={events.length + 1}><div role="row" className="log-columns log-column-headings"><span role="columnheader">Event time UTC</span><span role="columnheader">Process</span><span role="columnheader">Host</span><span role="columnheader">Log entry</span><span role="columnheader">Inspect</span></div><div className="virtual-log-content" style={{ height: virtual.getTotalSize() }}>{virtual.getVirtualItems().map(row => { const event = events[row.index]; return <div key={row.key} role="row" aria-rowindex={row.index + 2} className="log-columns log-event" style={{ height: row.size, transform: `translateY(${row.start}px)` }}><code role="cell">{event.timestamp_utc ?? 'Unknown timestamp'}</code><span role="cell" title={event.process_id}>{event.process_name_snapshot}</span><span role="cell" title={event.server_id}>{event.server_name_snapshot}</span><code role="cell" className="log-message">{logEntry(event)}</code><span role="cell"><button aria-label={`Inspect source line ${event.source.line_number ?? '?'} from ${event.process_name_snapshot}`} onClick={() => onInspect(event)}>Context</button></span></div>; })}</div></div>;
}

function logEntry(event: LogEvent): string {
  // The supported parsers return the exact source prefix. Remove only that
  // parsed timestamp, preserving every separator, field and continuation line.
  const timestamp = event.timestamp_original;
  return event.timestamp_utc !== null && timestamp && event.raw_line.startsWith(timestamp)
    ? event.raw_line.slice(timestamp.length)
    : event.raw_line;
}
