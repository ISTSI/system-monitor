import type { components } from './api/schema';

export type LiveSession = components['schemas']['LiveSessionResponse'];
export type LiveSnapshot = components['schemas']['LiveSnapshot'];
export type LiveEvent = components['schemas']['LiveEvent'];
export type LiveFrame = components['schemas']['LiveFrame'];
export type LiteralFilter = components['schemas']['HistoricalFilter'];

export type FilterDraft = { contains: string; includes: string; excludes: string; mode: 'any' | 'all'; sensitive: boolean };
export const emptyFilter = (): FilterDraft => ({ contains: '', includes: '', excludes: '', mode: 'any', sensitive: true });

export function literalFilter(draft: FilterDraft): LiteralFilter {
  const include = [draft.contains, ...draft.includes.split('\n')].filter(term => term !== '');
  const exclude = draft.excludes.split('\n').filter(term => term !== '');
  if (include.length > 20 || exclude.length > 20 || [...include, ...exclude].some(term => Array.from(term).length > 512)) throw new Error('Use at most 20 include and 20 exclude terms, each at most 512 Unicode characters.');
  return { include, exclude, include_mode: draft.mode, case_sensitive: draft.sensitive };
}

export function filterDraft(filter: LiteralFilter): FilterDraft {
  return { contains: filter.include?.[0] ?? '', includes: filter.include?.slice(1).join('\n') ?? '', excludes: filter.exclude?.join('\n') ?? '', mode: filter.include_mode, sensitive: filter.case_sensitive };
}

export function terminal(status: string): boolean { return ['stopped', 'interrupted', 'failed', 'expired'].includes(status); }

export function validFrame(value: unknown, session: LiveSession, projectId: string, workspaceId: string): value is LiveFrame {
  if (!value || typeof value !== 'object') return false;
  const frame = value as Record<string, unknown>;
  return frame.protocol_version === 2 && frame.project_id === projectId && frame.workspace_id === workspaceId && frame.session_id === session.session_id
    && Number.isSafeInteger(frame.seq) && (frame.seq as number) > 0 && Number.isSafeInteger(frame.filter_version)
    && typeof frame.type === 'string' && ['snapshot', 'events', 'status', 'filter_applied', 'gap', 'resync_required', 'counters', 'heartbeat', 'error', 'stopped'].includes(frame.type)
    && typeof frame.sent_at === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(frame.sent_at) && !!frame.payload && typeof frame.payload === 'object';
}

export function validEvents(value: unknown, projectId: string, processIds: string[]): value is LiveEvent[] {
  return Array.isArray(value) && value.length <= 20000 && value.every(event => !!event && typeof event === 'object'
    && event.project_id === projectId && processIds.includes(event.process_id) && typeof event.event_id === 'string'
    && typeof event.raw_line === 'string' && typeof event.process_name_snapshot === 'string' && typeof event.server_name_snapshot === 'string'
    && (event.timestamp_utc === null || typeof event.timestamp_utc === 'string') && !!event.source
    && typeof event.source.source_revision_id === 'string' && Number.isSafeInteger(event.source.byte_start));
}

// Canonical UTC strings preserve exact microseconds; browser Date and float
// timestamp arithmetic are deliberately absent from event ordering.
export function compareEvents(a: LiveEvent, b: LiveEvent): number {
  for (const [left, right] of [[a.timestamp_utc ?? '', b.timestamp_utc ?? ''], [a.process_id, b.process_id], [a.source.source_revision_id, b.source.source_revision_id]] as const) {
    if (left !== right) return left < right ? -1 : 1;
  }
  return (a.source.member_ordinal ?? -1) - (b.source.member_ordinal ?? -1) || a.source.byte_start - b.source.byte_start || (a.event_id < b.event_id ? -1 : a.event_id > b.event_id ? 1 : 0);
}

export function mergeEvents(previous: LiveEvent[], incoming: LiveEvent[], limit = 20000): LiveEvent[] {
  const unique = new Map(previous.map(event => [`${event.project_id}:${event.event_id}`, event]));
  incoming.forEach(event => unique.set(`${event.project_id}:${event.event_id}`, event));
  return [...unique.values()].sort(compareEvents).slice(-limit);
}
