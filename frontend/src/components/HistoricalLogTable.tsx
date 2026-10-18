import { useEffect, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useI18n } from '../i18n';
import type { HistoricalEvent as LogEvent } from '../investigation';
import type { HighlightContext } from '../logHighlight';
import { Icon } from './Common';
import { LOG_ROW_HEIGHT, LogColumnHeadings, LogEventCells, logTableStyle, type LogColumns } from './LogTablePresentation';

export function VirtualLog({ events, label, columns, compact = false, onInspect, highlights, selectedEventIds, onToggleSelection, selectionDisabled = false }: {
  events: LogEvent[]; label: string; columns: LogColumns; compact?: boolean;
  onInspect: (event: LogEvent) => void; highlights: HighlightContext | null;
  selectedEventIds?: ReadonlySet<string>;
  onToggleSelection?: (event: LogEvent) => void;
  selectionDisabled?: boolean;
}) {
  const { t } = useI18n();
  const scroll = useRef<HTMLDivElement>(null);
  const virtual = useVirtualizer({ count: events.length, getScrollElement: () => scroll.current, estimateSize: () => LOG_ROW_HEIGHT, overscan: 6, getItemKey: index => `${events[index].project_id}:${events[index].event_id}` });
  useEffect(() => { virtual.scrollToOffset(0); if (scroll.current) scroll.current.scrollLeft = 0; }, [events, virtual]);
  const tableStyle = logTableStyle(columns, true);
  return <div ref={scroll} className={`virtual-logs ${compact ? 'compact' : ''}`} style={tableStyle} tabIndex={0} role="table" aria-label={label} aria-rowcount={events.length + 1} aria-colcount={2 + Number(columns.timestamp) + Number(columns.process) + Number(columns.host)}>
    <LogColumnHeadings columns={columns} context />
    <div className="virtual-log-content" style={{ height: virtual.getTotalSize() }}>{virtual.getVirtualItems().map(row => {
      const event = events[row.index];
      const inspectLabel = t('Inspect source line {line} from {name}', { line: event.source.line_number ?? '?', name: event.process_name_snapshot });
      const selected = selectedEventIds?.has(`${event.project_id}:${event.event_id}`) ?? false;
      const selectable = !!onToggleSelection && !selectionDisabled;
      return <div key={row.key} role="row" aria-rowindex={row.index + 2} aria-selected={onToggleSelection ? selected : undefined} tabIndex={selectable ? 0 : undefined}
        className={`log-columns log-event${selected ? ' log-event-selected' : ''}`} style={{ height: row.size, transform: `translateY(${row.start}px)` }}
        onClick={click => {
          if (!selectable) return;
          const target = click.target instanceof Element ? click.target : null;
          if (target?.closest('button, a, input, select, textarea, label, summary, [role="button"], [role="link"], [contenteditable="true"]')) return;
          const selection = window.getSelection();
          if (selection && !selection.isCollapsed && selection.anchorNode && click.currentTarget.contains(selection.anchorNode)) return;
          onToggleSelection?.(event);
        }} onKeyDown={key => {
          if (!selectable || key.target !== key.currentTarget || (key.key !== ' ' && key.key !== 'Enter')) return;
          key.preventDefault(); onToggleSelection?.(event);
        }}>
        <span role="cell" className="log-context-cell"><button type="button" className="log-context-button" aria-label={inspectLabel} title={inspectLabel} onClick={() => onInspect(event)}><Icon kind="eye" /></button></span>
        <LogEventCells event={event} columns={columns} highlights={highlights} />
      </div>;
    })}</div>
  </div>;
}
