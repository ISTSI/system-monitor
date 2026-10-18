import { useI18n } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { message, write } from '../api/client';
import type { Bookmarks, HistoricalEvent, HistoricalQuery, InvestigationWorkspace } from '../investigation';
import { ErrorNotice } from './Common';

export default function EventBookmark({ projectId, investigationId, workspace, event, query, onWorkspace, offline }: {
  projectId: string; investigationId: string; offline: boolean; workspace: InvestigationWorkspace; event: HistoricalEvent;
  query: HistoricalQuery; onWorkspace: (value: InvestigationWorkspace) => void;
}) {
  const { t } = useI18n();
  const [annotation, setAnnotation] = useState(''); const [pin, setPin] = useState(true);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [saved, setSaved] = useState(false);
  const alive = useRef(true); const version = useRef(0);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; version.current += 1; };
  }, [projectId, investigationId, event.event_id]);
  async function bookmark() {
    const current = ++version.current;
    setBusy(true); setError('');
    try {
      const result = await write<Bookmarks>(`/projects/${encodeURIComponent(projectId)}/${offline ? 'bundle-investigations' : 'investigations'}/${encodeURIComponent(investigationId)}/bookmarks`, { expected_revision: workspace.revision, event_id: event.event_id, annotation, before: 5, after: 5, pin_context: pin, from: query.from, to: query.to, filter: query.filter, per_process_filters: query.per_process_filters });
      if (alive.current && current === version.current && result.project_id === projectId && result.investigation_id === investigationId) { onWorkspace({ ...workspace, revision: result.revision }); setSaved(true); }
    } catch (cause) { if (alive.current && current === version.current) setError(message(cause)); } finally { if (alive.current && current === version.current) setBusy(false); }
  }
  return <section className="event-bookmark" aria-label={t("Bookmark this event")}><h3>{t("Bookmark and annotation")}</h3>{error && <ErrorNotice>{t(error)}</ErrorNotice>}<label>{t("Annotation for this event")}<textarea aria-label={t("Annotation for this event")} value={annotation} maxLength={10000} rows={2} onChange={change => { setAnnotation(change.target.value); setSaved(false); }} /></label><div className="investigation-actions"><label className="checkbox-label"><input type="checkbox" checked={pin} onChange={change => setPin(change.target.checked)} />{t("Pin five lines before and after")}</label><button disabled={busy || saved} onClick={() => { void bookmark(); }}>{saved ? t("Bookmark saved") : t("Bookmark event with context")}</button></div>{!pin && <p className="history-warning">{t("Unpinned context may expire with the source cache. Annotation does not modify the original bytes.")}</p>}</section>;
}
