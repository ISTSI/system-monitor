import type { CSSProperties, ReactNode } from 'react';
import { useI18n } from '../i18n';
import type { HistoricalEvent } from '../investigation';
import { filtersForLog, type HighlightContext } from '../logHighlight';
import { formatUtcTimestamp } from '../utcDateTime';
import LogText from './LogText';

export type LogColumns = { timestamp: boolean; process: boolean; host: boolean };
export const LOG_ROW_HEIGHT = 20;

export function logTableStyle(columns: LogColumns, context = false): CSSProperties {
  const metadataWidth = (context ? 22 : 0) + (columns.timestamp ? 156 : 0) + (columns.process ? 155 : 0) + (columns.host ? 145 : 0);
  return {
    '--log-columns': `${context ? '22px ' : ''}${columns.timestamp ? '156px ' : ''}${columns.process ? '155px ' : ''}${columns.host ? '145px ' : ''}minmax(400px, 1fr)`,
    '--log-min-width': `${metadataWidth + 400}px`,
  } as CSSProperties;
}

export function LogColumnHeadings({ columns, context = false, className = '' }: { columns: LogColumns; context?: boolean; className?: string }) {
  const { t } = useI18n();
  return <div role="row" className={`log-columns log-column-headings ${className}`}>
    {context && <span role="columnheader" aria-label={t('Inspect')} />}
    {columns.timestamp && <span role="columnheader">{t('Event time UTC')}</span>}
    {columns.process && <span role="columnheader">{t('Process')}</span>}
    {columns.host && <span role="columnheader">{t('Host')}</span>}
    <span role="columnheader">{t('Log entry')}</span>
  </div>;
}

export function LogEventCells({ event, columns, highlights, notice, messageClassName = '' }: { event: HistoricalEvent; columns: LogColumns; highlights: HighlightContext | null; notice?: ReactNode; messageClassName?: string }) {
  const { t } = useI18n();
  return <>
    {columns.timestamp && <code role="cell" className="log-timestamp">{event.timestamp_utc ? formatUtcTimestamp(event.timestamp_utc) : t('Unknown timestamp')}</code>}
    {columns.process && <span role="cell" title={event.process_id}>{event.process_name_snapshot}</span>}
    {columns.host && <span role="cell" title={event.server_id}>{event.server_name_snapshot}</span>}
    <code role="cell" className={`log-message ${messageClassName}`}>{notice}<LogText highlightLimitTitle={t('Highlight limit reached; original text and filter results are unchanged.')} rawLine={event.raw_line} timestampOriginal={event.timestamp_original} timestampUtc={event.timestamp_utc} filters={filtersForLog(highlights, event.process_id)} /></code>
  </>;
}
