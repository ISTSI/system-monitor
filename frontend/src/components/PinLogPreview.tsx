import type { HistoricalEvent } from '../investigation';
import { groupPinLogs } from '../investigationPins';
import { useI18n } from '../i18n';
import { formatUtcTimestamp } from '../utcDateTime';

export default function PinLogPreview({ events, label }: { events: HistoricalEvent[]; label: string }) {
  const { t } = useI18n();
  return <div className="pin-process-logs" aria-label={label}>{groupPinLogs(events).map(group => <section className="pin-process-log" key={`${group.projectId}:${group.processId}`} data-process-id={group.processId}>
    <h3 title={group.processId}>{group.serverName}: {group.processName}</h3>
    <pre tabIndex={0}>{group.events.map(event => <span key={`${event.project_id}:${event.event_id}`} data-pin-event-id={event.event_id} title={`${event.timestamp_utc ? formatUtcTimestamp(event.timestamp_utc) : t('Unknown timestamp')} UTC · ${event.source.remote_path}${event.source.archive_member ? ` · ${event.source.archive_member}` : ''} · ${event.event_id}`}>{event.raw_line}{event.raw_line.endsWith('\n') ? '' : '\n'}</span>)}</pre>
  </section>)}</div>;
}
