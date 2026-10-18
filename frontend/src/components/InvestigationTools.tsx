import { useEffect, useRef, useState } from 'react';
import { message, request, write } from '../api/client';
import type { Bookmarks, HistoricalEvent, HistoricalQuery, InvestigationWorkspace, OfflineInvestigation, Trace } from '../investigation';
import { ErrorNotice, Modal } from './Common';
import BundleTransfer from './BundleTransfer';

export default function InvestigationTools({ projectId, systemName, investigationId, workspace, offline, queryDraft, layout, onWorkspace, onInspect, onOpen, onExpired }: {
  projectId: string; systemName: string; investigationId?: string; workspace: InvestigationWorkspace | null;
  offline: OfflineInvestigation | null; queryDraft: () => HistoricalQuery; layout: 'merged' | 'split';
  onWorkspace: (value: InvestigationWorkspace) => void; onInspect: (event: HistoricalEvent, query: HistoricalQuery) => void; onOpen: (id: string) => void; onExpired: () => void;
}) {
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const path = investigationId ? `${base}/${offline ? 'bundle-investigations' : 'investigations'}/${encodeURIComponent(investigationId)}` : '';
  const [title, setTitle] = useState(''); const [notes, setNotes] = useState(''); const [pinned, setPinned] = useState(false);
  const [bookmarks, setBookmarks] = useState<Bookmarks | null>(null);
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
    version.current += 1; setTrace(null); setTraceQuery(null); setError(''); setNotice('');
  }, [path, projectId, investigationId, offline]);
  useEffect(() => {
    let current = true;
    setBookmarks(null);
    if (!path) return;
    void request<Bookmarks>(`${path}/bookmarks`).then(result => { if (alive.current && current && result.project_id === projectId && result.investigation_id === investigationId) setBookmarks(result); }).catch((cause: unknown) => { if (alive.current && current) setError(message(cause)); });
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
      const result = await write<Bookmarks>(`${path}/bookmarks/${encodeURIComponent(bookmarkId)}${remove ? '/delete' : ''}`, remove ? { expected_revision: bookmarks.revision } : { expected_revision: bookmarks.revision, annotation, pin_context: pinContext }, remove ? 'POST' : 'PATCH');
      if (alive.current && current === version.current && result.project_id === projectId && result.investigation_id === investigationId) { setBookmarks(result); onWorkspace({ ...workspace, revision: result.revision }); }
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
  return <section className="investigation-tools" aria-label="Personal investigation tools">
    <div className="panel-heading"><h3>{offline ? 'Private offline investigation' : 'Personal investigation workspace'}</h3>{workspace && <span className="pill">{workspace.saved ? `Saved · revision ${workspace.revision}` : 'Unsaved workspace'}</span>}</div>
    {error && <ErrorNotice>{error}</ErrorNotice>}{notice && <p role="status">{notice}</p>}
    {offline && <p className="history-warning">Offline imported copy · Origin system <code>{offline.document.origin.project_id}</code> · Origin investigation <code>{offline.document.origin.investigation_id}</code>. No active connection profile was imported.</p>}
    {(workspace || offline) && <><div className="form-grid"><label>Investigation title<input aria-label="Investigation title" value={title} maxLength={200} onChange={event => setTitle(event.target.value)} /></label><label>Private investigation notes<textarea aria-label="Private investigation notes" value={notes} maxLength={10000} rows={3} onChange={event => setNotes(event.target.value)} /></label></div>{workspace && <><div className="investigation-actions">{!offline && <label className="checkbox-label"><input type="checkbox" checked={pinned} onChange={event => setPinned(event.target.checked)} />Pin captured sources against expiry</label>}<button className="primary" disabled={!!busy} onClick={() => { void save(); }}>Save investigation workspace</button><a href={`/systems/${encodeURIComponent(projectId)}/investigations/${encodeURIComponent(investigationId!)}`} target="_blank" rel="noopener noreferrer">Open saved investigation separately</a></div><p className={workspace.availability === 'retained' ? 'muted' : 'history-warning'}>Data availability: <strong data-testid="investigation-availability">{workspace.availability}</strong> · {workspace.collection_references.length} collection reference(s). {offline ? 'Imported evidence stays offline; personal edits do not change the original bundle.' : 'Unpinned cache may expire; expired data requires explicit collection.'}</p></>}</>}
    <BundleTransfer projectId={projectId} systemName={systemName} investigationId={investigationId} onOpen={onOpen} />
    {investigationId && <details className="correlation-tools" open><summary>Correlation search and chronological trace</summary><div className="correlation-controls"><label>Correlation search mode<select aria-label="Correlation search mode" value={mode} onChange={event => { setMode(event.target.value as 'exact' | 'literal'); setTrace(null); }}><option value="exact">Exact configured field</option><option value="literal">Literal text</option></select></label><label>Correlation field<input aria-label="Correlation field" value={field} maxLength={64} pattern="[A-Za-z_][A-Za-z0-9_]{0,63}" disabled={mode === 'literal'} onChange={event => { setField(event.target.value); setTrace(null); }} placeholder="request_id" /></label><label>Correlation value<input aria-label="Correlation value" value={value} maxLength={1024} onChange={event => { setValue(event.target.value); setTrace(null); }} placeholder="REQ-0042" /></label><button disabled={!!busy} onClick={() => { void search(); }}>Find chronological trace</button></div><p className="muted">Exact search compares the complete parsed field. Literal search also finds longer values such as REQ-00420. Current process, UTC and literal filters apply. Observed clock deltas do not establish network latency or causality.</p>{trace && <><p role="status" data-testid="trace-count">{trace.matched_count ?? 'Unknown'} trace matches{trace.partial ? ' · Partial coverage' : ''}</p><p>{trace.warning}</p><ol className="trace-events" aria-label="Chronological correlation trace">{trace.items.map(event => { const delta = trace.deltas.find(item => item.event_id === event.event_id); return <li key={`${projectId}:${event.event_id}`}><div><code>{event.timestamp_utc ?? 'Unknown timestamp'}</code><strong>{event.server_name_snapshot} / {event.process_name_snapshot}</strong><span>{delta?.delta_us == null ? 'First event on this page' : `Δ ${delta.delta_us} µs`}{delta?.source_time_inversion ? ' · Source time inversion' : ''}</span><button onClick={() => { if (traceQuery) onInspect(event, traceQuery); }}>Inspect trace event</button></div><pre>{event.raw_line}</pre></li>; })}</ol>{trace.next_cursor && <button disabled={!!busy} onClick={() => { void search(trace.next_cursor); }}>Next trace page</button>}</>}</details>}
    {!!bookmarks?.items.length && <section className="investigation-bookmarks" aria-label="Saved bookmarks"><h4>Bookmarks and pinned context</h4>{bookmarks.items.map(bookmark => <BookmarkEditor key={`${projectId}:${bookmark.bookmark_id}`} bookmark={bookmark} busy={!!busy} onSave={(annotation, pin) => { void changeBookmark(bookmark.bookmark_id, annotation, pin); }} onDelete={() => { void changeBookmark(bookmark.bookmark_id, '', false, true); }} />)}</section>}
    {offline && !bookmarks && !!offline.document.bookmarks.length && <section aria-label="Imported bookmarks"><h4>Imported annotations and context</h4>{offline.document.bookmarks.map(bookmark => <article className="bookmark-card" key={`${projectId}:${bookmark.id}`}><strong>{bookmark.server_name_snapshot} / {bookmark.process_name_snapshot}</strong><p>{bookmark.annotation}</p><code>{bookmark.event_id}</code>{bookmark.context && <details><summary>Retained source context</summary><ol className="source-context">{bookmark.context.items.map(item => <li key={`${projectId}:${item.event.event_id}`}><span>{item.is_anchor ? 'Bookmarked event' : 'Context'}{item.outside_time_bounds ? ' · Outside time bounds' : ''}{!item.matches_filter ? ' · Outside literal filter' : ''}</span><pre>{item.event.raw_line}</pre></li>)}</ol></details>}</article>)}</section>}
    {workspace && !offline && <div className="investigation-actions"><button disabled={!!busy || workspace.pinned || workspace.availability === 'unavailable'} onClick={() => setExpiring(true)}>Expire captured source cache</button><span className="muted">Unpin and save the workspace before expiring its raw data. Pinned bookmark contexts have a combined 32 MiB limit.</span></div>}
    {expiring && workspace && <Modal title="Expire captured source cache" onClose={() => { if (!busy) setExpiring(false); }}><p className="target-system">System: <strong>{systemName}</strong><code>{projectId}</code></p><p>Remove this investigation’s captured source bytes and event index. Existing notes and pinned bookmark context remain private and available. Unpinned surrounding context becomes unavailable. This cannot be undone without explicit recollection.</p>{error && <ErrorNotice>{error}</ErrorNotice>}<div className="form-actions"><button disabled={!!busy} onClick={() => setExpiring(false)}>Keep source cache</button><button className="danger-button" disabled={!!busy} onClick={() => { void expireCache(); }}>Remove unpinned source cache</button></div></Modal>}
    {busy && <p role="status">{busy}</p>}
  </section>;
}

function BookmarkEditor({ bookmark, busy, onSave, onDelete }: { bookmark: Bookmarks['items'][number]; busy: boolean; onSave: (annotation: string, pin: boolean) => void; onDelete: () => void }) {
  const [annotation, setAnnotation] = useState(bookmark.annotation); const [pin, setPin] = useState(bookmark.pin_context);
  useEffect(() => { setAnnotation(bookmark.annotation); setPin(bookmark.pin_context); }, [bookmark]);
  return <article className="bookmark-card"><strong>{bookmark.server_name_snapshot} / {bookmark.process_name_snapshot}</strong><code>{bookmark.event_id}</code><label>Bookmark annotation<textarea aria-label="Bookmark annotation" value={annotation} rows={2} maxLength={10000} onChange={event => setAnnotation(event.target.value)} /></label><div className="investigation-actions"><label className="checkbox-label"><input type="checkbox" checked={pin} onChange={event => setPin(event.target.checked)} />Pin surrounding context</label><button disabled={busy} onClick={() => onSave(annotation, pin)}>Save annotation</button><button disabled={busy} onClick={onDelete}>Delete bookmark</button></div>{!pin && <p className="history-warning">This context may become unavailable after cache expiry. Pin it before removing captured sources.</p>}{!bookmark.context && <p className="history-warning">Surrounding context is unavailable. Its source cache expired or it was not pinned.</p>}<details><summary>Retained source context ({bookmark.context?.items.length ?? 0} lines)</summary><ol className="source-context">{bookmark.context?.items.map(item => <li className={item.is_anchor ? 'context-anchor' : ''} key={`${item.event.project_id}:${item.event.event_id}`}><span>{item.is_anchor ? 'Bookmarked event' : 'Context'}{item.outside_time_bounds ? ' · Outside time bounds' : ''}{!item.matches_filter ? ' · Outside literal filter' : ''}</span><pre>{item.event.raw_line}</pre></li>)}</ol></details></article>;
}
