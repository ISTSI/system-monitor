import { useEffect, useRef, useState } from 'react';
import { message, write } from '../api/client';
import type { InvestigationWorkspace } from '../investigation';
import type { BookmarksWithPins, PinGroupItem, PinSelectionEntry } from '../investigationPins';
import { useI18n } from '../i18n';
import { ErrorNotice, Modal } from './Common';
import PinLogPreview from './PinLogPreview';

export default function InvestigationPinDialog({ projectId, systemName, investigationId, workspace, offline, entries, pin, replaceSelection = false, allowDelete = false, onSaved, onClose, onModify }: {
  projectId: string;
  systemName: string;
  investigationId: string;
  workspace: InvestigationWorkspace;
  offline: boolean;
  entries: PinSelectionEntry[];
  pin?: PinGroupItem;
  replaceSelection?: boolean;
  allowDelete?: boolean;
  onSaved: (response: BookmarksWithPins) => void;
  onClose: () => void;
  onModify?: (pin: PinGroupItem, entries: PinSelectionEntry[]) => void;
}) {
  const { t } = useI18n();
  const [description, setDescription] = useState(pin?.description ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const alive = useRef(true); const version = useRef(0);
  useEffect(() => {
    alive.current = true; setBusy(false); setError(''); setDescription(pin?.description ?? '');
    return () => { alive.current = false; version.current += 1; };
  }, [projectId, investigationId, offline, pin?.id, pin?.description]);
  const path = `/projects/${encodeURIComponent(projectId)}/${offline ? 'bundle-investigations' : 'investigations'}/${encodeURIComponent(investigationId)}/pins`;

  function validateWorkspace() {
    if (workspace.project_id !== projectId || workspace.investigation_id !== investigationId
      || entries.some(({ event, query }) => event.project_id !== projectId || !query.process_ids.includes(event.process_id))) {
      throw new Error('The selected logs do not belong to this investigation.');
    }
    if (pin && !workspace.pin_groups?.some(group => group.id === pin.id)) throw new Error('The selected pin does not belong to this investigation.');
  }

  async function deletePin() {
    if (busy || !pin) return;
    const current = ++version.current;
    setBusy(true); setError('');
    try {
      validateWorkspace();
      const result = await write<BookmarksWithPins>(`${path}/${encodeURIComponent(pin.id)}/delete`, { expected_revision: workspace.revision });
      if (!alive.current || current !== version.current) return;
      if (result.project_id !== projectId || result.investigation_id !== investigationId || result.revision !== workspace.revision + 1
        || result.pin_groups?.some(group => group.id === pin.id)) throw new Error('The saved pin response did not match this investigation.');
      onSaved(result);
    } catch (cause) {
      if (alive.current && current === version.current) setError(message(cause));
    } finally {
      if (alive.current && current === version.current) setBusy(false);
    }
  }

  async function savePin() {
    if (busy) return;
    const current = ++version.current;
    setBusy(true); setError('');
    try {
      const writingSelection = !pin || replaceSelection;
      if (writingSelection && (!entries.length || entries.length > 100)) throw new Error('Select between 1 and 100 log entries for a pin.');
      validateWorkspace();
      if (new Set(entries.map(entry => entry.event.event_id)).size !== entries.length) throw new Error('Select each log entry only once.');
      if (Array.from(description).length > 10000) throw new Error('A pin description allows at most 10,000 Unicode characters.');
      const expectedRevision = workspace.revision;
      const existingGroupIds = new Set(workspace.pin_groups?.map(group => group.id) ?? []);
      const result = await write<BookmarksWithPins>(pin ? `${path}/${encodeURIComponent(pin.id)}` : path, {
        expected_revision: expectedRevision,
        description,
        ...(writingSelection ? { events: entries.map(({ event, query }) => ({
          event_id: event.event_id, from: query.from, to: query.to, filter: query.filter,
          per_process_filters: query.per_process_filters?.[event.process_id]
            ? { [event.process_id]: query.per_process_filters[event.process_id] } : {},
        })) } : {}),
      }, pin ? 'PATCH' : 'POST');
      if (!alive.current || current !== version.current) return;
      const selected = new Set(entries.map(entry => entry.event.event_id));
      const acknowledgedGroup = result.pin_groups?.find(group => (pin ? group.id === pin.id : !existingGroupIds.has(group.id)) && group.description === description
        && (!writingSelection ? group.bookmark_ids.length === pin!.bookmark_ids.length && group.bookmark_ids.every(id => pin!.bookmark_ids.includes(id))
          : group.bookmark_ids.length === entries.length && group.bookmark_ids.every(id => {
          const bookmark = result.items.find(item => item.bookmark_id === id);
          return bookmark && selected.has(bookmark.event_id);
        })));
      const savedEventIds = acknowledgedGroup?.bookmark_ids.map(id => result.items.find(item => item.bookmark_id === id)!.event_id);
      if (result.project_id !== projectId || result.investigation_id !== investigationId || result.revision !== expectedRevision + 1
        || !acknowledgedGroup || (writingSelection && new Set(savedEventIds).size !== entries.length)
        || result.items.some(item => item.context?.items.some(context => context.event.project_id !== projectId))) {
        throw new Error('The saved pin response did not match this investigation.');
      }
      onSaved(result);
    } catch (cause) {
      if (alive.current && current === version.current) setError(message(cause));
    } finally {
      if (alive.current && current === version.current) setBusy(false);
    }
  }

  const unavailable = pin && !replaceSelection ? pin.bookmark_ids.length - entries.length : 0;
  return <Modal title={t(pin && !replaceSelection ? 'View pin' : 'Pin selected logs')} onClose={() => { if (!busy) onClose(); }}>
    <p className="target-system">{t('System:')} <strong>{systemName}</strong><code>{projectId}</code></p>
    {error && <ErrorNotice>{t(error)}</ErrorNotice>}
    <p>{t('{count} selected logs', { count: pin && !replaceSelection ? pin.bookmark_ids.length : entries.length })}</p>
    <PinLogPreview events={entries.map(entry => entry.event)} label={t(pin ? 'Pinned log entries' : 'Selected logs')} />
    {unavailable > 0 && <p className="history-warning">{t('This pinned log entry is unavailable.')} ({unavailable})</p>}
    <label>{t('Pin description')}<textarea aria-label={t('Pin description')} rows={4} maxLength={10000} value={description} disabled={busy} onChange={event => setDescription(event.target.value)} placeholder={t('Describe why these log entries matter.')} /></label>
    <div className="form-actions"><button type="button" title={pin ? t("Save changes to this pin.") : t("Save these log entries and their description as a pin.")} className="primary" disabled={busy || ((!pin || replaceSelection) && !entries.length)} onClick={() => { void savePin(); }}>{t(busy ? 'Saving pin' : 'Save')}</button><button type="button" title={t("Discard unsaved pin changes and close this dialog.")} disabled={busy} onClick={onClose}>{t('Cancel')}</button>{pin && onModify && <button type="button" title={t("Return to the log table to change the entries in this pin.")} disabled={busy || !entries.length || unavailable > 0} onClick={() => onModify({ ...pin, description }, entries)}>{t('Modify')}</button>}{pin && allowDelete && <button type="button" title={t("Delete this pin and its saved log selection.")} disabled={busy} onClick={() => { void deletePin(); }}>{t('Delete pin')}</button>}</div>
  </Modal>;
}
