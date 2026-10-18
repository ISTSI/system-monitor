import { useI18n } from '../i18n';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ApiError, message, request, write } from '../api/client';
import type { components } from '../api/schema';
import type { Config } from '../topology';
import { EmptyState, ErrorNotice, Icon, Modal } from './Common';
import HistoricalFiltersDialog, { type HistoricalFilterDraft } from './HistoricalFiltersDialog';
import UtcDateTimeInput from './UtcDateTimeInput';
import InvestigationPinDialog from './InvestigationPinDialog';
import { pinSelectionFromBookmarks, type BookmarksWithPins, type PinGroupItem, type PinSelectionEntry } from '../investigationPins';
import { defaultTimes, formatUtcTimestamp, utc } from '../utcDateTime';
import type { InvestigationWorkspace, OfflineInvestigation } from '../investigation';
import InvestigationTools from './InvestigationTools';
import EventBookmark from './EventBookmark';
import { VirtualLog } from './HistoricalLogTable';
import HistoricalProcessPanes from './HistoricalProcessPanes';
import ProcessVisibilityMenu from './ProcessVisibilityMenu';

type Plan = components['schemas']['HistoricalPlanResponse'];
type Job = components['schemas']['HistoricalJobResponse'];
type Query = components['schemas']['HistoricalQueryInput'];
type Filter = NonNullable<Query['filter']>;
type Results = components['schemas']['HistoricalQueryResponse'];
type Context = components['schemas']['HistoricalContextResponse'];
type LogEvent = Results['items'][number];
type Scope = components['schemas']['HistoricalScopeInput'];
type SourceDetails = components['schemas']['SourceDetails'];
type OfflineList = components['schemas']['OfflineListResponse'];
const runningStates = new Set(['queued', 'planning', 'collecting', 'indexing', 'cancel_requested']);
const logRowHeight = 20;
type LogColumns = { timestamp: boolean; process: boolean; host: boolean };
type QueryView = { scope: Query; visibleIds: string[] | null; previousVisibleIds?: string[] | null };

function visibleQuery(scope: Query, ids: string[]): Query {
  return { ...scope, process_ids: ids, cursor: null,
    per_process_filters: Object.fromEntries(Object.entries(scope.per_process_filters ?? {}).filter(([id]) => ids.includes(id))) };
}

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
  const [collectionFrom, setCollectionFrom] = useState(defaults[0]); const [collectionTo, setCollectionTo] = useState(defaults[1]);
  const [from, setFrom] = useState(defaults[0]); const [to, setTo] = useState(defaults[1]);
  const [filter, setFilter] = useState<Filter>({ include: [], exclude: [], include_mode: 'all', case_sensitive: true });
  const [processFilters, setProcessFilters] = useState<NonNullable<Query['per_process_filters']>>({});
  const [filtersOpen, setFiltersOpen] = useState(false); const [pinOpen, setPinOpen] = useState(false);
  const [viewedPin, setViewedPin] = useState<PinGroupItem | undefined>();
  const [pinEntries, setPinEntries] = useState<PinSelectionEntry[] | null>(null);
  const [modifyingPin, setModifyingPin] = useState<PinGroupItem | undefined>();
  const [pinChoiceOpen, setPinChoiceOpen] = useState(false);
  const [markedEvents, setMarkedEvents] = useState<Record<string, PinSelectionEntry>>({});
  const [plan, setPlan] = useState<Plan | null>(null);
  const [job, setJob] = useState<Job | null>(null); const [recent, setRecent] = useState<Job[]>([]);
  const [results, setResults] = useState<Results | null>(null); const [applied, setApplied] = useState<Query | null>(null);
  const [queryScope, setQueryScope] = useState<Query | null>(null);
  const [lane, setLane] = useState<'events' | 'diagnostic'>('events'); const [layout, setLayout] = useState<'merged' | 'split'>('merged');
  const [paneColumns, setPaneColumns] = useState<1 | 2 | 3 | 4>(1);
  const [shownProcessIds, setShownProcessIds] = useState<string[] | null>(null);
  const [columns, setColumns] = useState<LogColumns>({ timestamp: true, process: true, host: true });
  const [fullScreen, setFullScreen] = useState(false);
  const resultsPanel = useRef<HTMLDialogElement>(null); const fullScreenButton = useRef<HTMLButtonElement>(null);
  const columnMenu = useRef<HTMLDetailsElement>(null);
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
  useEffect(() => { setViewedPin(undefined); setPinEntries(null); setModifyingPin(undefined); setPinChoiceOpen(false); }, [projectId, job?.investigation_id]);
  const restoredQuery = useRef<Query | null>(null);
  const createdDraft = useRef<{ id: string; query: Query; layout: 'merged' | 'split' } | null>(null);
  const active = !!job && runningStates.has(job.status);
  useEffect(() => {
    const dismissColumns = (event: PointerEvent) => {
      const menu = columnMenu.current;
      if (menu?.open && event.target instanceof Node && !menu.contains(event.target)) menu.open = false;
    };
    document.addEventListener('pointerdown', dismissColumns, true);
    return () => document.removeEventListener('pointerdown', dismissColumns, true);
  }, []);
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
  const paneProcesses = useMemo(() => (queryScope?.process_ids ?? []).map(id => {
    const snapshot = (offline?.document.events ?? results?.items)?.find(event => event.process_id === id);
    const process = config.processes.find(item => item.id === id);
    return { id, name: snapshot?.process_name_snapshot ?? process?.name ?? id,
      host: snapshot?.server_name_snapshot ?? config.servers.find(server => server.id === process?.server_id)?.name ?? '' };
  }), [queryScope?.process_ids, config, offline, results?.items]);
  const visiblePaneIds = useMemo(() => (queryScope?.process_ids ?? []).filter(id => shownProcessIds === null || shownProcessIds.includes(id)), [queryScope?.process_ids, shownProcessIds]);
  const mergedEvents = useMemo(() => (results?.items ?? []).filter(event => visiblePaneIds.includes(event.process_id)), [results?.items, visiblePaneIds]);
  const mergedScopeMatches = !!applied && !!queryScope && JSON.stringify({ ...applied, cursor: null }) === JSON.stringify(visibleQuery(queryScope, visiblePaneIds));
  const selectedEventIds = useMemo(() => new Set(Object.keys(markedEvents)), [markedEvents]);
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
    setShownProcessIds(null); setQueryScope(null); setMarkedEvents({}); setPinOpen(false); setFiltersOpen(false);
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
        setProcessIds(value.process_ids); setCollectionFrom(value.from); setCollectionTo(value.to);
        setFrom(state?.from ?? value.from); setTo(state?.to ?? value.to);
        if (state) {
          setFilter(state.filter ?? { include: [], exclude: [], include_mode: 'all', case_sensitive: true }); setLayout(state.layout);
          setProcessFilters(state.per_process_filters ?? {});
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
        if (runningStates.has(value.status)) {
          setJob(value); timer = window.setTimeout(() => { void poll(); }, 400);
        } else {
          const workspace = await request<InvestigationWorkspace>(`${base}/investigations/${encodeURIComponent(value.investigation_id)}/workspace`);
          if (!current || value.investigation_id !== selectedInvestigation.current || workspace.project_id !== projectId || workspace.investigation_id !== value.investigation_id) return;
          setJob(value); updateWorkspace(workspace); refreshRecent();
        }
      } catch (cause) { if (current) { setError(message(cause)); timer = window.setTimeout(() => { void poll(); }, 2000); } }
    };
    timer = window.setTimeout(() => { void poll(); }, 250);
    return () => { current = false; window.clearTimeout(timer); };
  }, [active, base, job?.job_id, projectId, refreshRecent, updateWorkspace]);
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
      void query(restoredQuery.current ? { ...restoredQuery.current, limit: resultPageLimit() } : undefined, 'events', 1, [], job);
    });
    return () => { current = false; };
  }, [projectId, investigationId, job?.investigation_id, job?.status]);

  function scope(): Scope {
    if (!workspaceId) throw new Error('An active page workspace is required to collect. Reopen this system and retry.');
    if (!processIds.length) throw new Error('Select at least one configured process.');
    const start = utc(collectionFrom); const end = utc(collectionTo);
    if (start >= end) throw new Error('From must be earlier than the exclusive To bound.');
    return { workspace_id: workspaceId, process_ids: processIds, from: start, to: end, transport };
  }
  function queryFilter(): Query['filter'] {
    const include = filter.include ?? []; const exclude = filter.exclude ?? [];
    if (include.length > 20 || exclude.length > 20 || [...include, ...exclude].some(term => Array.from(term).length > 512)) throw new Error('Use at most 20 include and 20 exclude terms, each at most 512 Unicode characters.');
    return filter;
  }
  function perProcessFilters(ids = job?.process_ids ?? []): Query['per_process_filters'] {
    const selected = Object.entries(processFilters).filter(([id]) => ids.includes(id));
    if (selected.some(([, value]) => (value.include?.length ?? 0) > 20 || (value.exclude?.length ?? 0) > 20 || [...(value.include ?? []), ...(value.exclude ?? [])].some(term => Array.from(term).length > 512))) throw new Error('Use at most 20 per-process terms, each at most 512 Unicode characters.');
    return Object.fromEntries(selected);
  }
  function queryDraft(): Query {
    const start = utc(from); const end = utc(to);
    if (start >= end) throw new Error('From must be earlier than the exclusive To bound.');
    const ids = job?.process_ids ?? [];
    if (!ids.length) throw new Error('Open a retained collection before filtering events.');
    return { process_ids: ids, from: start, to: end, filter: queryFilter(), per_process_filters: perProcessFilters(ids), limit: resultPageLimit(), cursor: null, lane };
  }
  async function applyFilters(draft: HistoricalFilterDraft): Promise<boolean> {
    if (!job) return false;
    const scopedFilters = Object.fromEntries(Object.entries(draft.per_process_filters).filter(([id]) => job.process_ids.includes(id)));
    const succeeded = await query({ process_ids: job.process_ids, from: draft.from, to: draft.to, filter: draft.filter, per_process_filters: scopedFilters, limit: resultPageLimit(), cursor: null, lane });
    if (!succeeded) return false;
    setFrom(draft.from); setTo(draft.to); setFilter(draft.filter ?? { include: [], exclude: [], include_mode: 'all', case_sensitive: true });
    setProcessFilters(scopedFilters);
    return true;
  }
  function toggleMarkedEvent(event: LogEvent, eventQuery: Query | null) {
    if (!eventQuery || event.project_id !== projectId || !eventQuery.process_ids.includes(event.process_id)) return;
    const key = `${projectId}:${event.event_id}`;
    if (!markedEvents[key] && selectedEventIds.size >= 100) { setError('Select at most 100 log entries for one pin.'); return; }
    setMarkedEvents(current => {
      if (current[key]) return Object.fromEntries(Object.entries(current).filter(([id]) => id !== key));
      return { ...current, [key]: { event, query: eventQuery } };
    });
  }
  function afterPinSaved(response: BookmarksWithPins) {
    if (!job || response.project_id !== projectId || response.investigation_id !== job.investigation_id) return;
    if (savedWorkspace) updateWorkspace({ ...savedWorkspace, revision: response.revision, pin_groups: response.pin_groups ?? [] });
    if (pinEntries === null) { setMarkedEvents({}); setModifyingPin(undefined); }
    else if (modifyingPin && !(response.pin_groups ?? []).some(pin => pin.id === modifyingPin.id)) setModifyingPin(undefined);
    setPinOpen(false); setViewedPin(undefined); setPinEntries(null); setPinChoiceOpen(false);
  }
  function viewPin(pin: PinGroupItem, bookmarks: BookmarksWithPins['items']) {
    if (!job || !savedWorkspace) return;
    const query: Query = { process_ids: job.process_ids, from: job.from, to: job.to,
      filter: { include: [], exclude: [], include_mode: 'all', case_sensitive: true },
      per_process_filters: {}, cursor: null, limit: resultPageLimit(), lane: 'events' };
    setViewedPin(pin); setPinEntries(pinSelectionFromBookmarks(pin, bookmarks, query, projectId)); setPinOpen(true);
  }
  function modifyPin(pin: PinGroupItem, entries: PinSelectionEntry[]) {
    if (!job) return;
    setModifyingPin(pin); setPinOpen(false); setViewedPin(undefined); setPinEntries(null);
    setMarkedEvents(Object.fromEntries(entries.map(entry => [`${projectId}:${entry.event.event_id}`, entry])));
    const filter = { include: [], exclude: [], include_mode: 'all' as const, case_sensitive: true };
    setFrom(job.from); setTo(job.to); setFilter(filter); setProcessFilters({});
    void query({ process_ids: job.process_ids, from: job.from, to: job.to, filter,
      per_process_filters: {}, limit: resultPageLimit(), cursor: null, lane: 'events' }, 'events');
    resultsPanel.current?.scrollIntoView({ block: 'start' });
  }
  function openSelectedPin(update = false) {
    setViewedPin(update ? modifyingPin : undefined); setPinEntries(null); setPinChoiceOpen(false); setPinOpen(true);
  }
  function resultPageLimit(size = pageSize) {
    const viewport = visibleBody.current?.querySelector<HTMLElement>('.virtual-logs');
    const height = viewport?.clientHeight ?? visibleBody.current?.clientHeight ?? 340;
    return size || Math.min(1000, Math.max(40, Math.ceil(height / logRowHeight) * 4));
  }
  function changePageSize(size: number) {
    setPageSize(size);
    // Pagination changes the displayed query, without applying unrelated edits
    // still waiting in the filter/time/process controls.
    if (queryScope) {
      const nextScope = { ...queryScope, limit: resultPageLimit(size), cursor: null };
      if (!visiblePaneIds.length) { setQueryScope(nextScope); return; }
      void query(layout === 'merged' ? visibleQuery(nextScope, visiblePaneIds) : nextScope, lane, 1, [], undefined, { scope: nextScope, visibleIds: shownProcessIds });
    }
  }
  function changeVisibleProcesses(ids: string[]) {
    if (!queryScope || loadingResults) return;
    const ordered = queryScope.process_ids.filter(id => ids.includes(id));
    if (layout === 'split' || !ordered.length) {
      queryVersion.current += 1; setLoadingResults(false); setError('');
      setShownProcessIds(ordered);
      if (!ordered.length) { setPrevious([]); setPageNumber(1); }
      return;
    }
    setShownProcessIds(ordered);
    void query(visibleQuery(queryScope, ordered), lane, 1, [], undefined, { scope: queryScope, visibleIds: ordered, previousVisibleIds: shownProcessIds });
  }
  function changeLayout(next: 'merged' | 'split') {
    setLayout(next);
    if (next === 'merged' && queryScope && visiblePaneIds.length && applied && !mergedScopeMatches) {
      void query(visibleQuery(queryScope, visiblePaneIds), lane, 1, [], undefined, { scope: queryScope, visibleIds: shownProcessIds });
    }
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
      const draft: Query = { process_ids: input.process_ids, from: input.from, to: input.to,
        filter: { include: [], exclude: [], include_mode: 'all', case_sensitive: true }, per_process_filters: {},
        limit: resultPageLimit(), cursor: null, lane: 'events' };
      const value = await write<Job>(`${base}/collections`, input);
      if (alive.current && value.project_id === projectId) {
        queryVersion.current += 1; contextVersion.current += 1;
        selectedInvestigation.current = value.investigation_id; automaticallyLoaded.current = null;
        createdDraft.current = { id: value.investigation_id, query: draft, layout };
        setFrom(input.from); setTo(input.to); setFilter(draft.filter!); setProcessFilters({});
        setJob(value); setSavedWorkspace(null); setOffline(null); setResults(null); setApplied(null); setQueryScope(null); setShownProcessIds(null); setMarkedEvents({}); setPinOpen(false); setPrevious([]); setDetails(null); setContext(null); setDeleteTarget(null); setLoadingResults(false); setLane('events');
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
        setJob(null); setSavedWorkspace(null); setOffline(null); restoredQuery.current = null;
        setResults(null); setApplied(null); setQueryScope(null); setShownProcessIds(null); setMarkedEvents({}); setPinOpen(false); setPrevious([]); setPageNumber(1); setDetails(null); setContext(null); setLoadingResults(false); setLane('events');
        onOpen();
      }
      refreshRecent();
    } catch (cause) { if (alive.current) setError(message(cause)); } finally { if (alive.current) setBusy(''); }
  }
  async function query(input?: Query, nextLane = lane, nextPage = 1, history: (string | null)[] = [], initialJob?: Job, view?: QueryView) {
    if (!job || job.investigation_id !== selectedInvestigation.current) return false;
    const investigation = job.investigation_id;
    const version = ++queryVersion.current; setLoadingResults(true); setError('');
    try {
      const start = input?.from ?? initialJob?.from ?? utc(from); const end = input?.to ?? initialJob?.to ?? utc(to);
      const ids = input?.process_ids ?? initialJob?.process_ids ?? job.process_ids;
      if (start >= end) throw new Error('From must be earlier than the exclusive To bound.');
      if (!ids.length) throw new Error('Select at least one configured process.');
      const body: Query = input ?? { process_ids: ids, from: start, to: end, filter: queryFilter(), per_process_filters: perProcessFilters(ids), limit: resultPageLimit(), cursor: null, lane: nextLane };
      const value = await write<Results>(`${base}/${offline ? 'bundle-investigations' : 'investigations'}/${encodeURIComponent(investigation)}/query`, body);
      if (alive.current && version === queryVersion.current && investigation === selectedInvestigation.current && value.project_id === projectId && value.items.every(item => item.project_id === projectId)) {
        setResults(current => ({ ...value, matched_count: value.matched_count ?? (input?.cursor ? current?.matched_count ?? null : null) }));
        setApplied(body); setLane(nextLane); setPrevious(history); setPageNumber(nextPage);
        setQueryScope(view?.scope ?? { ...body, cursor: null });
        setShownProcessIds(view?.visibleIds ?? null);
        return true;
      }
      return false;
    } catch (cause) {
      if (alive.current && version === queryVersion.current) {
        setError(message(cause));
        if (view && 'previousVisibleIds' in view) setShownProcessIds(view.previousVisibleIds ?? null);
      }
      return false;
    } finally { if (alive.current && version === queryVersion.current) setLoadingResults(false); }
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
  const displayedProcesses = offline ? [...new Map(offline.document.events.map(event => [event.process_id, { id: event.process_id, name: event.process_name_snapshot, server_id: event.server_id, host: event.server_name_snapshot }])).values()] : config.processes.map(process => ({ ...process, host: config.servers.find(server => server.id === process.server_id)?.name ?? '' }));
  const collectedProcesses = (job?.process_ids ?? []).map(id => {
    const process = displayedProcesses.find(item => item.id === id);
    const snapshot = (offline?.document.events ?? results?.items)?.find(event => event.process_id === id);
    return { id, name: snapshot?.process_name_snapshot ?? process?.name ?? id,
      host: snapshot?.server_name_snapshot ?? process?.host ?? '' };
  });
  return <section className="history-workspace" aria-label={t("Historical investigation")}>
    <div className="history-heading"><div><h2>{t("Historical investigation")}</h2><p className="muted">{systemLabel} {t("· Retained raw events, exact UTC bounds and literal filters")}</p></div><span className="pill">{offline ? t("Offline bundle | no SSH") : (plan?.demo_mode ?? job?.demo_mode ?? transport === 'local_demo') ? t("Synthetic local fixtures · no SSH") : plan || job ? t("Approved SSH/SFTP") : t("SSH/SFTP · configured sources")}</span></div>
    {error && !fullScreen && !details && <ErrorNotice>{systemLabel}: {t(error)}</ErrorNotice>}
    {pendingCleanup.map(id => <div className="notice history-warning" role="status" key={`${projectId}:${id}`}><span>{systemLabel}{t(": Collection")} <code>{id}</code> {t("was deleted. Cleanup of its captured files is still pending.")}</span><button title={t("Hide this collection cleanup notice.")} aria-label={t('Dismiss cleanup notice for collection {id}', { id })} onClick={() => setPendingCleanup(current => current.filter(value => value !== id))}>{t("Dismiss")}</button></div>)}
    <div className="history-setup">
      <fieldset className="history-processes" disabled={active || !!busy || !!offline}><legend>{offline ? t("Imported process snapshots") : t("Configured processes")}</legend>{!offline && <p className="muted">{t('Choose processes for the next collection. The current collection keeps its original process list.')}</p>}{displayedProcesses.length ? displayedProcesses.map(process => <label className="checkbox-label" title={process.id} key={`${projectId}:${process.id}`}><input type="checkbox" data-process-id={process.id} checked={processIds.includes(process.id)} onChange={event => { setProcessIds(current => event.target.checked ? [...current, process.id] : current.filter(id => id !== process.id)); invalidatePlan(); }} /> <span>{process.host}: {process.name}</span></label>) : <p className="muted">{t("This system has no configured processes.")}</p>}</fieldset>
      <div className="history-controls">
        <fieldset className="history-filter-fields" disabled={active || !!busy || !!offline}><legend>{t('Collection time range')}</legend><div className="form-grid">
          <UtcDateTimeInput bound="From" value={collectionFrom} onChange={value => { setCollectionFrom(value); invalidatePlan(); }} />
          <UtcDateTimeInput bound="To" value={collectionTo} onChange={value => { setCollectionTo(value); invalidatePlan(); }} />
        </div><p className="muted">{t('Choose the UTC range to collect. The start is inclusive and the end is exclusive. Event table filters apply only to retained data.')}</p></fieldset>
        {historicalDemoEnabled && <label className="history-transport">{t("Collection transport")}<select aria-label={t("Collection transport")} value={transport} disabled={active || !!busy} onChange={event => { setTransport(event.target.value as 'local_demo' | 'ssh'); invalidatePlan(); }}><option value="local_demo">{t("Synthetic local fixtures")}</option><option value="ssh">{t("Approved SSH/SFTP")}</option></select></label>}<div className="history-plan-actions"><button title={t("Preview the sources and scan budget for this collection.")} onClick={() => { void preview(); }} disabled={!!busy || active || archived || !workspaceId || !!offline}>{t("Preview collection plan")}</button><button title={t("Collect logs for the selected processes and UTC range.")} className="primary" onClick={() => { void start(); }} disabled={!!busy || active || archived || !workspaceId || !!offline}>{t("Collect sources")}</button><span role="status">{t(busy)}</span></div>{archived && <p className="muted">{t("Archived system: retained collections remain readable.")}</p>}
      </div>
    </div>
    {plan && <section className="history-plan" aria-label={t("Collection plan")}><div className="panel-heading"><h3>{t("Collection plan ·")} {config.project.name}</h3><strong>{plan.source_count} {t("sources · approximately")} {bytes(plan.estimated_bytes)}</strong></div>{plan.demo_mode ? <p className="demo-label">{t("SYNTHETIC LOCAL FIXTURES")}</p> : <p className="muted">{t("Approved SSH/SFTP · read-only remote collection")}</p>}<p>{t("Scans retain raw events for later refiltering and source context. Candidate date coverage is unproven until scanned.")}</p>{plan.warnings.map((warning, index) => <p className="history-warning" key={index}>{warning}</p>)}<ul>{plan.sources.map(source => <li key={`${projectId}:${source.source_revision_id}`}><code>{source.remote_path}</code><span>{source.process_id} · {source.kind} · {bytes(source.estimated_bytes)}</span></li>)}</ul></section>}
    {recent.length > 0 && <label className="history-recent">{t("Open your retained collection")}<select aria-label={t("Open your retained collection")} value={job?.investigation_id ?? ''} disabled={!!busy || active} onChange={event => { if (event.target.value) onOpen(event.target.value); }}><option value="">{t("Choose a collection…")}</option>{recent.map(item => <option key={`${projectId}:${item.investigation_id}`} value={item.investigation_id}>{item.investigation_id.slice(0, 12)} · {t(item.status)} · {item.event_count} {t("events")}</option>)}</select></label>}
    {job && <section className="history-status" aria-label={t("Collection progress")}><div className="panel-heading"><h3>{config.project.name} {t("· Collection")} <span data-testid="collection-state">{t(job.status)}</span></h3>{active ? <button title={t("Request cancellation of this collection.")} onClick={() => { void cancel(); }} disabled={!!busy || job.status === 'cancel_requested'}>{t("Cancel collection")}</button> : <button title={t("Review deletion of this retained collection.")} className="danger-button" onClick={() => setDeleteTarget(job)} disabled={!!busy || !!offline}>{t("Delete collection")}</button>}<code data-testid="investigation-id">{job.investigation_id}</code></div><progress aria-label={t("Scanned sources")} value={job.scanned_sources} max={Math.max(job.source_count, 1)} /><p aria-live="polite">{job.scanned_sources} / {job.source_count} {t("sources scanned ·")} {job.event_count} {t("indexed events ·")} {job.parse_issue_count} {t("parse issues ·")} {bytes(job.downloaded_bytes)} {t("read ·")} {bytes(job.expanded_bytes)} {t("expanded")}</p><p className="coverage-label">{t("Coverage:")} <strong>{t(job.coverage_status)}</strong>{t(". Observed first/last timestamps do not establish continuous coverage.")}</p>{job.errors.map((issue, index) => <p className="history-warning" key={index}>{typeof issue === 'string' ? issue : JSON.stringify(issue)}</p>)}<details><summary title={t("Show coverage and errors for each collected source.")}>{t("Per-source coverage and failures")}</summary><div className="coverage-table">{job.coverage.map(source => <div key={`${projectId}:${source.source_revision_id}`}><code>{source.remote_path}</code><span>{source.process_id} · {t(source.status)} · {source.events} {t("events ·")} {bytes(source.bytes)} {t("| byte [")}{source.byte_start}, {source.byte_end})</span>{source.checksum && <code>{t("SHA-256")} {source.checksum}</code>}{source.error_code && <strong>{source.error_code}</strong>}</div>)}</div></details></section>}
    <InvestigationTools projectId={projectId} systemName={config.project.name} investigationId={job?.investigation_id} workspace={savedWorkspace} offline={offline} queryDraft={queryDraft} layout={layout} onWorkspace={updateWorkspace} onExpired={afterCacheExpired} onInspect={(event, input) => { void inspect(event, input); }} onOpen={id => { refreshRecent(); onOpen(id); }} onViewPin={viewPin} />

    <dialog open ref={resultsPanel} className={`history-results ${fullScreen ? 'history-results-fullscreen' : ''}`} role={fullScreen ? 'dialog' : 'region'} aria-label={t("Event results")} onCancel={event => { event.preventDefault(); setFullScreen(false); }}>
    <div className="history-results-heading">
      <div className="workspace-tabs" aria-label={t("Result lane")}><button title={t("Show retained events with usable UTC timestamps.")} className={lane === 'events' ? 'active' : ''} aria-pressed={lane === 'events'} onClick={() => { void query(undefined, 'events'); }} disabled={!job || loadingResults}>{t("Timestamped events")}</button><button title={t("Show retained records with missing or unusable timestamps.")} className={lane === 'diagnostic' ? 'active' : ''} aria-pressed={lane === 'diagnostic'} onClick={() => { void query(undefined, 'diagnostic'); }} disabled={!job || loadingResults}>{t("Diagnostic lane")}{job ? ` (${job.parse_issue_count})` : ''}</button></div>
      <div className="history-table-actions">
        <button type="button" title={t("Edit time and literal filters for the retained logs.")} onClick={() => { setError(''); setFiltersOpen(true); }} disabled={!job || loadingResults}>{t('Filters')}</button>
        <button type="button" title={t("Save the selected log entries as a described pin.")} aria-label={t('Pin')} disabled={!job || !savedWorkspace || !selectedEventIds.size || loadingResults} onClick={() => { if (modifyingPin) setPinChoiceOpen(true); else openSelectedPin(); }}>{t('Pin')}{selectedEventIds.size > 0 && <> ({selectedEventIds.size})</>}</button>
        {selectedEventIds.size > 0 && <button type="button" title={t("Unmark all selected log entries.")} onClick={() => setMarkedEvents({})}>{t('Clear selection')}</button>}
        <label>{t("Result layout")}<select aria-label={t("Result layout")} value={layout} disabled={loadingResults} onChange={event => changeLayout(event.target.value as 'merged' | 'split')}><option value="merged">{t("Merged")}</option><option value="split">{t("Separate process panes")}</option></select></label>
        <ProcessVisibilityMenu processOptions={paneProcesses} visibleProcessIds={visiblePaneIds} disabled={loadingResults} onChange={changeVisibleProcesses} />
        <label>{t('Pane arrangement')}<select aria-label={t('Pane arrangement')} value={paneColumns} disabled={layout === 'merged' || loadingResults} onChange={event => setPaneColumns(Number(event.target.value) as 1 | 2 | 3 | 4)}><option value={1}>{t('Stacked')}</option><option value={2}>{t('2 columns')}</option><option value={3}>{t('3 columns')}</option><option value={4}>{t('4 columns')}</option></select></label>
        <details className="log-column-menu" ref={columnMenu} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false; }} onKeyDown={event => {
          if (event.key === 'Escape' && event.currentTarget.open) {
            event.preventDefault(); event.stopPropagation(); event.currentTarget.open = false;
            event.currentTarget.querySelector('summary')?.focus();
          }
        }}><summary title={t("Choose which log metadata columns to show.")}>{t("Columns")}</summary><fieldset><legend>{t("Visible columns")}</legend>
          <label className="checkbox-label"><input type="checkbox" checked={columns.timestamp} onChange={event => setColumns(current => ({ ...current, timestamp: event.target.checked }))} />{t("Event time UTC")}</label>
          <label className="checkbox-label"><input type="checkbox" checked={columns.process} onChange={event => setColumns(current => ({ ...current, process: event.target.checked }))} />{t("Process")}</label>
          <label className="checkbox-label"><input type="checkbox" checked={columns.host} onChange={event => setColumns(current => ({ ...current, host: event.target.checked }))} />{t("Host")}</label>
          <label className="checkbox-label"><input type="checkbox" checked disabled />{t("Log entry")}</label>
          <button type="button" title={t("Show the UTC time, process and host columns.")} onClick={() => setColumns({ timestamp: true, process: true, host: true })}>{t("Show all columns")}</button>
        </fieldset></details>
        <button type="button" title={fullScreen ? t("Restore the results to the page layout.") : t("Expand the results to fill the browser window.")} ref={fullScreenButton} onClick={() => setFullScreen(current => !current)} aria-pressed={fullScreen}><Icon kind={fullScreen ? 'collapse' : 'expand'} />{fullScreen ? t("Exit full screen") : t("Full screen")}</button>
      </div>
    </div>
    {modifyingPin && <p className="history-time-help" role="status">{t('Modifying pin selection')}: {modifyingPin.description || t('Pin · {count} logs', { count: modifyingPin.bookmark_ids.length })} <button type="button" title={t("Cancel changes to this pin selection and clear the marks.")} onClick={() => { setModifyingPin(undefined); setMarkedEvents({}); }}>{t('Cancel modification')}</button></p>}
    {error && fullScreen && !details && <ErrorNotice>{systemLabel}: {t(error)}</ErrorNotice>}
    {results && <div className="history-result-summary" role="status"><span>{config.project.name} · {projectId}</span>{layout === 'merged' && <strong data-testid="match-count">{!visiblePaneIds.length ? 0 : mergedScopeMatches ? results.matched_count ?? t("Count unknown") : t("Count unknown")} {lane === 'diagnostic' ? t("diagnostic records") : t("matches")}</strong>}<span>{layout === 'merged' && <>{mergedEvents.length} {t("rows on page")} {pageNumber} </>}{t("· snapshot")} {results.source_snapshot_revision}{results.partial ? t(" · Partial coverage") : ''}</span>{loadingResults && <span>{t("Applying query…")}</span>}</div>}
    {job && <p className="history-time-help">{t('Collected UTC [')}{formatUtcTimestamp(job.from)}, {formatUtcTimestamp(job.to)})</p>}
    {job && <div className="history-time-help" role="group" aria-label={t('Collected processes')}><strong>{t('Collected processes')}:</strong> {collectedProcesses.map((process, index) => <span key={`${projectId}:${process.id}`} title={process.id}>{index > 0 ? ', ' : ''}{process.host ? `${process.host}: ` : ''}{process.name}</span>)}</div>}
    {applied && <p className="history-time-help">{t("Displayed UTC [")}{formatUtcTimestamp(applied.from)}, {formatUtcTimestamp(applied.to)}) · {applied.filter?.include?.length ?? 0} {t("include /")} {applied.filter?.exclude?.length ?? 0} {t("exclude terms ·")} {applied.filter?.case_sensitive ? t("Case sensitive") : t("Unicode casefold")}{t(". Edit controls and apply to replace this query.")}</p>}
    {lane === 'diagnostic' && <p className="history-time-help">{t("These records have no usable event timestamp. The process predicate applies; oversized previews remain visible when their literal match is unknown. No time is invented and these records are excluded from timestamped match totals.")}</p>}

    <div ref={visibleBody} className="history-result-body" aria-busy={loadingResults}>{layout === 'split' && results && applied && queryScope ? <><HistoricalProcessPanes projectId={projectId} systemName={config.project.name} queryPath={`${base}/${offline ? 'bundle-investigations' : 'investigations'}/${encodeURIComponent(job?.investigation_id ?? '')}/query`} query={queryScope} seedQuery={applied} seed={results} columns={columns} selectedEventIds={selectedEventIds} onToggleSelection={toggleMarkedEvent} processOptions={paneProcesses} visibleProcessIds={visiblePaneIds} paneColumns={paneColumns} onInspect={(event, input) => { void inspect(event, input); }} />{!visiblePaneIds.length && <EmptyState title={t('No processes selected')}>{t('Use Show process to turn on one or more processes.')}</EmptyState>}</> : queryScope && !visiblePaneIds.length ? <EmptyState title={t('No processes selected')}>{t('Use Show process to turn on one or more processes.')}</EmptyState> : results ? mergedEvents.length ? <VirtualLog columns={columns} highlights={applied} selectedEventIds={selectedEventIds} onToggleSelection={event => toggleMarkedEvent(event, applied)} events={mergedEvents} label={`${systemLabel} · ${t(lane === 'events' ? 'Timestamped events' : 'Diagnostic lane')}`} onInspect={event => { void inspect(event); }} /> : <EmptyState title={results.availability === 'unavailable' ? t("Retained source data unavailable") : t("No matching records")}>{results.availability === 'unavailable' ? t("The source cache expired or was explicitly removed. Notes and pinned bookmark context remain available. Recollection requires an explicit action.") : job?.event_count ? t("Captured data is available. Change the literal filter, time interval or result lane.") : t("No indexed data is available. Review source coverage and collection errors.")}</EmptyState> : <EmptyState title={loadingResults ? t("Loading timestamped events") : active ? t("Collection in progress") : job ? t("Indexed data is ready to query") : t("Inspect configured log history")}>{loadingResults ? t("Loading retained events for the selected collection.") : active ? t("Timestamped events load automatically when collection finishes. You can also query the data collected so far.") : job ? t("Apply a literal filter or open the diagnostic lane to query this retained collection.") : t("Select configured processes, set UTC bounds, then collect. Preview the bounded source plan if needed.")}</EmptyState>}</div>
    <div className="history-results-footer">
        <label>{t("Rows")}<select aria-label={t("Rows")} value={pageSize} disabled={loadingResults} onChange={event => changePageSize(Number(event.target.value))}><option value={0}>{t("Viewport")}</option><option value={10}>10</option><option value={50}>50</option><option value={200}>200</option></select></label>
      {layout === 'merged' && results && applied && <div className="history-pagination"><button title={t("Show the previous page of matching events.")} disabled={!previous.length || loadingResults || !visiblePaneIds.length || !mergedScopeMatches} onClick={() => { const history = previous.slice(0, -1); void query({ ...applied, cursor: previous.at(-1) ?? null }, lane, pageNumber - 1, history, undefined, { scope: queryScope ?? applied, visibleIds: shownProcessIds }); }}>{t("Previous result page")}</button><span>{t("Pagination is bound to this collection, filter and source snapshot. Each page keeps the browser cache bounded.")}</span><button title={t("Show the next page of matching events.")} disabled={!results.next_cursor || loadingResults || !visiblePaneIds.length || !mergedScopeMatches} onClick={() => { void query({ ...applied, cursor: results.next_cursor }, lane, pageNumber + 1, [...previous, applied.cursor ?? null], undefined, { scope: queryScope ?? applied, visibleIds: shownProcessIds }); }}>{t("Next result page")}</button></div>}
    </div>
    </dialog>
    {filtersOpen && job && <HistoricalFiltersDialog initial={{ from, to, filter, per_process_filters: processFilters }} processOptions={collectedProcesses} bounds={{ from: job.from, to: job.to }} busy={loadingResults} error={error} onApply={applyFilters} onClose={() => { setFiltersOpen(false); setError(''); }} />}
    {pinChoiceOpen && <Modal title={t('Update the pin or create a new one?')} onClose={() => setPinChoiceOpen(false)}><div className="form-actions"><button type="button" title={t("Close this choice and keep the selected log entries.")} onClick={() => setPinChoiceOpen(false)}>{t('Cancel')}</button><button type="button" title={t("Create a separate pin from the selected log entries.")} onClick={() => openSelectedPin(false)}>{t('Create a new pin')}</button><button type="button" title={t("Replace the existing pin with the selected log entries.")} className="primary" onClick={() => openSelectedPin(true)}>{t('Update the pin')}</button></div></Modal>}
    {pinOpen && job && savedWorkspace && <InvestigationPinDialog key={`${projectId}:${job.investigation_id}:${viewedPin?.id ?? 'new'}`} projectId={projectId} systemName={config.project.name} investigationId={job.investigation_id} workspace={savedWorkspace} offline={!!offline} entries={pinEntries ?? Object.values(markedEvents)} pin={viewedPin} allowDelete={!!viewedPin && pinEntries !== null} replaceSelection={!!viewedPin && pinEntries === null} onModify={savedWorkspace.availability !== 'unavailable' ? modifyPin : undefined} onSaved={afterPinSaved} onClose={() => setPinOpen(false)} />}
    {deleteTarget && <Modal title={t("Delete retained collection")} onClose={() => { if (!busy) setDeleteTarget(null); }}><p className="target-system">{t("System:")} <strong>{config.project.name}</strong><code>{projectId}</code></p><p>{t("Collection:")} <code>{deleteTarget.investigation_id}</code></p><p>{t("Permanently delete this retained collection and its indexed events, source context and captured-source downloads. Other collections and remote log files remain available.")}</p><p>{t("This cannot be undone.")}</p>{error && <ErrorNotice>{t(error)}</ErrorNotice>}<div className="form-actions"><button title={t("Close this dialog and keep the retained collection.")} disabled={!!busy} onClick={() => setDeleteTarget(null)}>{t("Keep collection")}</button><button title={t("Permanently delete this collection and its captured data.")} className="danger-button" disabled={!!busy} onClick={() => { void removeCollection(); }}>{busy === 'Deleting collection' ? t("Deleting…") : t("Delete collection")}</button></div></Modal>}
    {details && <Modal title={t("Event provenance and source context")} onClose={() => { setDetails(null); contextVersion.current += 1; }}><p className="target-system">{t("System:")} <strong>{config.project.name}</strong><code>{projectId}</code></p><p>{details.server_name_snapshot} / {details.process_name_snapshot}</p>{error && <ErrorNotice>{t(error)}</ErrorNotice>}<pre className="event-raw">{details.raw_line}</pre>{details.parse_status === 'oversized_line' && <p className="history-warning">{t("This line exceeded the configured limit. The displayed text is a bounded preview; its full literal match is unknown. The captured source download preserves the original bytes when complete.")}</p>}<dl className="provenance"><div><dt>{t("Event ID")}</dt><dd><code>{details.event_id}</code></dd></div><div><dt>{t("UTC / parse status")}</dt><dd>{details.timestamp_utc ? formatUtcTimestamp(details.timestamp_utc) : t("Unknown timestamp")} · {t(details.parse_status)}</dd></div><div><dt>{t("Original timestamp")}</dt><dd><code>{details.timestamp_original ?? t("Not parsed")}</code></dd></div><div><dt>{t("Source revision")}</dt><dd><code>{details.source.source_revision_id}</code></dd></div><div><dt>{t("Original path / member")}</dt><dd><code>{details.source.remote_path}{details.source.archive_member ? ` :: ${t('Archive member {name} (ordinal {ordinal})', { name: details.source.archive_member, ordinal: details.source.member_ordinal ?? '?' })}` : ''}</code></dd></div><div><dt>{t("Physical position")}</dt><dd>{t("Line")} {details.source.line_number ?? t("unknown")} {t("· byte [")}{details.source.byte_start}, {details.source.byte_end})</dd></div><div><dt>{t("Content SHA-256")}</dt><dd><code>{details.source.content_sha256}</code></dd></div></dl><SourceCoverageDetails value={sourceDetails} /><div className="history-context-heading"><h3>{t("Source-order context")}</h3><button title={t("Download the retained original bytes of this log source.")} disabled={!!offline} onClick={() => { void download(details); }}>{t("Download captured source")}</button><button title={t("Copy the original log line with its system and process labels.")} onClick={() => { void navigator.clipboard.writeText(`[System: ${systemLabel}] [${details.server_name_snapshot}/${details.process_name_snapshot}] ${details.raw_line}`).then(() => setCopied(true)).catch(() => setError('Clipboard access failed. Select and copy the original text above.')); }}>{copied ? t("Copied") : t("Copy event text")}</button></div><p className="muted">{t("Five physical lines before/after in the same source member, independent of the merged ordering. Context does not increase match totals.")}</p>{contextBusy && <p role="status">{t("Loading source context…")}</p>}{savedWorkspace && detailsQuery && job && <EventBookmark key={`${projectId}:${job.investigation_id}:${details.event_id}`} projectId={projectId} investigationId={job.investigation_id} offline={!!offline} workspace={savedWorkspace} event={details} query={detailsQuery} onWorkspace={updateWorkspace} />}<ol className="source-context">{context?.items.map(item => <li className={item.is_anchor ? 'context-anchor' : ''} key={`${projectId}:${item.event.event_id}`}><div><strong>{item.is_anchor ? t("Selected event") : t("Context")}</strong><span>{t("line")} {item.event.source.line_number ?? '?'}{item.outside_time_bounds ? t(" · Outside time bounds") : ''}{item.matches_filter === null ? t(" | Literal match unknown (truncated record)") : !item.matches_filter ? t(" · Outside literal filter") : ''}{item.event.timestamp_utc === null ? t(" · Unknown timestamp") : ''}</span></div><pre>{item.event.raw_line}</pre></li>)}</ol></Modal>}
  </section>;
}

function SourceCoverageDetails({ value }: { value: SourceDetails | null }) {
  const { t } = useI18n();
  return value && <section className="source-coverage-details" aria-label={t("Captured source coverage")}><h3>{t("Captured source coverage")}</h3><dl><div><dt>{t("Source status")}</dt><dd>{t(value.status)}{value.error_code ? ` · ${value.error_code}` : ''}</dd></div><div><dt>{t("Observed event range UTC")}</dt><dd>{value.observed_from ? formatUtcTimestamp(value.observed_from) : t("Unknown")} → {value.observed_to ? formatUtcTimestamp(value.observed_to) : t("Unknown")}</dd></div><div><dt>{t("Retained index")}</dt><dd>{value.retained_event_count} {t("events ·")} {value.parse_issue_count} {t("parse issues")}</dd></div><div><dt>{t("Original bytes")}</dt><dd>{value.raw_bytes_available ? t("Available") : t("Unavailable")} · {bytes(value.downloaded_bytes)} {t("read ·")} {bytes(value.expanded_bytes)} {t("expanded")}</dd></div><div><dt>{t("Captured byte ranges")}</dt><dd><code>{JSON.stringify(value.captured_ranges)}</code></dd></div></dl>{value.limitations.map((limitation, index) => <p className="history-warning" key={index}>{limitation}</p>)}<p className="muted">{t("Observed timestamps and scanned boundaries do not prove continuous coverage.")}</p></section>;
}
