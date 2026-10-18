import assert from 'node:assert/strict';
import { test } from 'node:test';
import { groupPinLogs, pinSelectionFromBookmarks } from '../src/investigationPins.ts';

const event = (eventId, processId = 'process-a', projectId = 'system-a') => ({
  project_id: projectId, event_id: eventId, process_id: processId,
  server_name_snapshot: 'Server', process_name_snapshot: 'Process',
  raw_line: '<script>untrusted identical source text</script>', timestamp_utc: '2026-10-18T12:34:56.123456Z',
});
const bookmark = (id, anchor) => ({
  bookmark_id: id, event_id: anchor.event_id,
  context: { project_id: anchor.project_id, event_id: anchor.event_id, items: [{ is_anchor: true, event: anchor }] },
});
const query = {
  process_ids: ['other-process'], from: '2026-10-18T00:00:00.000001Z', to: '2026-10-19T00:00:00.000001Z',
  filter: { include: ['currently invisible'], exclude: [], include_mode: 'all', case_sensitive: true },
  per_process_filters: {}, lane: 'events', limit: 100, cursor: 'old-page',
};

test('pin terminal groups preserve repeated source lines and isolate process identities by system', () => {
  const first = event('entry-1'); const second = event('entry-2', 'process-b'); const repeated = event('entry-3'); const foreign = event('entry-1', 'process-a', 'system-b');
  const groups = groupPinLogs([first, second, repeated, foreign]);
  assert.equal(groups.length, 3);
  assert.deepEqual(groups[0].events, [first, repeated]);
  assert.deepEqual(groups[1].events, [second]);
  assert.deepEqual(groups[2].events, [foreign]);
  assert.equal(groups[0].events[0].raw_line, '<script>untrusted identical source text</script>');
});

test('restoring pin selection uses retained anchors despite display filters and keeps exact collection bounds', () => {
  const first = event('entry-1'); const diagnostic = { ...event('entry-2', 'process-b'), timestamp_utc: null };
  const context = bookmark('bookmark-1', first);
  context.context.items.unshift({ is_anchor: false, event: event('surrounding-line') });
  const restored = pinSelectionFromBookmarks({ bookmark_ids: ['bookmark-2', 'bookmark-1'] }, [context, bookmark('bookmark-2', diagnostic)], query, 'system-a');
  assert.deepEqual(restored.map(entry => entry.event), [diagnostic, first]);
  assert.equal(restored[0].query.lane, 'diagnostic');
  assert.equal(restored[1].query.lane, 'events');
  assert.equal(restored[0].query.from, query.from); assert.equal(restored[0].query.to, query.to);
  assert.deepEqual(restored[0].query.process_ids, ['process-b']);
  assert.deepEqual(restored[0].query.filter.include, []); assert.equal(restored[0].query.cursor, null);
  assert.deepEqual(query.process_ids, ['other-process']); assert.deepEqual(query.filter.include, ['currently invisible']); assert.equal(query.cursor, 'old-page');
});

test('missing, cross-system and mismatched retained contexts cannot become a restored pin selection', () => {
  const valid = bookmark('valid', event('entry-1'));
  const foreign = bookmark('foreign', event('entry-2', 'process-a', 'system-b'));
  const wrongContext = bookmark('wrong-context', event('entry-3')); wrongContext.context.project_id = 'system-b';
  const wrongAnchor = bookmark('wrong-anchor', event('entry-4')); wrongAnchor.context.event_id = 'entry-999';
  const notAnchor = bookmark('not-anchor', event('entry-5')); notAnchor.context.items[0].is_anchor = false;
  const expired = { bookmark_id: 'expired', event_id: 'entry-6', context: null };
  const pin = { bookmark_ids: ['missing', 'foreign', 'wrong-context', 'wrong-anchor', 'not-anchor', 'expired', 'valid'] };
  const restored = pinSelectionFromBookmarks(pin, [valid, foreign, wrongContext, wrongAnchor, notAnchor, expired], query, 'system-a');
  assert.deepEqual(restored.map(entry => entry.event.event_id), ['entry-1']);
});
