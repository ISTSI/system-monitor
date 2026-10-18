import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { message, request } from '../api/client';
import type { components } from '../api/schema';
import { useI18n } from '../i18n';
import { VirtualLog } from './HistoricalLogTable';

type Query = components['schemas']['HistoricalQueryInput'];
type Results = components['schemas']['HistoricalQueryResponse'];
type LogEvent = Results['items'][number];
type PageRequest = { id: string; query: Query; page: number; previous: (string | null)[] };
type Pane = {
  query: Query;
  response: Results | null;
  events: LogEvent[];
  page: number;
  previous: (string | null)[];
  busy: boolean;
  error: string;
  retry: PageRequest | null;
};

export type HistoricalProcessPanesProps = {
  projectId: string;
  systemName: string;
  queryPath: string;
  query: Query;
  seed: Results;
  seedQuery: Query;
  columns: { timestamp: boolean; process: boolean; host: boolean };
  processOptions: { id: string; name: string; host: string }[];
  visibleProcessIds: string[];
  paneColumns: 1 | 2 | 3 | 4;
  onInspect: (event: LogEvent, query: Query) => void;
  selectedEventIds?: ReadonlySet<string>;
  onToggleSelection?: (event: LogEvent, query: Query) => void;
  selectionDisabled?: boolean;
};

function processQuery(query: Query, id: string): Query {
  const ownFilter = query.per_process_filters?.[id];
  return { ...query, process_ids: [id], per_process_filters: ownFilter ? { [id]: ownFilter } : {}, cursor: null };
}

function initialPanes(query: Query, seed: Results, seedQuery: Query): Record<string, Pane> {
  // A last merged page also has no next cursor, but cannot seed complete panes.
  const completeSeed = !seedQuery.cursor && !seed.next_cursor;
  const singleFirstPage = !seedQuery.cursor && seedQuery.process_ids.length === 1 && seedQuery.limit === query.limit;
  return Object.fromEntries(query.process_ids.map(id => {
    const ownQuery = processQuery(query, id);
    // A complete subset query proves nothing about another applied process.
    // Compare only this process's predicates; other per-process filters cannot
    // change the rows in this pane. Complete seeds may use a different limit
    // when all of this process's events still fit the requested pane page.
    const signature = (value: Query) => JSON.stringify([value.from, value.to, value.filter ?? null, value.per_process_filters?.[id] ?? null, value.lane, value.correlation ?? null]);
    const compatible = seedQuery.process_ids.includes(id) && signature(query) === signature(seedQuery);
    const seedEvents = seed.items.filter(event => event.process_id === id);
    const reusable = compatible && ((completeSeed && seedEvents.length <= query.limit) || singleFirstPage);
    const events = reusable ? seedEvents : [];
    const response = reusable ? {
      ...seed,
      items: events,
      matched_count: singleFirstPage ? seed.matched_count : seed.matched_count === null ? null : events.length,
      next_cursor: singleFirstPage ? seed.next_cursor : null,
    } : null;
    return [id, { query: ownQuery, response, events, page: 1, previous: [], busy: !reusable, error: '', retry: null } satisfies Pane];
  }));
}

export default function HistoricalProcessPanes(props: HistoricalProcessPanesProps) {
  // Filters, source snapshots and scope replace the pane cache. Presentation and
  // the merged cursor do not: hiding a pane preserves its rows and scroll.
  const identity = JSON.stringify([props.projectId, props.queryPath, { ...props.query, cursor: null }, props.seed.source_snapshot_revision]);
  return <ProcessPaneQuery key={identity} {...props} />;
}

function ProcessPaneQuery({ projectId, systemName, queryPath, query, seed, seedQuery, columns, processOptions, visibleProcessIds, paneColumns, onInspect, selectedEventIds, onToggleSelection, selectionDisabled }: HistoricalProcessPanesProps) {
  const { t } = useI18n();
  const [panes, setPanes] = useState(() => initialPanes(query, seed, seedQuery));
  const initial = useRef({ projectId, queryPath, query, seed, panes });
  const load = useRef<((task: PageRequest) => void) | null>(null);

  useEffect(() => {
    const snapshot = initial.current;
    let active = true;
    let running = 0;
    const queued: { task: PageRequest; version: number }[] = [];
    const controllers = new Set<AbortController>();
    const versions = new Map<string, number>();

    function pump() {
      while (active && running < 2 && queued.length) {
        const { task, version } = queued.shift()!;
        if (version !== versions.get(task.id)) continue;
        running += 1;
        const controller = new AbortController();
        controllers.add(controller);
        const current = () => active && version === versions.get(task.id);
        void request<Results>(snapshot.queryPath, {
          method: 'POST', body: JSON.stringify(task.query),
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]),
        }).then(value => {
          if (!current()) return;
          if (value.project_id !== snapshot.projectId || value.items.some(event => event.project_id !== snapshot.projectId || event.process_id !== task.id || (task.query.lane === 'diagnostic' ? event.timestamp_utc !== null : event.timestamp_utc === null))) {
            throw new Error('The returned events do not match this process pane. Retry the query.');
          }
          if (value.source_snapshot_revision !== snapshot.seed.source_snapshot_revision) {
            throw new Error('The retained source snapshot changed. Apply the query again.');
          }
          setPanes(previous => {
            const old = previous[task.id];
            const response = { ...value, matched_count: value.matched_count ?? (task.query.cursor ? old.response?.matched_count ?? null : null) };
            return { ...previous, [task.id]: { query: task.query, response, events: value.items, page: task.page, previous: task.previous, busy: false, error: '', retry: null } };
          });
        }).catch((cause: unknown) => {
          if (current()) setPanes(previous => ({ ...previous, [task.id]: { ...previous[task.id], busy: false, error: message(cause), retry: task } }));
        }).finally(() => {
          controllers.delete(controller);
          running -= 1;
          pump();
        });
      }
    }

    const enqueue = (task: PageRequest) => {
      if (!active) return;
      const version = (versions.get(task.id) ?? 0) + 1;
      versions.set(task.id, version);
      setPanes(previous => ({ ...previous, [task.id]: { ...previous[task.id], busy: true, error: '', retry: task } }));
      queued.push({ task, version });
      pump();
    };
    load.current = enqueue;
    for (const [id, pane] of Object.entries(snapshot.panes)) {
      if (!pane.response) enqueue({ id, query: pane.query, page: 1, previous: [] });
    }
    return () => {
      active = false;
      load.current = null;
      queued.length = 0;
      for (const controller of controllers) controller.abort();
    };
  }, []);

  const visible = new Set(visibleProcessIds);
  const visibleCount = query.process_ids.filter(id => visible.has(id)).length;
  return <div className="history-split" style={{ '--history-pane-columns': visibleCount === 1 ? 1 : paneColumns } as CSSProperties}>
    {query.process_ids.map(id => {
      const pane = panes[id];
      const option = processOptions.find(process => process.id === id);
      const name = pane.events[0]?.process_name_snapshot ?? option?.name ?? id;
      const host = pane.events[0]?.server_name_snapshot ?? option?.host ?? '';
      const hidden = !visible.has(id);
      return <section key={`${projectId}:${id}`} data-process-id={id} aria-label={`${systemName} · ${name}`} aria-busy={pane.busy} hidden={hidden} style={hidden ? { display: 'none' } : undefined}>
        <div className="history-process-heading"><h3>{systemName} · {name}</h3><span>{host} · {t('{count} rows on this page', { count: pane.events.length })}</span></div>
        <div className="history-pane-status" role="status">
          {pane.busy ? t('Loading process results…') : pane.response && <>{pane.response.matched_count ?? t('Count unknown')} {t(query.lane === 'diagnostic' ? 'diagnostic records' : 'matches')} · {t('Page {page}', { page: pane.page })}{pane.response.partial ? t(' · Partial coverage') : ''}</>}
        </div>
        {pane.error && <div className="notice error" role="alert"><span>{t(pane.error)}</span><button type="button" aria-label={t('Retry {name}', { name })} disabled={pane.busy} onClick={() => { if (pane.retry) load.current?.(pane.retry); }}>{t('Retry')}</button></div>}
        {pane.response && pane.events.length === 0 && <p className="history-pane-empty">{t(pane.response.availability === 'unavailable' ? 'Retained source data unavailable' : 'No matching records')}</p>}
        <VirtualLog columns={columns} highlights={pane.query} events={pane.events} label={`${systemName} (${projectId}) · ${id}`} compact onInspect={event => onInspect(event, pane.query)} selectedEventIds={selectedEventIds} onToggleSelection={onToggleSelection ? event => onToggleSelection(event, pane.query) : undefined} selectionDisabled={selectionDisabled} />
        <div className="history-pane-pagination">
          <button type="button" aria-label={t('Previous page for {name}', { name })} disabled={!pane.previous.length || pane.busy} onClick={() => {
            load.current?.({ id, query: { ...pane.query, cursor: pane.previous.at(-1) ?? null }, page: pane.page - 1, previous: pane.previous.slice(0, -1) });
          }}>{t('Previous page')}</button>
          <span>{t('Page {page}', { page: pane.page })}</span>
          <button type="button" aria-label={t('Next page for {name}', { name })} disabled={!pane.response?.next_cursor || pane.busy} onClick={() => {
            load.current?.({ id, query: { ...pane.query, cursor: pane.response?.next_cursor ?? null }, page: pane.page + 1, previous: [...pane.previous, pane.query.cursor ?? null] });
          }}>{t('Next page')}</button>
        </div>
      </section>;
    })}
  </div>;
}
