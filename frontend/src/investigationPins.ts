import type { Bookmarks, HistoricalEvent, HistoricalQuery } from './investigation';
import type { components } from './api/schema';

export type PinGroupItem = components['schemas']['PinGroup'];

export type BookmarksWithPins = Bookmarks;
export type PinSelectionEntry = { event: HistoricalEvent; query: HistoricalQuery };

export type PinProcessLogs = {
  projectId: string;
  processId: string;
  serverName: string;
  processName: string;
  events: HistoricalEvent[];
};

// A process has one logical log source. Keep its selected rows together without
// deduplicating identical text at different source positions.
export function groupPinLogs(events: HistoricalEvent[]): PinProcessLogs[] {
  const processes = new Map<string, PinProcessLogs>();
  for (const event of events) {
    const key = JSON.stringify([event.project_id, event.process_id]);
    let group = processes.get(key);
    if (!group) {
      group = { projectId: event.project_id, processId: event.process_id, serverName: event.server_name_snapshot, processName: event.process_name_snapshot, events: [] };
      processes.set(key, group);
    }
    group.events.push(event);
  }
  return [...processes.values()];
}

// Saved contexts retain the original anchor even after source expiry. Restore
// those anchors independently of the current display predicate; no query or SSH
// connection is needed to view them. The caller supplies collection UTC bounds.
export function pinSelectionFromBookmarks(pin: PinGroupItem, bookmarks: Bookmarks['items'], query: HistoricalQuery, projectId: string): PinSelectionEntry[] {
  const members = new Map(bookmarks.map(bookmark => [bookmark.bookmark_id, bookmark]));
  const selected: PinSelectionEntry[] = [];
  for (const id of pin.bookmark_ids) {
    const bookmark = members.get(id);
    const anchor = bookmark?.context?.items.find(item => item.is_anchor && item.event.event_id === bookmark.event_id)?.event;
    if (!anchor || anchor.project_id !== projectId || bookmark?.context?.project_id !== projectId || bookmark.context.event_id !== anchor.event_id) continue;
    selected.push({ event: anchor, query: {
      ...query,
      process_ids: [anchor.process_id],
      filter: { include: [], exclude: [], include_mode: 'all', case_sensitive: true },
      per_process_filters: {},
      correlation: null,
      cursor: null,
      lane: anchor.timestamp_utc === null ? 'diagnostic' : 'events',
    } });
  }
  return selected;
}
