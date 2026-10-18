import { useI18n } from '../i18n';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ApiError, message, request, write } from '../api/client';
import type { components } from '../api/schema';
import type { Config } from '../topology';
import { EmptyState, ErrorNotice, Icon, Modal } from './Common';
import UtcDateTimeInput from './UtcDateTimeInput';
import { defaultTimes, formatUtcTimestamp, utc } from '../utcDateTime';
import type { InvestigationWorkspace, OfflineInvestigation } from '../investigation';
import InvestigationTools from './InvestigationTools';
import EventBookmark from './EventBookmark';
import LogText from './LogText';
import { filtersForLog, type HighlightContext } from '../logHighlight';

type Plan = components['schemas']['HistoricalPlanResponse'];
type Job = components['schemas']['HistoricalJobResponse'];
type Query = components['schemas']['HistoricalQueryInput'];
type Results = components['schemas']['HistoricalQueryResponse'];
type Context = components['schemas']['HistoricalContextResponse'];
type LogEvent = Results['items'][number];
type Scope = components['schemas']['HistoricalScopeInput'];
type SourceDetails = components['schemas']['SourceDetails'];
type OfflineList = components['schemas']['OfflineListResponse'];
const runningStates = new Set(['queued', 'planning', 'collecting', 'indexing', 'cancel_requested']);
const logRowHeight = 20;
type LogColumns = { timestamp: boolean; process: boolean; host: boolean };

function bytes(value: number) { return value < 1024 ? `${value} B` : value < 1048576 ? `${(value / 1024).toFixed(1)} KiB` : `${(value / 1048576).toFixed(1)} MiB`; }

export default function HistoricalViewer({ projectId, config, workspaceId, selection, archived, historicalDemoEnabled, investigationId, onOpen, onCaptureChange }: {
  projectId: string; config: Config; workspaceId?: string; selection: { ids: string[]; version: number }; archived: boolean;
  historicalDemoEnabled: boolean;
  investigationId?: string; onOpen: (id?: string) => void; onCaptureChange: (active: boolean) => void;
}) {
  const { t } = useI18n();
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const [defaults] = useState(defaultTimes);
  const [transport, setTransport] = useState<'local_demo' | 'ssh'>(historicalDemoEnabled ? 'local_demo' : 'ssh');
  const [processIds, setProcessIds] = useState<string[]>(selection.ids);
  const [from, setFrom] = useState(defaults[0]); const [to, setTo] = useState(defaults[1]);
  const [contains, setContains] = useState(''); const [includes, setIncludes] = useState(''); const [excludes, setExcludes] = useState('');
  const [includeMode, setIncludeMode] = useState<'any' | 'all'>('all'); const [caseSensitive, setCaseSensitive] = useState(true);
  const [processFilters, setProcessFilters] = useState<Record<string, { contains: string; excludes: string; mode?: 'any' | 'all'; sensitive?: boolean }>>({});
  const [plan, setPlan] = useState<Plan | null>(null);
  const [job, setJob] = useState<Job | null>(null); const [recent, setRecent] = useState<Job[]>([]);
  const [results, setResults] = useState<Results | null>(null); const [applied, setApplied] = useState<Query | null>(null);
  const [lane, setLane] = useState<'events' | 'diagnostic'>('events'); const [layout, setLayout] = useState<'merged' | 'split'>('merged');
  const [columns, setColumns] = useState<LogColumns>({ timestamp: true, process: true, host: true });
  const [fullScreen, setFullScreen] = useState(false);
  const resultsPanel = useRef<HTMLDialogElement>(null); const fullScreenButton = useRef<HTMLButtonElement>(null);
  const [savedWorkspace, setSavedWorkspace] = useState<InvestigationWorkspace | null>(null);
  const [offline, setOffline] = useState<OfflineInvestigation | null>(null);
  const [pageSize, setPageSize] = useState(0);
  const [previous, setPrevious] = useState<(string | null)[]>([]); const [pageNumber, setPageNumber] = useState(1);
  const [details, setDetails] = useState<LogEvent | null>(null); const [context, setContext] = useState<Context | null>(null);
  const [detailsQuery, setDetailsQuery] = useState<Query | null>(null);
  const [sourceDetails, setSourceDetails] = useState<SourceDetails | null>(null);
  const [contextBusy, setContextBusy] = useState(false); const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  const [copied, setCopied] = useState(false); const [loadingResults, setLoadingResults] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Job | null>(null);
  const [pendingCleanup, setPendingCleanup] = useState<string[]>([]);
  const alive = useRef(true); const queryVersion = useRef(0); const contextVersion = useRef(0); const visibleBody = useRef<HTMLDivElement>(null);
  const recentVersion = useRef(0); const planVersion = useRef(0); const automaticallyLoaded = useRef<string | null>(null);
  const selectedInvestigation = useRef<string | null>(null);
  const restoredQuery = useRef<Query | null>(null);
  const createdDraft = useRef<{ id: string; query: Query; layout: 'merged' | 'split' } | null>(null);
  const active = !!job && runningStates.has(job.status);
  // Keep the same table/virtualizer mounted when entering the dialog top layer.
  // Native modal focus handling also keeps the controls behind it inaccessible.
  useLayoutEffect(() => {
    const panel = resultsPanel.current;
    if (!panel) return;
    if (fullScreen) {
      panel.close(); panel.showModal();
      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      fullScreenButton.current?.focus({ preventScroll: true });
      return () => { document.body.style.overflow = previousOverflow; };
    }
    if (panel.matches(':modal')) {
      panel.close(); panel.show();
      fullScreenButton.current?.focus({ preventScroll: true });
    }
  }, [fullScreen]);
  // Locale and other control changes must not replace pane event arrays: the
  // log virtualizer resets its scroll position when query results change.
  const splitEvents = useMemo(() => {
    const grouped = new Map<string, LogEvent[]>();
    for (const event of results?.items ?? []) {
      const pane = grouped.get(event.process_id);
      if (pane) pane.push(event);
      else grouped.set(event.process_id, [event]);
    }
    return [...grouped.entries()];
  }, [results?.items]);
  const updateWorkspace = useCallback((value: InvestigationWorkspace) => {
    if (alive.current && value.project_id === projectId && value.investigation_id === selectedInvestigation.current) setSavedWorkspace(value);
  }, [projectId]);

  useEffect(() => { if (selection.version > 0) { setProcessIds(selection.ids); setPlan(null); planVersion.current += 1; } }, [selection]);
  useEffect(() => { onCaptureChange(active); return () => onCaptureChange(false); }, [active, onCaptureChange]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; queryVersion.current += 1; contextVersion.current += 1; }; }, []);
  const refreshRecent = useCallback(() => {
    const version = ++recentVersion.current;
    void Promise.all([
      request<{ project_id: string; items: Job[] }>(`${base}/investigations`),
      request<OfflineList>(`${base}/bundle-investigations`),
    ]).then(([value, imported]) => { if (alive.current && version === recentVersion.current && value.project_id === projectId && imported.project_id === projectId) setRecent([...value.items, ...imported.items.filter(item => item.project_id === projectId).map(item => item.job)]); }).catch((cause: unknown) => { if (alive.current && version === recentVersion.current) setError(message(cause)); });
  }, [base, projectId]);
  useEffect(() => { refreshRecent(); }, [refreshRecent]);
  useEffect(() => {
    if (!investigationId) return;
    let current = true;
    queryVersion.current += 1; contextVersion.current += 1;
    planVersion.current += 1; setPlan(null);
    selectedInvestigation.current = investigationId; automaticallyLoaded.current = null;
    setJob(null); setSavedWorkspace(null); setOffline(null); restoredQuery.current = null;
    setLoadingResults(false); setDetails(null); setContext(null); setResults(null); setApplied(null); setDeleteTarget(null); setLane('events');
    setBusy('Opening collection'); setError('');
    const open = async () => {
      try {
        let value: Job;
        let workspace: InvestigationWorkspace | null = null;
        let imported: OfflineInvestigation | null = null;
        try {
          value = await request<Job>(`${base}/investigations/${encodeURIComponent(investigationId)}`);
          workspace = await request<InvestigationWorkspace>(`${base}/investigations/${encodeURIComponent(investigationId)}/workspace`);
        } catch (cause) {
          if (!(cause instanceof ApiError) || cause.status !== 404) throw cause;
          imported = await request<OfflineInvestigation>(`${base}/bundle-investigations/${encodeURIComponent(investigationId)}`);
          workspace = await request<InvestigationWorkspace>(`${base}/bundle-investigations/${encodeURIComponent(investigationId)}/workspace`);
          value = imported.job;
        }
        if (!current || value.project_id !== projectId || value.investigation_id !== investigationId || (workspace && (workspace.project_id !== projectId || workspace.investigation_id !== investigationId)) || (imported && (imported.project_id !== projectId || imported.investigation_id !== investigationId))) return;
        const draft = createdDraft.current?.id === investigationId ? createdDraft.current : null;
        const state = draft && workspace && !workspace.saved ? { ...workspace, ...draft.query, filter: draft.query.filter ?? workspace.filter, per_process_filters: draft.query.per_process_filters ?? {}, layout: draft.layout } : workspace ?? imported?.document.selection;
        createdDraft.current = null;
        setOffline(imported); setSavedWorkspace(workspace); setJob(value);
        setProcessIds(state?.process_ids ?? value.process_ids); setFrom(state?.from ?? value.from); setTo(state?.to ?? value.to);
        if (state) {
          setContains(state.filter?.include?.[0] ?? ''); setIncludes(state.filter?.include?.slice(1).join('\n') ?? ''); setExcludes(state.filter?.exclude?.join('\n') ?? '');
          setIncludeMode(state.filter?.include_mode ?? 'all'); setCaseSensitive(state.filter?.case_sensitive ?? true); setLayout(state.layout);
          setProcessFilters(Object.fromEntries(Object.entries(state.per_process_filters ?? {}).map(([id, filter]) => [id, { contains: filter.include?.join('\n') ?? '', excludes: filter.exclude?.join('\n') ?? '', mode: filter.include_mode, sensitive: filter.case_sensitive }])));
          restoredQuery.current = { process_ids: state.process_ids, from: state.from, to: state.to, filter: state.filter, per_process_filters: state.per_process_filters, limit: 200, cursor: null, lane: 'events' };
        }
        setResults(null); setApplied(null); setPrevious([]);
      } catch (cause) { if (current) setError(message(cause)); }
      finally { if (current) setBusy(''); }
    };
    void open();
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
      void query(restoredQuery.current ?? undefined, 'events', 1, [], job);
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
    if (selected.some(id => [processFilters[id].contains, processFilters[id].excludes].some(terms => terms.split('\n').length > 20 || terms.split('\n').some(term => Array.from(term).length > 512)))) throw new Error('Use at most 20 per-process terms, each at most 512 Unicode characters.');
    return Object.fromEntries(selected.map(id => [id, {
      include: processFilters[id].contains.split('\n').filter(term => term !== ''),
      exclude: processFilters[id].excludes.split('\n').filter(term => term !== ''), include_mode: processFilters[id].mode ?? 'all', case_sensitive: processFilters[id].sensitive ?? caseSensitive,
    }]));
  }
  function queryDraft(): Query {
    const start = utc(from); const end = utc(to);
    if (start >= end) throw new Error('From must be earlier than the exclusive To bound.');
    if (!processIds.length) throw new Error('Select at least one process.');
    return { process_ids: processIds, from: start, to: end, filter: queryFilter(), per_process_filters: perProcessFilters(), limit: pageSize || 200, cursor: null, lane };
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
      const draft = queryDraft();
      const value = await write<Job>(`${base}/collections`, input);
      if (alive.current && value.project_id === projectId) {
        queryVersion.current += 1; contextVersion.current += 1;
        selectedInvestigation.current = value.investigation_id; automaticallyLoaded.current = null;
        createdDraft.current = { id: value.investigation_id, query: draft, layout };
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
      const body: Query = input ?? { process_ids: ids, from: start, to: end, filter: queryFilter(), per_process_filters: perProcessFilters(ids), limit: pageSize || Math.min(1000, Math.max(40, Math.ceil((visibleBody.current?.clientHeight ?? 340) / logRowHeight) * 4)), cursor: null, lane: nextLane };
      const value = await write<Results>(`${base}/${offline ? 'bundle-investigations' : 'investigations'}/${encodeURIComponent(investigation)}/query`, body);
      if (alive.current && version === queryVersion.current && investigation === selectedInvestigation.current && value.project_id === projectId && value.items.every(item => item.project_id === projectId)) { setResults(current => ({ ...value, matched_count: value.matched_count ?? (input?.cursor ? current?.matched_count ?? null : null) })); setApplied(body); setLane(nextLane); setPrevious(history); setPageNumber(nextPage); }
    } catch (cause) { if (alive.current && version === queryVersion.current) setError(message(cause)); } finally { if (alive.current && version === queryVersion.current) setLoadingResults(false); }
  }
  async function inspect(event: LogEvent, inspectQuery = applied) {
    if (!job || !inspectQuery || event.project_id !== projectId) return;
    setDetails(event); setDetailsQuery(inspectQuery); setSourceDetails(null); setContext(null); setContextBusy(true); setCopied(false); setError(''); const version = ++contextVersion.current;
    try {
      const [value, source] = await Promise.all([
        write<Context>(`${base}/${offline ? 'bundle-investigations' : 'investigations'}/${encodeURIComponent(job.investigation_id)}/events/${encodeURIComponent(event.event_id)}/context`, { before: 5, after: 5, from: inspectQuery.from, to: inspectQuery.to, filter: inspectQuery.filter, per_process_filters: inspectQuery.per_process_filters }),
        offline ? Promise.resolve(null) : request<SourceDetails>(`${base}/investigations/${encodeURIComponent(job.investigation_id)}/sources/${encodeURIComponent(event.source.source_revision_id)}/provenance`),
      ]);
      if (alive.current && version === contextVersion.current && value.project_id === projectId && value.items.every(item => item.event.project_id === projectId)) { setContext(value); if (source?.project_id === projectId && source.investigation_id === job.investigation_id) setSourceDetails(source); }
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
  function afterCacheExpired() {
    const investigation = selectedInvestigation.current;
    if (!investigation) return;
    void query(); refreshRecent();
    void request<Job>(`${base}/investigations/${encodeURIComponent(investigation)}`).then(value => {
      if (alive.current && selectedInvestigation.current === investigation && value.project_id === projectId && value.investigation_id === investigation) setJob(value);
    }).catch((cause: unknown) => { if (alive.current && selectedInvestigation.current === investigation) setError(message(cause)); });
  }
  const invalidatePlan = () => { planVersion.current += 1; setPlan(null); };
  const systemLabel = `${config.project.name} (${projectId})`;
  const displayedProcesses = offline ? [...new Map(offline.document.events.map(event => [event.process_id, { id: event.process_id, name: event.process_name_snapshot, server_id: event.server_id }])).values()] : config.processes;
  return <section className="history-workspace" aria-label={t("Historical investigation")}>
    <div className="history-heading"><div><h2>{t("Historical investigation")}</h2><p className="muted">{systemLabel} {t("· Retained raw events, exact UTC bounds and literal filters")}</p></div><span className="pill">{offline ? t("Offline bundle | no SSH") : (plan?.demo_mode ?? job?.demo_mode ?? transport === 'local_demo') ? t("Synthetic local fixtures · no SSH") : plan || job ? t("Approved SSH/SFTP") : t("SSH/SFTP · configured sources")}</span></div>
    {error && !fullScreen && !details && <ErrorNotice>{systemLabel}: {t(error)}</ErrorNotice>}
    {pendingCleanup.map(id => <div className="notice history-warning" role="status" key={`${projectId}:${id}`}><span>{systemLabel}{t(": Collection")} <code>{id}</code> {t("was deleted. Cleanup of its captured files is still pending.")}</span><button aria-label={t('Dismiss cleanup notice for collection {id}', { id })} onClick={() => setPendingCleanup(current => current.filter(value => value !== id))}>{t("Dismiss")}</button></div>)}
    <div className="history-setup">
      <fieldset className="history-processes"><legend>{offline ? t("Imported process snapshots") : t("Configured processes")}</legend>{displayedProcesses.length ? displayedProcesses.map(process => <label className="checkbox-label" key={`${projectId}:${process.id}`}><input type="checkbox" checked={processIds.includes(process.id)} onChange={event => { setProcessIds(current => event.target.checked ? [...current, process.id] : current.filter(id => id !== process.id)); invalidatePlan(); }} /> <span>{process.name}<small>{config.servers.find(server => server.id === process.server_id)?.name} · {process.id}</small></span></label>) : <p className="muted">{t("This system has no configured processes.")}</p>}</fieldset>
      <div className="history-controls">{historicalDemoEnabled && <label className="history-transport">{t("Collection transport")}<select aria-label={t("Collection transport")} value={transport} disabled={active || !!busy} onChange={event => { setTransport(event.target.value as 'local_demo' | 'ssh'); invalidatePlan(); }}><option value="local_demo">{t("Synthetic local fixtures")}</option><option value="ssh">{t("Approved SSH/SFTP")}</option></select></label>}<div className="form-grid"><UtcDateTimeInput bound="From" value={from} onChange={value => { setFrom(value); invalidatePlan(); }} /><UtcDateTimeInput bound="To" value={to} onChange={value => { setTo(value); invalidatePlan(); }} /></div><p className="history-time-help">{t("Interval [from, to): From is included; To is excluded. Unknown timestamps stay in a separate diagnostic lane.")}</p><div className="history-plan-actions"><button onClick={() => { void preview(); }} disabled={!!busy || active || archived || !workspaceId || !!offline}>{t("Preview collection plan")}</button><button className="primary" onClick={() => { void start(); }} disabled={!!busy || active || archived || !workspaceId || !!offline}>{t("Collect sources")}</button><span role="status">{t(busy)}</span></div>{archived && <p className="muted">{t("Archived system: retained collections remain readable.")}</p>}
      </div>
    </div>
    {plan && <section className="history-plan" aria-label={t("Collection plan")}><div className="panel-heading"><h3>{t("Collection plan ·")} {config.project.name}</h3><strong>{plan.source_count} {t("sources · approximately")} {bytes(plan.estimated_bytes)}</strong></div>{plan.demo_mode ? <p className="demo-label">{t("SYNTHETIC LOCAL FIXTURES")}</p> : <p className="muted">{t("Approved SSH/SFTP · read-only remote collection")}</p>}<p>{t("Scans retain raw events for later refiltering and source context. Candidate date coverage is unproven until scanned.")}</p>{plan.warnings.map((warning, index) => <p className="history-warning" key={index}>{warning}</p>)}<ul>{plan.sources.map(source => <li key={`${projectId}:${source.source_revision_id}`}><code>{source.remote_path}</code><span>{source.process_id} · {source.kind} · {bytes(source.estimated_bytes)}</span></li>)}</ul></section>}
    {recent.length > 0 && <label className="history-recent">{t("Open your retained collection")}<select aria-label={t("Open your retained collection")} value={job?.investigation_id ?? ''} disabled={!!busy || active} onChange={event => { if (event.target.value) onOpen(event.target.value); }}><option value="">{t("Choose a collection…")}</option>{recent.map(item => <option key={`${projectId}:${item.investigation_id}`} value={item.investigation_id}>{item.investigation_id.slice(0, 12)} · {t(item.status)} · {item.event_count} {t("events")}</option>)}</select></label>}
    {job && <section className="history-status" aria-label={t("Collection progress")}><div className="panel-heading"><h3>{config.project.name} {t("· Collection")} <span data-testid="collection-state">{t(job.status)}</span></h3>{active ? <button onClick={() => { void cancel(); }} disabled={!!busy || job.status === 'cancel_requested'}>{t("Cancel collection")}</button> : <button className="danger-button" onClick={() => setDeleteTarget(job)} disabled={!!busy || !!offline}>{t("Delete collection")}</button>}<code data-testid="investigation-id">{job.investigation_id}</code></div><progress aria-label={t("Scanned sources")} value={job.scanned_sources} max={Math.max(job.source_count, 1)} /><p aria-live="polite">{job.scanned_sources} / {job.source_count} {t("sources scanned ·")} {job.event_count} {t("indexed events ·")} {job.parse_issue_count} {t("parse issues ·")} {bytes(job.downloaded_bytes)} {t("read ·")} {bytes(job.expanded_bytes)} {t("expanded")}</p><p className="coverage-label">{t("Coverage:")} <strong>{t(job.coverage_status)}</strong>{t(". Observed first/last timestamps do not establish continuous coverage.")}</p>{job.errors.map((issue, index) => <p className="history-warning" key={index}>{typeof issue === 'string' ? issue : JSON.stringify(issue)}</p>)}<details><summary>{t("Per-source coverage and failures")}</summary><div className="coverage-table">{job.coverage.map(source => <div key={`${projectId}:${source.source_revision_id}`}><code>{source.remote_path}</code><span>{source.process_id} · {t(source.status)} · {source.events} {t("events ·")} {bytes(source.bytes)} {t("| byte [")}{source.byte_start}, {source.byte_end})</span>{source.checksum && <code>{t("SHA-256")} {source.checksum}</code>}{source.error_code && <strong>{source.error_code}</strong>}</div>)}</div></details></section>}
    <InvestigationTools key={`${projectId}:${job?.investigation_id ?? 'new'}`} projectId={projectId} systemName={config.project.name} investigationId={job?.investigation_id} workspace={savedWorkspace} offline={offline} queryDraft={queryDraft} layout={layout} onWorkspace={updateWorkspace} onExpired={afterCacheExpired} onInspect={(event, input) => { void inspect(event, input); }} onOpen={id => { refreshRecent(); onOpen(id); }} />
    <div className="history-filter"><div className="literal-filter"><label>{t("Contains string")}<input value={contains} onChange={event => setContains(event.target.value)} placeholder={t("Literal text, including punctuation")} /></label><button onClick={() => { setContains(''); setIncludes(''); setExcludes(''); setProcessFilters({}); }} disabled={contains === '' && includes === '' && excludes === '' && !Object.values(processFilters).some(value => value.contains || value.excludes)}>{t("Clear filter")}</button><label className="checkbox-label"><input type="checkbox" checked={caseSensitive} onChange={event => setCaseSensitive(event.target.checked)} />{t("Case sensitive")}</label><button className="primary" onClick={() => { void query(); }} disabled={!job || loadingResults}>{t("Apply filter")}</button></div><details className="advanced-filter"><summary>{t("Advanced literal filters")}</summary><div className="form-grid"><label>{t("Additional include terms (one per line)")}<textarea aria-label={t("Additional include terms (one per line)")} value={includes} onChange={event => setIncludes(event.target.value)} rows={3} /></label><label>{t("Exclude terms (one per line)")}<textarea aria-label={t("Exclude terms (one per line)")} value={excludes} onChange={event => setExcludes(event.target.value)} rows={3} /></label></div><label>{t("Include mode")}<select aria-label={t("Include mode")} value={includeMode} onChange={event => setIncludeMode(event.target.value as 'any' | 'all')}><option value="all">{t("All include terms")}</option><option value="any">{t("Any include term")}</option></select></label><p className="muted">{t("Up to 20 include and 20 exclude terms, 512 characters each. Spaces and punctuation are literal; exclusions always reject. Case-insensitive matching uses backend Unicode casefold.")}</p></details><details className="advanced-filter"><summary>{t("Per-process literal filters")}</summary><p className="muted">{t("Each process filter is combined with the global filter. Blank terms add no restriction; case sensitivity follows the control above.")}</p>{displayedProcesses.filter(process => processIds.includes(process.id)).map(process => <div className="form-grid process-filter-row" key={`${projectId}:${process.id}`}><label>{t("Contains string for")} {process.name}<textarea aria-label={t('Contains string for {name}', { name: process.name })} rows={2} value={processFilters[process.id]?.contains ?? ''} onChange={event => setProcessFilters(current => ({ ...current, [process.id]: { ...current[process.id], contains: event.target.value, excludes: current[process.id]?.excludes ?? '' } }))} /></label><label>{t("Exclude string for")} {process.name}<textarea aria-label={t('Exclude string for {name}', { name: process.name })} rows={2} value={processFilters[process.id]?.excludes ?? ''} onChange={event => setProcessFilters(current => ({ ...current, [process.id]: { ...current[process.id], contains: current[process.id]?.contains ?? '', excludes: event.target.value } }))} /></label></div>)}</details></div>
    <dialog open ref={resultsPanel} className={`history-results ${fullScreen ? 'history-results-fullscreen' : ''}`} role={fullScreen ? 'dialog' : 'region'} aria-label={t("Event results")} onCancel={event => { event.preventDefault(); setFullScreen(false); }}>
    <div className="history-results-heading">
      <div className="workspace-tabs" aria-label={t("Result lane")}><button className={lane === 'events' ? 'active' : ''} aria-pressed={lane === 'events'} onClick={() => { void query(undefined, 'events'); }} disabled={!job || loadingResults}>{t("Timestamped events")}</button><button className={lane === 'diagnostic' ? 'active' : ''} aria-pressed={lane === 'diagnostic'} onClick={() => { void query(undefined, 'diagnostic'); }} disabled={!job || loadingResults}>{t("Diagnostic lane")}{job ? ` (${job.parse_issue_count})` : ''}</button></div>
      <div className="history-table-actions">
        <label>{t("Result layout")}<select aria-label={t("Result layout")} value={layout} onChange={event => setLayout(event.target.value as 'merged' | 'split')}><option value="merged">{t("Merged")}</option><option value="split">{t("Separate process panes")}</option></select></label>
        <label>{t("Rows per result page")}<select aria-label={t("Rows per result page")} value={pageSize} onChange={event => setPageSize(Number(event.target.value))}><option value={0}>{t("Measured viewport")}</option><option value={10}>10</option><option value={50}>50</option><option value={200}>200</option></select></label>
        <details className="log-column-menu"><summary>{t("Columns")}</summary><fieldset><legend>{t("Visible columns")}</legend>
          <label className="checkbox-label"><input type="checkbox" checked={columns.timestamp} onChange={event => setColumns(current => ({ ...current, timestamp: event.target.checked }))} />{t("Event time UTC")}</label>
          <label className="checkbox-label"><input type="checkbox" checked={columns.process} onChange={event => setColumns(current => ({ ...current, process: event.target.checked }))} />{t("Process")}</label>
          <label className="checkbox-label"><input type="checkbox" checked={columns.host} onChange={event => setColumns(current => ({ ...current, host: event.target.checked }))} />{t("Host")}</label>
          <label className="checkbox-label"><input type="checkbox" checked disabled />{t("Log entry")}</label>
          <button type="button" onClick={() => setColumns({ timestamp: true, process: true, host: true })}>{t("Show all columns")}</button>
        </fieldset></details>
        <button type="button" ref={fullScreenButton} onClick={() => setFullScreen(current => !current)} aria-pressed={fullScreen}><Icon kind={fullScreen ? 'collapse' : 'expand'} />{fullScreen ? t("Exit full screen") : t("Full screen")}</button>
      </div>
    </div>
    {error && fullScreen && !details && <ErrorNotice>{systemLabel}: {t(error)}</ErrorNotice>}
    {results && <div className="history-result-summary" role="status"><span>{config.project.name} · {projectId}</span><strong data-testid="match-count">{results.matched_count ?? t("Count unknown")} {lane === 'diagnostic' ? t("diagnostic records") : t("matches")}</strong><span>{results.items.length} {t("rows on page")} {pageNumber} {t("· snapshot")} {results.source_snapshot_revision}{results.partial ? t(" · Partial coverage") : ''}</span>{loadingResults && <span>{t("Applying query…")}</span>}</div>}
    {applied && <p className="history-time-help">{t("Applied UTC [")}{formatUtcTimestamp(applied.from)}, {formatUtcTimestamp(applied.to)}) · {applied.filter?.include?.length ?? 0} {t("include /")} {applied.filter?.exclude?.length ?? 0} {t("exclude terms ·")} {applied.filter?.case_sensitive ? t("Case sensitive") : t("Unicode casefold")}{t(". Edit controls and apply to replace this query.")}</p>}
    {lane === 'diagnostic' && <p className="history-time-help">{t("These records have no usable event timestamp. The process predicate applies; oversized previews remain visible when their literal match is unknown. No time is invented and these records are excluded from timestamped match totals.")}</p>}
    <div ref={visibleBody} className="history-result-body" aria-busy={loadingResults}>{results ? results.items.length ? layout === 'merged' ? <VirtualLog columns={columns} highlights={applied} events={results.items} label={`${systemLabel} · ${t(lane === 'events' ? 'Timestamped events' : 'Diagnostic lane')}`} onInspect={event => { void inspect(event); }} /> : <div className="history-split">{splitEvents.map(([id, events]) => <section key={`${projectId}:${id}`}><h3>{config.project.name} · {events[0]?.process_name_snapshot}</h3><VirtualLog columns={columns} highlights={applied} events={events} label={`${systemLabel} · ${id}`} compact onInspect={event => { void inspect(event); }} /></section>)}</div> : <EmptyState title={results.availability === 'unavailable' ? t("Retained source data unavailable") : t("No matching records")}>{results.availability === 'unavailable' ? t("The source cache expired or was explicitly removed. Notes and pinned bookmark context remain available. Recollection requires an explicit action.") : job?.event_count ? t("Captured data is available. Change the literal filter, time interval or result lane.") : t("No indexed data is available. Review source coverage and collection errors.")}</EmptyState> : <EmptyState title={loadingResults ? t("Loading timestamped events") : active ? t("Collection in progress") : job ? t("Indexed data is ready to query") : t("Inspect configured log history")}>{loadingResults ? t("Loading retained events for the selected collection.") : active ? t("Timestamped events load automatically when collection finishes. You can also query the data collected so far.") : job ? t("Apply a literal filter or open the diagnostic lane to query this retained collection.") : t("Select configured processes, set UTC bounds, then collect. Preview the bounded source plan if needed.")}</EmptyState>}</div>
    {results && applied && <div className="history-pagination"><button disabled={!previous.length || loadingResults} onClick={() => { const history = previous.slice(0, -1); void query({ ...applied, cursor: previous.at(-1) ?? null }, lane, pageNumber - 1, history); }}>{t("Previous result page")}</button><span>{t("Pagination is bound to this collection, filter and source snapshot. Each page keeps the browser cache bounded.")}</span><button disabled={!results.next_cursor || loadingResults} onClick={() => { void query({ ...applied, cursor: results.next_cursor }, lane, pageNumber + 1, [...previous, applied.cursor ?? null]); }}>{t("Next result page")}</button></div>}
    </dialog>
    {deleteTarget && <Modal title={t("Delete retained collection")} onClose={() => { if (!busy) setDeleteTarget(null); }}><p className="target-system">{t("System:")} <strong>{config.project.name}</strong><code>{projectId}</code></p><p>{t("Collection:")} <code>{deleteTarget.investigation_id}</code></p><p>{t("Permanently delete this retained collection and its indexed events, source context and captured-source downloads. Other collections and remote log files remain available.")}</p><p>{t("This cannot be undone.")}</p>{error && <ErrorNotice>{t(error)}</ErrorNotice>}<div className="form-actions"><button disabled={!!busy} onClick={() => setDeleteTarget(null)}>{t("Keep collection")}</button><button className="danger-button" disabled={!!busy} onClick={() => { void removeCollection(); }}>{busy === 'Deleting collection' ? t("Deleting…") : t("Delete collection")}</button></div></Modal>}
    {details && <Modal title={t("Event provenance and source context")} onClose={() => { setDetails(null); contextVersion.current += 1; }}><p className="target-system">{t("System:")} <strong>{config.project.name}</strong><code>{projectId}</code></p><p>{details.server_name_snapshot} / {details.process_name_snapshot}</p>{error && <ErrorNotice>{t(error)}</ErrorNotice>}<pre className="event-raw">{details.raw_line}</pre>{details.parse_status === 'oversized_line' && <p className="history-warning">{t("This line exceeded the configured limit. The displayed text is a bounded preview; its full literal match is unknown. The captured source download preserves the original bytes when complete.")}</p>}<dl className="provenance"><div><dt>{t("Event ID")}</dt><dd><code>{details.event_id}</code></dd></div><div><dt>{t("UTC / parse status")}</dt><dd>{details.timestamp_utc ? formatUtcTimestamp(details.timestamp_utc) : t("Unknown timestamp")} · {t(details.parse_status)}</dd></div><div><dt>{t("Original timestamp")}</dt><dd><code>{details.timestamp_original ?? t("Not parsed")}</code></dd></div><div><dt>{t("Source revision")}</dt><dd><code>{details.source.source_revision_id}</code></dd></div><div><dt>{t("Original path / member")}</dt><dd><code>{details.source.remote_path}{details.source.archive_member ? ` :: ${t('Archive member {name} (ordinal {ordinal})', { name: details.source.archive_member, ordinal: details.source.member_ordinal ?? '?' })}` : ''}</code></dd></div><div><dt>{t("Physical position")}</dt><dd>{t("Line")} {details.source.line_number ?? t("unknown")} {t("· byte [")}{details.source.byte_start}, {details.source.byte_end})</dd></div><div><dt>{t("Content SHA-256")}</dt><dd><code>{details.source.content_sha256}</code></dd></div></dl><SourceCoverageDetails value={sourceDetails} /><div className="history-context-heading"><h3>{t("Source-order context")}</h3><button disabled={!!offline} onClick={() => { void download(details); }}>{t("Download captured source")}</button><button onClick={() => { void navigator.clipboard.writeText(`[System: ${systemLabel}] [${details.server_name_snapshot}/${details.process_name_snapshot}] ${details.raw_line}`).then(() => setCopied(true)).catch(() => setError('Clipboard access failed. Select and copy the original text above.')); }}>{copied ? t("Copied") : t("Copy event text")}</button></div><p className="muted">{t("Five physical lines before/after in the same source member, independent of the merged ordering. Context does not increase match totals.")}</p>{contextBusy && <p role="status">{t("Loading source context…")}</p>}{savedWorkspace && detailsQuery && job && <EventBookmark key={`${projectId}:${job.investigation_id}:${details.event_id}`} projectId={projectId} investigationId={job.investigation_id} offline={!!offline} workspace={savedWorkspace} event={details} query={detailsQuery} onWorkspace={updateWorkspace} />}<ol className="source-context">{context?.items.map(item => <li className={item.is_anchor ? 'context-anchor' : ''} key={`${projectId}:${item.event.event_id}`}><div><strong>{item.is_anchor ? t("Selected event") : t("Context")}</strong><span>{t("line")} {item.event.source.line_number ?? '?'}{item.outside_time_bounds ? t(" · Outside time bounds") : ''}{item.matches_filter === null ? t(" | Literal match unknown (truncated record)") : !item.matches_filter ? t(" · Outside literal filter") : ''}{item.event.timestamp_utc === null ? t(" · Unknown timestamp") : ''}</span></div><pre>{item.event.raw_line}</pre></li>)}</ol></Modal>}
  </section>;
}

function SourceCoverageDetails({ value }: { value: SourceDetails | null }) {
  const { t } = useI18n();
  return value && <section className="source-coverage-details" aria-label={t("Captured source coverage")}><h3>{t("Captured source coverage")}</h3><dl><div><dt>{t("Source status")}</dt><dd>{t(value.status)}{value.error_code ? ` · ${value.error_code}` : ''}</dd></div><div><dt>{t("Observed event range UTC")}</dt><dd>{value.observed_from ? formatUtcTimestamp(value.observed_from) : t("Unknown")} → {value.observed_to ? formatUtcTimestamp(value.observed_to) : t("Unknown")}</dd></div><div><dt>{t("Retained index")}</dt><dd>{value.retained_event_count} {t("events ·")} {value.parse_issue_count} {t("parse issues")}</dd></div><div><dt>{t("Original bytes")}</dt><dd>{value.raw_bytes_available ? t("Available") : t("Unavailable")} · {bytes(value.downloaded_bytes)} {t("read ·")} {bytes(value.expanded_bytes)} {t("expanded")}</dd></div><div><dt>{t("Captured byte ranges")}</dt><dd><code>{JSON.stringify(value.captured_ranges)}</code></dd></div></dl>{value.limitations.map((limitation, index) => <p className="history-warning" key={index}>{limitation}</p>)}<p className="muted">{t("Observed timestamps and scanned boundaries do not prove continuous coverage.")}</p></section>;
}

function VirtualLog({ events, label, columns, compact = false, onInspect, highlights }: { events: LogEvent[]; label: string; columns: LogColumns; compact?: boolean; onInspect: (event: LogEvent) => void; highlights: HighlightContext | null }) {
  const { t } = useI18n();
  const scroll = useRef<HTMLDivElement>(null);
  const virtual = useVirtualizer({ count: events.length, getScrollElement: () => scroll.current, estimateSize: () => logRowHeight, overscan: 6, getItemKey: index => `${events[index].project_id}:${events[index].event_id}` });
  useEffect(() => { virtual.scrollToOffset(0); if (scroll.current) scroll.current.scrollLeft = 0; }, [events, virtual]);
  const metadataWidth = 22 + (columns.timestamp ? 156 : 0) + (columns.process ? 155 : 0) + (columns.host ? 145 : 0);
  const tableStyle = { '--log-columns': `22px ${columns.timestamp ? '156px ' : ''}${columns.process ? '155px ' : ''}${columns.host ? '145px ' : ''}minmax(400px, 1fr)`, '--log-min-width': `${metadataWidth + 400}px` } as CSSProperties;
  return <div ref={scroll} className={`virtual-logs ${compact ? 'compact' : ''}`} style={tableStyle} tabIndex={0} role="table" aria-label={label} aria-rowcount={events.length + 1} aria-colcount={2 + Number(columns.timestamp) + Number(columns.process) + Number(columns.host)}>
    <div role="row" className="log-columns log-column-headings"><span role="columnheader" aria-label={t("Inspect")} />{columns.timestamp && <span role="columnheader">{t("Event time UTC")}</span>}{columns.process && <span role="columnheader">{t("Process")}</span>}{columns.host && <span role="columnheader">{t("Host")}</span>}<span role="columnheader">{t("Log entry")}</span></div>
    <div className="virtual-log-content" style={{ height: virtual.getTotalSize() }}>{virtual.getVirtualItems().map(row => {
      const event = events[row.index];
      const inspectLabel = t('Inspect source line {line} from {name}', { line: event.source.line_number ?? '?', name: event.process_name_snapshot });
      return <div key={row.key} role="row" aria-rowindex={row.index + 2} className="log-columns log-event" style={{ height: row.size, transform: `translateY(${row.start}px)` }}>
        <span role="cell" className="log-context-cell"><button type="button" className="log-context-button" aria-label={inspectLabel} title={inspectLabel} onClick={() => onInspect(event)}><Icon kind="eye" /></button></span>
        {columns.timestamp && <code role="cell" className="log-timestamp">{event.timestamp_utc ? formatUtcTimestamp(event.timestamp_utc) : t("Unknown timestamp")}</code>}
        {columns.process && <span role="cell" title={event.process_id}>{event.process_name_snapshot}</span>}
        {columns.host && <span role="cell" title={event.server_id}>{event.server_name_snapshot}</span>}
        <code role="cell" className="log-message"><LogText highlightLimitTitle={t('Highlight limit reached; original text and filter results are unchanged.')} rawLine={event.raw_line} timestampOriginal={event.timestamp_original} timestampUtc={event.timestamp_utc} filters={filtersForLog(highlights, event.process_id)} /></code>
      </div>;
    })}</div>
  </div>;
}
