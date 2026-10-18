import { useI18n } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { message, request, write } from '../api/client';
import type { Bookmarks, HistoricalEvent, HistoricalQuery, InvestigationWorkspace, OfflineInvestigation, Trace } from '../investigation';
import type { BookmarksWithPins, PinGroupItem } from '../investigationPins';
import { ErrorNotice, Modal } from './Common';
import { formatUtcTimestamp } from '../utcDateTime';
import BundleTransfer from './BundleTransfer';

export default function InvestigationTools({ projectId, systemName, investigationId, workspace, offline, queryDraft, layout, onWorkspace, onInspect, onOpen, onExpired, onViewPin }: {
  projectId: string; systemName: string; investigationId?: string; workspace: InvestigationWorkspace | null;
  offline: OfflineInvestigation | null; queryDraft: () => HistoricalQuery; layout: 'merged' | 'split';
  onWorkspace: (value: InvestigationWorkspace) => void; onInspect: (event: HistoricalEvent, query: HistoricalQuery) => void; onOpen: (id: string) => void; onExpired: () => void;
  onViewPin: (pin: PinGroupItem, bookmarks: Bookmarks['items']) => void;
}) {
  const { t } = useI18n();
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const path = investigationId ? `${base}/${offline ? 'bundle-investigations' : 'investigations'}/${encodeURIComponent(investigationId)}` : '';
  const [title, setTitle] = useState(''); const [notes, setNotes] = useState(''); const [pinned, setPinned] = useState(false);
  const [bookmarks, setBookmarks] = useState<BookmarksWithPins | null>(null);
  const [field, setField] = useState('request_id'); const [value, setValue] = useState('');
  const [mode, setMode] = useState<'exact' | 'literal'>('exact');
  const [trace, setTrace] = useState<Trace | null>(null); const [traceQuery, setTraceQuery] = useState<HistoricalQuery | null>(null);
  const [busy, setBusy] = useState(''); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [expiring, setExpiring] = useState(false);
  const alive = useRef(true); const version = useRef(0);
  useEffect(() => { alive.current = true; return () => { alive.current = false; version.current += 1; }; }, []);
  useEffect(() => {
    setTitle(workspace?.title ?? offline?.document.selection.title ?? ''); setNotes(workspace?.notes ?? offline?.document.selection.notes ?? ''); setPinned(workspace?.pinned ?? false);
  }, [workspace?.investigation_id, workspace?.title, workspace?.notes, workspace?.pinned, offline?.investigation_id]);
  useEffect(() => {
    version.current += 1; setTrace(null); setTraceQuery(null); setError(''); setNotice(''); setBusy(''); setExpiring(false);
  }, [path, projectId, investigationId, offline]);
  useEffect(() => { setBookmarks(null); }, [path]);
  useEffect(() => {
    let current = true;
    if (!path) return;
    void request<BookmarksWithPins>(`${path}/bookmarks`).then(result => { if (alive.current && current && result.project_id === projectId && result.investigation_id === investigationId) setBookmarks(result); }).catch((cause: unknown) => { if (alive.current && current) setError(message(cause)); });
    return () => { current = false; };
  }, [path, projectId, investigationId, offline, workspace?.revision]);
  async function save() {
    if (!workspace || !path) return;
    const current = version.current; setBusy('Saving workspace'); setError(''); setNotice('');
    try {
      const query = queryDraft();
      const result = await write<InvestigationWorkspace>(`${path}/workspace`, { expected_revision: workspace.revision, title, notes, pinned, process_ids: query.process_ids, from: query.from, to: query.to, filter: query.filter, per_process_filters: query.per_process_filters, layout }, 'PATCH');
      if (alive.current && current === version.current && result.project_id === projectId && result.investigation_id === investigationId) { onWorkspace(result); setNotice('Workspace saved. This link reopens your retained data without connecting to hosts.'); }
    } catch (cause) { if (alive.current && current === version.current) setError(message(cause)); }
    finally { if (alive.current && current === version.current) setBusy(''); }
  }
  async function search(cursor?: string | null) {
    if (!path) return;
    const current = version.current; setBusy('Searching retained correlation'); setError('');
    try {
      if (!value || Array.from(value).length > 512) throw new Error('Enter a correlation value of 1–512 Unicode characters.');
      const query = cursor && traceQuery ? { ...traceQuery, cursor } : { ...queryDraft(), cursor: null, lane: 'events' as const };
      const result = await write<Trace>(`${path}/correlation`, { ...query, mode, field, value });
      if (alive.current && current === version.current && result.project_id === projectId && result.items.every(item => item.project_id === projectId)) { setTrace(result); setTraceQuery(query); }
    } catch (cause) { if (alive.current && current === version.current) setError(message(cause)); }
    finally { if (alive.current && current === version.current) setBusy(''); }
  }
  async function changeBookmark(bookmarkId: string, annotation: string, pinContext: boolean, remove = false) {
    if (!workspace || !bookmarks) return;
    const current = version.current; setBusy(remove ? 'Deleting bookmark' : 'Updating annotation'); setError('');
    try {
      const result = await write<BookmarksWithPins>(`${path}/bookmarks/${encodeURIComponent(bookmarkId)}${remove ? '/delete' : ''}`, remove ? { expected_revision: bookmarks.revision } : { expected_revision: bookmarks.revision, annotation, pin_context: pinContext }, remove ? 'POST' : 'PATCH');
      if (alive.current && current === version.current && result.project_id === projectId && result.investigation_id === investigationId) { setBookmarks(result); onWorkspace({ ...workspace, revision: result.revision, ...(result.pin_groups ? { pin_groups: result.pin_groups } : {}) }); }
    } catch (cause) { if (alive.current && current === version.current) setError(message(cause)); }
    finally { if (alive.current && current === version.current) setBusy(''); }
  }
  async function expireCache() {
    if (!workspace) return;
    const current = version.current; setBusy('Expiring source cache'); setError('');
    try {
      const result = await write<{ project_id: string; investigation_id: string; revision: number; availability: 'unavailable'; cache_cleanup_pending: boolean }>(`${path}/expire`, { expected_revision: workspace.revision });
      if (alive.current && current === version.current && result.project_id === projectId && result.investigation_id === investigationId) {
        setExpiring(false); onWorkspace({ ...workspace, revision: result.revision, availability: result.availability }); onExpired();
        setNotice(result.cache_cleanup_pending ? 'Source data is unavailable. Captured-file cleanup is still pending; pinned bookmark context remains retained.' : 'Source cache removed. Pinned bookmark context remains retained; ordinary event queries are unavailable.');
      }
    } catch (cause) { if (alive.current && current === version.current) setError(message(cause)); }
    finally { if (alive.current && current === version.current) setBusy(''); }
  }
  const pinGroups = bookmarks?.pin_groups ?? [];
  const groupedBookmarkIds = new Set(pinGroups.flatMap(pin => pin.bookmark_ids));
  const ungroupedBookmarks = bookmarks?.items.filter(bookmark => !groupedBookmarkIds.has(bookmark.bookmark_id)) ?? [];
  return <section className="investigation-tools" aria-label={t("Personal investigation tools")}>
    <div className="panel-heading"><h3>{offline ? t("Private offline investigation") : t("Personal investigation workspace")}</h3>{workspace && <span className="pill">{workspace.saved ? t('Saved · revision {revision}', { revision: workspace.revision }) : t("Unsaved workspace")}</span>}</div>
    {error && <ErrorNotice>{t(error)}</ErrorNotice>}{notice && <p role="status">{t(notice)}</p>}
    {offline && <p className="history-warning">{t("Offline imported copy · Origin system")} <code>{offline.document.origin.project_id}</code> {t("· Origin investigation")} <code>{offline.document.origin.investigation_id}</code>{t(". No active connection profile was imported.")}</p>}
    {(workspace || offline) && <><div className="form-grid"><label>{t("Investigation title")}<input aria-label={t("Investigation title")} value={title} maxLength={200} onChange={event => setTitle(event.target.value)} /></label><label>{t("Private investigation notes")}<textarea aria-label={t("Private investigation notes")} value={notes} maxLength={10000} rows={3} onChange={event => setNotes(event.target.value)} /></label></div>{workspace && <><div className="investigation-actions">{!offline && <label className="checkbox-label"><input type="checkbox" checked={pinned} onChange={event => setPinned(event.target.checked)} />{t("Pin captured sources against expiry")}</label>}<button title={t("Save the title, notes, filters, layout and retention choice.")} className="primary" disabled={!!busy} onClick={() => { void save(); }}>{t("Save investigation workspace")}</button><a title={t("Open this investigation in an independent browser tab.")} href={`/systems/${encodeURIComponent(projectId)}/investigations/${encodeURIComponent(investigationId!)}`} target="_blank" rel="noopener noreferrer">{t("Open saved investigation separately")}</a></div><p className={workspace.availability === 'retained' ? 'muted' : 'history-warning'}>{t("Data availability:")} <strong data-testid="investigation-availability">{t(workspace.availability)}</strong> · {workspace.collection_references.length} {t("collection reference(s).")} {offline ? t("Imported evidence stays offline; personal edits do not change the original bundle.") : t("Unpinned cache may expire; expired data requires explicit collection.")}</p></>}</>}
    <BundleTransfer key={`${projectId}:${investigationId ?? 'new'}`} projectId={projectId} systemName={systemName} investigationId={investigationId} onOpen={onOpen} />
    {investigationId && <details className="correlation-tools" open><summary title={t("Show correlation search and the time-ordered event trace.")}>{t("Correlation search and chronological trace")}</summary><div className="correlation-controls"><label>{t("Correlation search mode")}<select aria-label={t("Correlation search mode")} value={mode} onChange={event => { setMode(event.target.value as 'exact' | 'literal'); setTrace(null); }}><option value="exact">{t("Exact configured field")}</option><option value="literal">{t("Literal text")}</option></select></label><label>{t("Correlation field")}<input aria-label={t("Correlation field")} value={field} maxLength={64} pattern="[A-Za-z_][A-Za-z0-9_]{0,63}" disabled={mode === 'literal'} onChange={event => { setField(event.target.value); setTrace(null); }} placeholder="request_id" /></label><label>{t("Correlation value")}<input aria-label={t("Correlation value")} value={value} maxLength={1024} onChange={event => { setValue(event.target.value); setTrace(null); }} placeholder="REQ-0042" /></label><button title={t("Find matching correlation events using the current filters.")} disabled={!!busy} onClick={() => { void search(); }}>{t("Find chronological trace")}</button></div><p className="muted">{t("Exact search compares the complete parsed field. Literal search also finds longer values such as REQ-00420. Current process, UTC and literal filters apply. Observed clock deltas do not establish network latency or causality.")}</p>{trace && <><p role="status" data-testid="trace-count">{trace.matched_count ?? t("Unknown")} {t("trace matches")}{trace.partial ? t(" · Partial coverage") : ''}</p><p>{trace.warning}</p><ol className="trace-events" aria-label={t("Chronological correlation trace")}>{trace.items.map(event => { const delta = trace.deltas.find(item => item.event_id === event.event_id); return <li key={`${projectId}:${event.event_id}`}><div><code>{event.timestamp_utc ? formatUtcTimestamp(event.timestamp_utc) : t("Unknown timestamp")}</code><strong>{event.server_name_snapshot} / {event.process_name_snapshot}</strong><span>{delta?.delta_us == null ? t("First event on this page") : `Δ ${delta.delta_us} µs`}{delta?.source_time_inversion ? t(" · Source time inversion") : ''}</span><button title={t("Open the original source and context for this trace event.")} onClick={() => { if (traceQuery) onInspect(event, traceQuery); }}>{t("Inspect trace event")}</button></div><pre>{event.raw_line}</pre></li>; })}</ol>{trace.next_cursor && <button title={t("Show the next page of correlation matches.")} disabled={!!busy} onClick={() => { void search(trace.next_cursor); }}>{t("Next trace page")}</button>}</>}</details>}
    {!!pinGroups.length && bookmarks && <section className="investigation-pins" aria-label={t('Pins')}><h4>{t('Pins')}</h4>{pinGroups.map(pin => <article className="pin-card pin-summary" data-pin-id={pin.id} key={`${projectId}:${pin.id}`}><span title={pin.description}>{pin.description || t('Pin · {count} logs', { count: pin.bookmark_ids.length })}</span><button type="button" title={t("Open the saved log entries and description for this pin.")} disabled={!!busy} onClick={() => onViewPin(pin, bookmarks.items)}>{t('View')}</button></article>)}</section>}
    {!!ungroupedBookmarks.length && <section className="investigation-bookmarks" aria-label={t("Saved bookmarks")}><h4>{t("Bookmarks and pinned context")}</h4>{ungroupedBookmarks.map(bookmark => <BookmarkEditor key={`${projectId}:${bookmark.bookmark_id}`} bookmark={bookmark} busy={!!busy} onSave={(annotation, pin) => { void changeBookmark(bookmark.bookmark_id, annotation, pin); }} onDelete={() => { void changeBookmark(bookmark.bookmark_id, '', false, true); }} />)}</section>}
    {offline && !bookmarks && !!offline.document.bookmarks.length && <section aria-label={t("Imported bookmarks")}><h4>{t("Imported annotations and context")}</h4>{offline.document.bookmarks.map(bookmark => <article className="bookmark-card" key={`${projectId}:${bookmark.id}`}><strong>{bookmark.server_name_snapshot} / {bookmark.process_name_snapshot}</strong><p>{bookmark.annotation}</p><code>{bookmark.event_id}</code>{bookmark.context && <details><summary title={t("Show the retained lines surrounding this bookmarked event.")}>{t("Retained source context")}</summary><ol className="source-context">{bookmark.context.items.map(item => <li key={`${projectId}:${item.event.event_id}`}><span>{item.is_anchor ? t("Bookmarked event") : t("Context")}{item.outside_time_bounds ? t(" · Outside time bounds") : ''}{!item.matches_filter ? t(" · Outside literal filter") : ''}</span><pre>{item.event.raw_line}</pre></li>)}</ol></details>}</article>)}</section>}
    {workspace && !offline && <div className="investigation-actions"><button title={t("Review removal of this investigation's unpinned captured data.")} disabled={!!busy || workspace.pinned || workspace.availability === 'unavailable'} onClick={() => setExpiring(true)}>{t("Expire captured source cache")}</button><span className="muted">{t("Unpin and save the workspace before expiring its raw data. Pinned bookmark contexts have a combined 32 MiB limit.")}</span></div>}
    {expiring && workspace && <Modal title={t("Expire captured source cache")} onClose={() => { if (!busy) setExpiring(false); }}><p className="target-system">{t("System:")} <strong>{systemName}</strong><code>{projectId}</code></p><p>{t("Remove this investigation’s captured source bytes and event index. Existing notes and pinned bookmark context remain private and available. Unpinned surrounding context becomes unavailable. This cannot be undone without explicit recollection.")}</p>{error && <ErrorNotice>{t(error)}</ErrorNotice>}<div className="form-actions"><button title={t("Close this dialog and keep the captured source data.")} disabled={!!busy} onClick={() => setExpiring(false)}>{t("Keep source cache")}</button><button title={t("Remove captured source bytes and the event index for this investigation.")} className="danger-button" disabled={!!busy} onClick={() => { void expireCache(); }}>{t("Remove unpinned source cache")}</button></div></Modal>}
    {busy && <p role="status">{t(busy)}</p>}
  </section>;
}

function BookmarkEditor({ bookmark, busy, onSave, onDelete }: { bookmark: Bookmarks['items'][number]; busy: boolean; onSave: (annotation: string, pin: boolean) => void; onDelete: () => void }) {
  const { t } = useI18n();
  const [annotation, setAnnotation] = useState(bookmark.annotation); const [pin, setPin] = useState(bookmark.pin_context);
  useEffect(() => { setAnnotation(bookmark.annotation); setPin(bookmark.pin_context); }, [bookmark]);
  return <article className="bookmark-card"><strong>{bookmark.server_name_snapshot} / {bookmark.process_name_snapshot}</strong><code>{bookmark.event_id}</code><label>{t("Bookmark annotation")}<textarea aria-label={t("Bookmark annotation")} value={annotation} rows={2} maxLength={10000} onChange={event => setAnnotation(event.target.value)} /></label><div className="investigation-actions"><label className="checkbox-label"><input type="checkbox" checked={pin} onChange={event => setPin(event.target.checked)} />{t("Pin surrounding context")}</label><button title={t("Save this annotation and its surrounding-context retention choice.")} disabled={busy} onClick={() => onSave(annotation, pin)}>{t("Save annotation")}</button><button title={t("Delete this bookmark and its saved annotation.")} disabled={busy} onClick={onDelete}>{t("Delete bookmark")}</button></div>{!pin && <p className="history-warning">{t("This context may become unavailable after cache expiry. Pin it before removing captured sources.")}</p>}{!bookmark.context && <p className="history-warning">{t("Surrounding context is unavailable. Its source cache expired or it was not pinned.")}</p>}<details><summary title={t("Show the retained lines surrounding this bookmarked event.")}>{t("Retained source context (")}{bookmark.context?.items.length ?? 0} {t("lines)")}</summary><ol className="source-context">{bookmark.context?.items.map(item => <li className={item.is_anchor ? 'context-anchor' : ''} key={`${item.event.project_id}:${item.event.event_id}`}><span>{item.is_anchor ? t("Bookmarked event") : t("Context")}{item.outside_time_bounds ? t(" · Outside time bounds") : ''}{!item.matches_filter ? t(" · Outside literal filter") : ''}</span><pre>{item.event.raw_line}</pre></li>)}</ol></details></article>;
}
